// Фоновая часть расширения WhoKey: разговаривает с мостом (native messaging)
// и вставляет логин и пароль в страницу.
//
// Почему здесь, а не во всплывающем окошке: когда человек переключается в WhoKey,
// чтобы ввести мастер-пароль, окошко закрывается. Фоновая часть продолжает ждать
// и, если на сайте один аккаунт, заполнит его сама, как только WhoKey откроется.

const HOST = "ru.edu.whokey";

// Ключ сопряжения с WhoKey лежит в chrome.storage.local. По умолчанию его могут читать и
// скрипты расширения на страницах сайтов (inline.js) — им он не нужен, а взломанная
// вкладка могла бы его достать. Оставляем доступ только страницам самого расширения
chrome.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" }).catch(() => {});

// --- соединение с мостом ---

let port = null;
let pending = []; // ожидающие ответа запросы — мост отвечает по порядку

function connect() {
  if (port) return port;
  port = chrome.runtime.connectNative(HOST);
  port.onMessage.addListener((message) => {
    if (message && message.status === "waiting") {
      // WhoKey закрыт или заблокирован — мост его открыл и ждёт мастер-пароль
      pending.forEach((p) => (p.waited = true));
      chrome.runtime.sendMessage({ kind: "waiting" }).catch(() => {});
      return;
    }
    const first = pending.shift();
    if (first) first.resolve({ ...message, waited: first.waited });
  });
  port.onDisconnect.addListener(() => {
    // «host not found» — мост не прописан: WhoKey ни разу не запускали
    const error = chrome.runtime.lastError ? chrome.runtime.lastError.message : "";
    const status = /not found/i.test(error) ? "not_installed" : "bridge_closed";
    pending.forEach((p) => p.resolve({ status, waited: p.waited }));
    pending = [];
    port = null;
  });
  return port;
}

// Оборвать зависшие запросы и мост. Нужно, когда человек нажал кнопку снова,
// а старый запрос всё ещё ждёт WhoKey (например, WhoKey закрыли, не введя
// мастер-пароль): иначе новый запрос встал бы в очередь за старым и висел.
// Новый мост снова откроет WhoKey.
function reset() {
  if (port) {
    const old = port;
    port = null;
    old.disconnect(); // мост увидит, что браузер ушёл, и завершится
  }
  pending.forEach((p) => p.resolve({ status: "cancelled", waited: p.waited }));
  pending = [];
}

function request(message) {
  return new Promise((resolve) => {
    pending.push({ resolve, waited: false });
    try {
      connect().postMessage(message);
    } catch (e) {
      pending.pop();
      resolve({ status: "bridge_closed" });
    }
  });
}

// Запрос с ключом; при первом подключении — разрешение в WhoKey.
// В WhoKey уходит только адрес сайта (origin), без пути и параметров:
// в них бывают токены, а для проверки сайта больше ничего не нужно.
async function api(message) {
  if (message.url) message = { ...message, url: new URL(message.url).origin };
  const { pairKey } = await chrome.storage.local.get("pairKey");
  let reply = await request({ ...message, key: pairKey || "" });
  if (reply.status !== "pair_required") return reply;
  const waited = reply.waited;
  // код сопряжения: расширение показывает его на своём значке (он виден, даже когда
  // окошко закрылось) и в окошке, а человек вводит его в WhoKey. Чужая программа может
  // попросить доступ со своим кодом, но показать его на нашем значке не может
  const code = String(crypto.getRandomValues(new Uint32Array(1))[0] % 10000).padStart(4, "0");
  chrome.action.setBadgeBackgroundColor({ color: "#936fc4" });
  chrome.action.setBadgeText({ text: code });
  chrome.runtime.sendMessage({ kind: "pairing", code }).catch(() => {});
  const pair = await request({ type: "pair", code });
  chrome.action.setBadgeText({ text: "" });
  if (pair.status !== "ok") return { ...pair, waited: waited || pair.waited };
  await chrome.storage.local.set({ pairKey: pair.key });
  reply = await request({ ...message, key: pair.key });
  return { ...reply, waited: waited || pair.waited || reply.waited };
}

// --- вставка в страницу ---

// Эта функция выполняется ВНУТРИ страницы. Она ничего не знает о WhoKey —
// только получает логин и пароль и находит поля. Вставляет «волной»: буквы
// бегут по очереди (см. type ниже), стиль полей страницы не меняется.
async function fillInPage(expectedOrigin, login, password, auto, useTarget) {
  // Заполняем сами после ожидания WhoKey, а окно браузера сейчас закрыто окном
  // WhoKey (человек только что вводил мастер-пароль). Такая страница для браузера
  // «скрыта», и проверка видимости ниже не нашла бы ни одного поля. Ждём, пока
  // человек вернётся к странице (не дольше 2 минут), и только тогда ищем поля.
  if (auto && document.visibilityState !== "visible") {
    await new Promise((resolve) => {
      const done = () => { document.removeEventListener("visibilitychange", check); resolve(); };
      const check = () => { if (document.visibilityState === "visible") done(); };
      document.addEventListener("visibilitychange", check);
      setTimeout(done, 120000);
    });
    await new Promise((resolve) => requestAnimationFrame(() => resolve())); // дать странице отрисоваться
  }
  // страница успела смениться (перешли на другой сайт) — не заполняем
  if (location.origin !== expectedOrigin) return { ok: false, reason: "moved" };
  // поле должно быть по-настоящему видно человеку: не прозрачное (и не внутри
  // прозрачного родителя), не обрезанное, не за экраном и не под чужим слоем —
  // иначе страница могла бы подставить невидимое поле-ловушку
  const visible = (el) => {
    if (el.disabled || el.readOnly) return false;
    if (el.checkVisibility && !el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return false;
    const box = el.getBoundingClientRect();
    if (box.width < 8 || box.height < 8) return false;
    const style = getComputedStyle(el);
    if (style.color === "transparent" || style.clipPath !== "none") return false;
    const x = box.left + box.width / 2, y = box.top + box.height / 2;
    if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return false; // за пределами окна
    const top = document.elementFromPoint(x, y);
    if (!top || top === el || el.contains(top) || top.tagName === "LABEL") return true;
    // сверху что-то лежит: прячет поле только непрозрачный слой. Прозрачный (или
    // «плавающая» подпись, как на многих сайтах) поле не прячет — человек его видит
    return Number(getComputedStyle(top).opacity) < 0.05;
  };
  const set = (el, value, done = true) => {
    // через «родной» сеттер: иначе React и похожие библиотеки не заметят значение
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    el.focus();
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    // «изменено» — один раз, когда значение готово, а не на каждую букву
    if (done) el.dispatchEvent(new Event("change", { bubbles: true }));
  };
  // Поле, у которого человек нажал на значок WhoKey (inline.js), — только если окошко открыто
  // этим нажатием. Эта функция работает в том же изолированном от сайта мире расширения, что и
  // inline.js, поэтому видит его отметку, а сайт — нет. Ключ — символ: элементом страницы с
  // таким id его не подменить
  const marked = useTarget ? globalThis[Symbol.for("whokey.target")] : null;
  const target = marked instanceof HTMLInputElement ? marked : null;
  // поле могло оказаться ниже экрана — прокрутим к нему, прежде чем проверять видимость
  const focus = target && target.isConnected ? target : document.querySelector("input[type=password]");
  if (focus) focus.scrollIntoView({ block: "center" });
  const inputs = [...document.querySelectorAll("input")].filter(visible);
  const passwords = inputs.filter((el) => el.type === "password");
  // заполняем сами (без выбора человека), только если поле пароля одно — иначе
  // непонятно, какое из них настоящее
  if (auto && passwords.length > 1) return { ok: false, reason: "ambiguous" };
  const isLoginField = (el) => ["text", "email", "tel", ""].includes(el.type)
    || el.autocomplete === "username";
  let passwordField = passwords[0];
  if (target && inputs.includes(target)) {
    // форма того поля, у которого нажали: пароль — это поле или первое поле пароля после него
    const scope = target.form ? inputs.filter((el) => el.form === target.form) : inputs;
    const after = scope.slice(scope.indexOf(target));
    passwordField = target.type === "password" ? target : after.find((el) => el.type === "password");
  }
  let loginField = null;
  if (target && !passwordField && isLoginField(target)) {
    loginField = target; // вход в два шага: сейчас только логин
  } else if (passwordField) {
    // логин — последнее подходящее поле ПЕРЕД паролем (в той же форме, если она есть)
    const scope = passwordField.form ? inputs.filter((el) => el.form === passwordField.form) : inputs;
    const before = scope.slice(0, scope.indexOf(passwordField));
    loginField = before.filter((el) => el.autocomplete === "username").pop() || before.filter(isLoginField).pop();
  } else {
    // вход в два шага (сначала только логин): поле логина без поля пароля
    loginField = inputs.find((el) => el.autocomplete === "username" || el.autocomplete === "email" || el.type === "email")
      || inputs.find((el) => isLoginField(el) && /e-?mail|login|user/i.test(`${el.name} ${el.id}`)) || null;
  }
  if (!passwordField && !loginField) return { ok: false, reason: "no_field" };

  // Анимация «волной»: буквы вписываются по одной. Если в системе включено
  // «Уменьшить движение» — сразу целиком. Стиль полей страницы не меняем:
  // подсветка поверх чужого оформления (свои рамки, скругления, обёртки)
  // на части сайтов выглядела криво.
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const type = async (el, value) => {
    if (calm || !value) return set(el, value);
    // вся строка укладывается примерно в 0,25 с, даже длинный пароль
    const step = Math.max(8, Math.min(35, 250 / value.length));
    for (let i = 1; i <= value.length; i++) {
      if (location.origin !== expectedOrigin) return; // страница сменилась посреди набора — прекращаем
      set(el, value.slice(0, i), i === value.length);
      await sleep(step);
    }
  };
  if (loginField && login) await type(loginField, login);
  if (passwordField) await type(passwordField, password);
  return { ok: true, partial: !passwordField };
}

async function fill(tabId, url, index, login, auto = false, useTarget = false) {
  const reply = await api({ type: "fill", url, index, login });
  if (reply.status !== "ok") return reply;
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId },
      func: fillInPage,
      args: [new URL(url).origin, reply.login, reply.password, auto, useTarget === true],
    });
    const r = result && result.result;
    if (!r) return { status: "no_field" };
    return r.ok ? { status: r.partial ? "filled_login" : "filled" } : { status: r.reason };
  } catch (e) {
    return { status: "moved" }; // вкладку закрыли или перешли на другую страницу
  }
}

// --- запросы от всплывающего окошка ---

async function open(tabId, url, fromIcon = false) {
  if (pending.length) reset(); // прошлое нажатие ещё ждёт — начинаем заново
  const reply = await api({ type: "logins", url });
  if (reply.status === "cancelled") return reply; // это прошлое нажатие — его окошко уже закрыто
  if (reply.status !== "ok") return reply;
  const items = reply.items;
  chrome.action.setBadgeText({ tabId, text: "" });
  if (reply.waited && items.length === 1) {
    // ждали, пока откроется WhoKey (окошко за это время закрылось) — заполняем сами
    const result = await fill(tabId, url, items[0].index, items[0].login, true, fromIcon);
    return { ...result, items };
  }
  if (reply.waited && items.length > 1) {
    // аккаунтов несколько — выбрать может только человек: число на иконке
    chrome.action.setBadgeBackgroundColor({ tabId, color: "#936fc4" });
    chrome.action.setBadgeText({ tabId, text: String(items.length) });
  }
  return { status: "ok", items };
}

// --- значок в поле (inline.js) открывает окошко на панели браузера ---

// Раньше аккаунт выбирали в меню, встроенном в страницу. Сайт мог подделать такое меню или
// спрятать его под своей кнопкой (проверки видимости обходились точным расчётом кадров).
// Окошко на панели — часть самого браузера: страница не может ни нарисовать поверх него,
// ни нажать в нём. Значок только сообщает «человек нажал на меня у такого поля».
//
// Окошко узнаёт о нажатии из этой отметки: она одноразовая и живёт 3 секунды. Только с ней
// окошко заполняет поле, у которого нажали, и предлагает сгенерировать пароль
const ARM_MS = 3000;
const armed = new Map(); // вкладка -> { until, newPassword, origin }

// сайт страницы — чтобы отметка не перешла на другую страницу, если вкладка сразу ушла дальше
function originOf(url) {
  try {
    return new URL(url).origin;
  } catch (e) {
    return null;
  }
}

async function iconClick(sender, newPassword) {
  if (sender.frameId !== 0) return;
  armed.set(sender.tab.id, { until: Date.now() + ARM_MS, newPassword: newPassword === true, origin: originOf(sender.url) });
  try {
    await chrome.action.openPopup({ windowId: sender.tab.windowId });
  } catch (e) {
    armed.delete(sender.tab.id); // окно браузера не в фокусе — окошко не открылось
  }
}

function takeArm(tabId, url) {
  const record = armed.get(tabId);
  armed.delete(tabId);
  if (record === undefined || Date.now() > record.until) return null;
  return record.origin !== null && record.origin === originOf(url) ? record : null;
}

// --- где показывать значок (настройки расширения, options.html) ---

async function inlineAllowed(url) {
  const { inlineEnabled = true, inlineOff = [] } = await chrome.storage.local.get(["inlineEnabled", "inlineOff"]);
  try {
    return inlineEnabled && !inlineOff.includes(new URL(url).hostname);
  } catch (e) {
    return false;
  }
}

async function hideOnSite(tabId, url) {
  const { inlineOff = [] } = await chrome.storage.local.get("inlineOff");
  const host = new URL(url).hostname;
  if (!inlineOff.includes(host)) await chrome.storage.local.set({ inlineOff: [...inlineOff, host].sort() });
  try {
    await chrome.tabs.sendMessage(tabId, { kind: "inline_off" }, { frameId: 0 });
  } catch (e) { /* страницу уже закрыли или перезагрузили */ }
}

// Эта функция выполняется ВНУТРИ страницы: находит поля нового пароля той формы, у которой
// нажали на значок (и «Повторите пароль»), и логин из той же формы. С password — вписывает
// пароль; без него только проверяет, есть ли куда вписывать (до того, как просить WhoKey)
function fillNewPassword(expectedOrigin, password) {
  if (location.origin !== expectedOrigin) return { ok: false, reason: "moved" };
  const marked = globalThis[Symbol.for("whokey.target")];
  const target = marked instanceof HTMLInputElement && marked.isConnected ? marked : null;
  if (!target || target.type !== "password") return { ok: false, reason: "no_field" };
  const shown = (el) => !el.disabled && !el.readOnly
    && (!el.checkVisibility || el.checkVisibility({ opacityProperty: true, visibilityProperty: true }))
    && el.getBoundingClientRect().width >= 8;
  const scope = [...(target.form || document).querySelectorAll("input")].filter(shown);
  const passwords = scope.filter((el) => el.type === "password");
  if (!passwords.includes(target)) return { ok: false, reason: "no_field" }; // поле спрятали
  const hint = (el) => `${el.autocomplete || ""} ${el.name || ""} ${el.id || ""}`.toLowerCase();
  // «текущий / старый пароль» не трогаем никогда
  const current = (el) => /current-password|current|old/.test(hint(el));
  const candidates = passwords.filter((el) => !current(el));
  const newMarked = candidates.filter((el) => /new-password/.test(hint(el)));
  // помеченные сайтом «новый пароль»; иначе пароль + повтор; иначе это поле и следующие
  const fields = newMarked.length ? newMarked
    : candidates.length === 2 ? candidates
      : candidates.slice(Math.max(candidates.indexOf(target), 0));
  if (!fields.length || current(target)) return { ok: false, reason: "no_field" };
  const before = scope.slice(0, scope.indexOf(fields[0]));
  const loginField = before.filter((el) => el.autocomplete === "username").pop()
    || before.filter((el) => ["text", "email", "tel", ""].includes(el.type)).pop();
  const login = loginField ? loginField.value.trim().slice(0, 256) : "";
  if (password === null) return { ok: true, login };
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  for (const el of fields) {
    el.focus();
    setter.call(el, password);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }
  return { ok: true, login };
}

async function inPage(tabId, url, password) {
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId }, func: fillNewPassword, args: [new URL(url).origin, password],
    });
    return result || { ok: false, reason: "no_field" };
  } catch (e) {
    return { ok: false, reason: "moved" };
  }
}

// Порядок важен (ревью безопасности 1.5.1): пароль сначала появляется в WhoKey (окно новой
// записи), и только потом на сайте. Если WhoKey не может открыть окно — пароль не создаётся,
// и на сайт ничего не уходит: пароль не окажется там, где его нигде не записали
async function generate(tabId, url) {
  const form = await inPage(tabId, url, null); // есть ли вообще куда вписывать
  if (!form.ok) return { status: form.reason };
  const reply = await api({ type: "generate", url, login: form.login });
  if (reply.status !== "ok") return reply;
  const result = await inPage(tabId, url, reply.password);
  // не вписалось — в WhoKey пароль уже есть (окно новой записи открыто), его можно скопировать оттуда
  return { status: result.ok ? "generated" : "generated_not_filled" };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false; // только от своих страниц
  if (sender.tab) {
    // значок на странице (inline.js) сообщает только «человек нажал на меня»
    // и спрашивает, показываться ли на этом сайте. Больше вкладка ничего попросить не может
    if (sender.frameId !== 0 || !sender.url || sender.url.startsWith("chrome-extension://")) return false;
    if (message.kind === "icon_click") iconClick(sender, message.newPassword);
    if (message.kind === "inline_state") {
      inlineAllowed(sender.tab.url).then((show) => sendResponse({ show }));
      return true;
    }
    return false;
  }
  // дальше — всплывающее окошко с панели браузера (у него нет вкладки)
  if (message.kind === "open") {
    // окошко открыто нажатием на значок в поле — заполнять то поле, а на форме нового
    // пароля предложить сгенерировать его
    const ticket = takeArm(message.tabId, message.url);
    open(message.tabId, message.url, ticket !== null).then((reply) => sendResponse({
      ...reply, fromIcon: ticket !== null, newPassword: ticket !== null && ticket.newPassword }));
    return true; // ответ придёт позже
  }
  if (message.kind === "fill") {
    fill(message.tabId, message.url, message.index, message.login, false, message.useTarget === true).then(sendResponse);
    return true;
  }
  if (message.kind === "generate") {
    generate(message.tabId, message.url).then(sendResponse);
    return true;
  }
  if (message.kind === "hide_site") {
    hideOnSite(message.tabId, message.url).then(() => sendResponse({ status: "ok" }));
    return true;
  }
  if (message.kind === "show") {
    // «Добавить в WhoKey»: WhoKey откроет новую запись с адресом этого сайта
    api({ type: "show", url: message.url }).then(sendResponse);
    return true;
  }
  return false;
});
