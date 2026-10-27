// Фоновая часть расширения WhoKey: разговаривает с мостом (native messaging)
// и вставляет логин и пароль в страницу.
//
// Почему здесь, а не во всплывающем окошке: когда человек переключается в WhoKey,
// чтобы ввести мастер-пароль, окошко закрывается. Фоновая часть продолжает ждать
// и, если на сайте один аккаунт, заполнит его сама, как только WhoKey откроется.

const HOST = "ru.edu.whokey";

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
  // код сопряжения: окошко и WhoKey показывают одни и те же 4 цифры — человек сверяет,
  // что разрешение просит именно это расширение, а не чужая программа
  const code = String(crypto.getRandomValues(new Uint32Array(1))[0] % 10000).padStart(4, "0");
  chrome.runtime.sendMessage({ kind: "pairing", code }).catch(() => {});
  const pair = await request({ type: "pair", code });
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
  // поле могло оказаться ниже экрана — прокрутим к нему, прежде чем проверять видимость
  const firstPassword = document.querySelector("input[type=password]");
  if (firstPassword) firstPassword.scrollIntoView({ block: "center" });
  const inputs = [...document.querySelectorAll("input")].filter(visible);
  const passwords = inputs.filter((el) => el.type === "password");
  // заполняем сами (без выбора человека), только если поле пароля одно — иначе
  // непонятно, какое из них настоящее
  if (auto && passwords.length > 1) return { ok: false, reason: "ambiguous" };
  const passwordField = passwords[0];
  const isLoginField = (el) => ["text", "email", "tel", ""].includes(el.type)
    || el.autocomplete === "username";
  let loginField = null;
  if (passwordField) {
    // логин — последнее подходящее поле ПЕРЕД паролем (в той же форме, если она есть)
    const scope = passwordField.form ? inputs.filter((el) => el.form === passwordField.form) : inputs;
    const before = scope.slice(0, scope.indexOf(passwordField));
    loginField = before.filter((el) => el.autocomplete === "username").pop() || before.filter(isLoginField).pop();
  } else {
    // вход в два шага (сначала только логин): поле логина без поля пароля
    loginField = inputs.find((el) => el.autocomplete === "username" || el.type === "email") || null;
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

// --- запросы от всплывающего окошка ---

async function open(tabId, url) {
  if (pending.length) reset(); // прошлое нажатие ещё ждёт — начинаем заново
  const reply = await api({ type: "logins", url });
  if (reply.status === "cancelled") return reply; // это прошлое нажатие — его окошко уже закрыто
  if (reply.status !== "ok") return reply;
  const items = reply.items;
  chrome.action.setBadgeText({ tabId, text: "" });
  if (reply.waited && items.length === 1) {
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

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false; // только от своего окошка
  if (message.kind === "open") {
    open(message.tabId, message.url).then(sendResponse);
    return true; // ответ придёт позже
  }
  if (message.kind === "fill") {
    fill(message.tabId, message.url, message.index, message.login).then(sendResponse);
    return true;
  }
  return false;
});
