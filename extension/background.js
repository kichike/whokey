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
async function fillInPage(expectedOrigin, login, password, auto) {
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
  // Поле, у которого человек нажал на значок WhoKey (inline.js). Эта функция работает в том
  // же изолированном от сайта мире расширения, что и inline.js, поэтому видит его отметку,
  // а сайт — нет. Отметка одноразовая
  const target = globalThis.__whokeyTarget;
  globalThis.__whokeyTarget = null;
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

async function fill(tabId, url, index, login, auto = false) {
  const reply = await api({ type: "fill", url, index, login });
  if (reply.status !== "ok") return reply;
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId },
      func: fillInPage,
      args: [new URL(url).origin, reply.login, reply.password, auto],
    });
    const r = result && result.result;
    if (!r) return { status: "no_field" };
    return r.ok ? { status: r.partial ? "filled_login" : "filled" } : { status: r.reason };
  } catch (e) {
    return { status: "moved" }; // вкладку закрыли или перешли на другую страницу
  }
}

// --- запросы от всплывающего окошка и меню на странице ---

async function open(tabId, url, fromMenu = false) {
  if (pending.length) reset(); // прошлое нажатие ещё ждёт — начинаем заново
  const reply = await api({ type: "logins", url });
  if (reply.status === "cancelled") return reply; // это прошлое нажатие — его окошко уже закрыто
  if (reply.status !== "ok") return reply;
  const items = reply.items;
  chrome.action.setBadgeText({ tabId, text: "" });
  // из меню на странице — никогда сами: человек выберет аккаунт в меню, оно остаётся открытым
  if (reply.waited && items.length === 1 && !fromMenu) {
    // ждали, пока откроется WhoKey (окошко за это время закрылось) — заполняем сами
    const result = await fill(tabId, url, items[0].index, items[0].login, true);
    return { ...result, items };
  }
  if (reply.waited && items.length > 1) {
    // аккаунтов несколько — выбрать может только человек: число на иконке
    chrome.action.setBadgeBackgroundColor({ tabId, color: "#936fc4" });
    chrome.action.setBadgeText({ tabId, text: String(items.length) });
  }
  return { status: "ok", items };
}

// --- меню под полем пароля (inline.js рисует значок, menu.html — само меню) ---

// Меню встроено в страницу по «одноразовому» адресу (use_dynamic_url в manifest.json):
// он меняется в каждом сеансе браузера, так что сайт не может встроить меню сам.
// Поэтому узнаём меню не по полному адресу, а так: это страница нашего расширения
// (sender.id проверен выше) с путём /menu.html
function isMenu(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "chrome-extension:" && parsed.pathname === "/menu.html";
  } catch (e) {
    return false;
  }
}

// Меню можно открыть только сразу после настоящего нажатия на значок WhoKey в поле.
// Без этого любой сайт (или реклама на нём) мог бы встроить невидимое меню и без
// единого нажатия открывать WhoKey, просить мастер-пароль и запускать сопряжение.
// Значок (inline.js, сама страница — кадр 0) сообщает о нажатии; разрешение одноразовое
// и живёт 3 секунды.
const ARM_MS = 3000;
const armed = new Map(); // вкладка -> до какого момента можно открыть меню

function arm(sender, newPassword) {
  if (sender.frameId !== 0 || sender.url.startsWith("chrome-extension://")) return;
  armed.set(sender.tab.id, { until: Date.now() + ARM_MS, newPassword: newPassword === true });
}

function takeArm(tabId) {
  const record = armed.get(tabId);
  armed.delete(tabId);
  return record !== undefined && Date.now() <= record.until ? record : null;
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
  await menuCommand(tabId, "inline_off");
}

// Эта функция выполняется ВНУТРИ страницы: вписывает сгенерированный пароль в поля
// нового пароля той формы, у которой нажали на значок (и в «Повторите пароль»).
// Возвращает логин из той же формы — чтобы WhoKey открыл запись уже с ним
function fillNewPassword(expectedOrigin, password) {
  const target = globalThis.__whokeyTarget;
  globalThis.__whokeyTarget = null;
  if (location.origin !== expectedOrigin) return { ok: false, reason: "moved" };
  if (!target || !target.isConnected || target.type !== "password") return { ok: false, reason: "no_field" };
  const shown = (el) => !el.disabled && !el.readOnly
    && (!el.checkVisibility || el.checkVisibility({ opacityProperty: true, visibilityProperty: true }))
    && el.getBoundingClientRect().width >= 8;
  const scope = [...(target.form || document).querySelectorAll("input")].filter(shown);
  const passwords = scope.filter((el) => el.type === "password");
  const marked = passwords.filter((el) => (el.autocomplete || "").toLowerCase() === "new-password");
  // помеченные сайтом «новый пароль»; иначе пароль + повтор; иначе это поле и следующие
  // (в «старый, новый, повтор» старый не трогаем)
  const fields = marked.length ? marked
    : passwords.length === 2 ? passwords : passwords.slice(passwords.indexOf(target));
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  for (const el of fields) {
    el.focus();
    setter.call(el, password);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }
  const before = scope.slice(0, scope.indexOf(fields[0]));
  const login = before.filter((el) => el.autocomplete === "username").pop()
    || before.filter((el) => ["text", "email", "tel", ""].includes(el.type)).pop();
  return { ok: true, login: login ? login.value.trim().slice(0, 256) : "" };
}

async function generate(tabId, url) {
  const reply = await api({ type: "generate", url });
  if (reply.status !== "ok") return reply;
  await menuCommand(tabId, "menu_hide");
  let result;
  try {
    [{ result }] = await chrome.scripting.executeScript({
      target: { tabId }, func: fillNewPassword, args: [new URL(url).origin, reply.password],
    });
  } catch (e) {
    result = { ok: false, reason: "moved" };
  }
  if (!result || !result.ok) {
    await menuCommand(tabId, "menu_unhide");
    return { status: (result && result.reason) || "no_field" };
  }
  // пароль уже в форме — сразу сохраняем его в WhoKey (окно новой записи), чтобы не потерять
  await closeMenu(tabId);
  const saved = await api({ type: "show", url, login: result.login, password: reply.password });
  return { status: saved.status === "ok" ? "generated" : saved.status };
}

// Команда меню на вкладке: menu_close — закрыть, menu_hide / menu_unhide — спрятать и
// показать снова. Ждём ответа: прежде чем заполнять, меню должно исчезнуть — иначе
// проверка «поле видно человеку» в fillInPage решила бы, что поле чем-то закрыто
async function menuCommand(tabId, kind) {
  try {
    await chrome.tabs.sendMessage(tabId, { kind }, { frameId: 0 });
  } catch (e) { /* страницу уже закрыли или перезагрузили */ }
}
const closeMenu = (tabId) => menuCommand(tabId, "menu_close");

function fromMenu(message, sender, sendResponse) {
  // вкладку и адрес страницы сообщает сам браузер (sender), а не страница:
  // сайт не может попросить пароль «от имени» другого сайта
  const tabId = sender.tab.id;
  const url = sender.tab.url;
  if (message.kind === "menu_open") {
    const ticket = takeArm(tabId);
    if (!ticket) {
      sendResponse({ status: "error" }); // меню не после нажатия на значок — не открываем
      return false;
    }
    const page = new URL(url);
    // адрес страницы целиком — только для значка сайта: браузер помнит значки по страницам.
    // Меню — страница самого расширения, сайт его не прочитает
    open(tabId, url, true).then((reply) => sendResponse({
      ...reply, host: page.hostname, page: page.origin + page.pathname, newPassword: ticket.newPassword }));
    return true;
  }
  if (message.kind === "menu_generate") {
    generate(tabId, url).then(sendResponse);
    return true;
  }
  if (message.kind === "menu_hide_site") {
    hideOnSite(tabId, url).then(() => sendResponse({ status: "ok" }));
    return true;
  }
  if (message.kind === "menu_fill") {
    // на время вставки меню прячем; получилось — закрываем, нет — показываем снова
    // с объяснением, и аккаунт можно выбрать ещё раз
    menuCommand(tabId, "menu_hide")
      .then(() => fill(tabId, url, message.index, message.login))
      .then(async (reply) => {
        const done = reply.status === "filled" || reply.status === "filled_login";
        if (!done) await menuCommand(tabId, "menu_unhide");
        sendResponse(reply);
      });
    return true;
  }
  if (message.kind === "menu_show") {
    api({ type: "show", url }).then((reply) => {
      if (reply.status === "ok") closeMenu(tabId);
      sendResponse(reply);
    });
    return true;
  }
  if (message.kind === "menu_size" || message.kind === "menu_close") {
    chrome.tabs.sendMessage(tabId, message, { frameId: 0 }).catch(() => {});
  }
  return false;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false; // только от своих страниц
  if (sender.tab) {
    if (!sender.url) return false;
    // значок на странице (inline.js) сообщает только «человек нажал на меня»
    // и спрашивает, показываться ли на этом сайте
    if (message.kind === "menu_armed") {
      arm(sender, message.newPassword);
      return false;
    }
    if (message.kind === "inline_state" && sender.frameId === 0 && !isMenu(sender.url)) {
      inlineAllowed(sender.tab.url).then((show) => sendResponse({ show }));
      return true;
    }
    // всё остальное с вкладки — только от меню (menu.html внутри страницы)
    if (!isMenu(sender.url)) return false;
    return fromMenu(message, sender, sendResponse);
  }
  // дальше — всплывающее окошко с панели браузера (у него нет вкладки)
  if (message.kind === "open") {
    open(message.tabId, message.url).then(sendResponse);
    return true; // ответ придёт позже
  }
  if (message.kind === "fill") {
    fill(message.tabId, message.url, message.index, message.login).then(sendResponse);
    return true;
  }
  if (message.kind === "show") {
    // «Добавить в WhoKey»: WhoKey откроет новую запись с адресом этого сайта
    api({ type: "show", url: message.url }).then(sendResponse);
    return true;
  }
  return false;
});
