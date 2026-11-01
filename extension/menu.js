// Меню под полем пароля: страница самого расширения во фрейме на сайте.
// Сайт не может заглянуть внутрь (другой источник) — список логинов видит только человек.
// Сюда не приходит ни одного пароля: их вставляет фоновая часть после выбора аккаунта.

const $ = (id) => document.getElementById(id);
const msg = (key, ...subs) => chrome.i18n.getMessage(key, subs) || key;
const send = (message) => chrome.runtime.sendMessage(message);

document.documentElement.lang = chrome.i18n.getUILanguage();

// Защита от «невидимых» нажатий: сайт может сделать фрейм прозрачным или накрыть его
// своей картинкой и подсунуть человеку кнопку «Продолжить» ровно над аккаунтом.
// Браузер сообщает, видно ли фрейм по-настоящему (IntersectionObserver v2), —
// нажатия принимаем, только если меню честно видно хотя бы полсекунды.
let visibleSince = null;
let trackingWorks = false;
try {
  new IntersectionObserver((entries) => {
    const entry = entries[entries.length - 1];
    if (!("isVisible" in entry)) return;
    trackingWorks = true;
    visibleSince = entry.isVisible ? visibleSince || performance.now() : null;
  }, { trackVisibility: true, delay: 100, threshold: [1.0] }).observe($("menu"));
} catch (e) { /* старый браузер без проверки видимости */ }

// меню сдвинули — снова ждём полсекунды видимости (см. placeMenu в inline.js).
// Сообщение может прислать и сама страница, но оно только откладывает нажатия
addEventListener("message", () => {
  if (visibleSince !== null) visibleSince = performance.now();
  movedAt = performance.now();
});
let movedAt = -Infinity;

function trustedClick(event) {
  if (performance.now() - movedAt < 500) return false;
  if (!event.isTrusted) return false;
  if (!trackingWorks) return event.detail === 0 || performance.now() > 500; // Enter с клавиатуры — detail 0
  return visibleSince !== null && performance.now() - visibleSince >= 500;
}

// высоту меню знает только оно само — сообщаем странице, какой сделать фрейм
function resize() {
  // высота содержимого, а не документа: документ не бывает ниже самого фрейма
  send({ kind: "menu_size", height: Math.ceil($("menu").scrollHeight) });
}

const TEXTS = {
  filled: ["filled", "good"], filled_login: ["filled_login", "good"], no_field: ["no_field", "bad"],
  moved: ["moved", "bad"], denied: ["denied", "bad"], locked: ["locked", "bad"],
  not_installed: ["not_installed", "bad"], bridge_closed: ["bridge_closed", "bad"], bad_page: ["bad_page", "bad"],
  not_found: ["not_found", "bad"], error: ["error", "bad"], busy: ["busy", "bad"], timeout: ["timeout", "bad"],
  fake_app: ["fake_app", "bad"], ambiguous: ["choose", ""], cancelled: ["connecting", ""],
  generated: ["generated", "good"],
};

function status(text, kind = "") {
  $("status").textContent = text;
  $("status").className = kind;
  $("code").hidden = true;
  resize();
}

let pageHost = "";   // сайт, на котором открыто меню (сообщает фоновая часть)
let pageUrl = "";    // адрес страницы без параметров — по нему браузер помнит значок

// Значок сайта — из хранилища значков самого браузера (разрешение "favicon"): без запросов
// в интернет, никакой сервер не узнаёт, на какие сайты вы заходите. Если браузер значка
// не знает, он отдаёт стандартный «глобус» — тогда лучше оставить первую букву названия.
const favicon = (page) => new Promise((resolve) => {
  const img = new Image(32, 32);
  img.alt = "";
  img.onload = () => resolve(img);
  img.onerror = () => resolve(null);
  img.src = chrome.runtime.getURL(`/_favicon/?pageUrl=${encodeURIComponent(page)}&size=32`);
});

function pixels(img) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 32;
  const context = canvas.getContext("2d");
  context.drawImage(img, 0, 0, 32, 32);
  return context.getImageData(0, 0, 32, 32).data.join(",");
}

// Светлый значок (белый кот GitHub в тёмной теме) на белой плашке не виден —
// для него плашка тёмная. Светлый — если средняя яркость видимых точек высокая
function isLight(img) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 32;
  const context = canvas.getContext("2d");
  context.drawImage(img, 0, 0, 32, 32);
  const data = context.getImageData(0, 0, 32, 32).data;
  let sum = 0, count = 0;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 128) continue; // прозрачные точки не считаем
    sum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    count++;
  }
  return count > 0 && sum / count > 170;
}

let iconPromise = null; // один значок на всё меню: все аккаунты в нём — с одного сайта

function loadSiteIcon() {
  iconPromise = iconPromise || (async () => {
    if (!pageUrl) return null;
    // глобус — то, что браузер отдаёт для сайта, где никто не бывал (.invalid не существует)
    const globe = await favicon("https://whokey.invalid/");
    const isGlobe = (img) => !img || (globe && pixels(img) === pixels(globe));
    // сначала значок этой страницы, потом — главной страницы сайта
    for (const page of [pageUrl, new URL(pageUrl).origin + "/"]) {
      const icon = await favicon(page);
      if (!isGlobe(icon)) return { src: icon.src, light: isLight(icon) };
    }
    return null;
  })();
  return iconPromise;
}

async function siteIcon(avatar) {
  const icon = await loadSiteIcon();
  if (!icon) return;
  const img = new Image(32, 32);
  img.alt = "";
  img.src = icon.src;
  avatar.textContent = "";
  avatar.classList.add("icon", icon.light ? "light" : "dark");
  avatar.append(img);
}

function showResult(reply) {
  const [key, kind] = TEXTS[reply.status] || ["error", "bad"];
  // «откройте окошко ещё раз» — про окошко на панели; в меню аккаунт выбирают заново
  status(msg(key === "not_found" ? "menu_not_found" : key, pageHost), kind);
  // не получилось — аккаунты снова можно выбрать («нажмите ещё раз»)
  document.querySelectorAll("#items button").forEach((b) => (b.disabled = false));
  if (reply.status === "filled" || reply.status === "filled_login") setTimeout(() => send({ kind: "menu_close" }), 600);
}

function showItems(items, host) {
  const list = $("items");
  list.textContent = "";
  if (!items.length) {
    status(msg("no_entries", host));
    const add = $("add");
    add.textContent = msg("add_entry");
    add.hidden = false;
    add.onclick = async (event) => {
      if (!trustedClick(event)) return;
      add.disabled = true;
      const reply = await send({ kind: "menu_show" });
      if (reply.status !== "ok") showResult(reply);
    };
    resize();
    return;
  }
  status("");
  for (const item of items) {
    const button = document.createElement("button");
    const avatar = document.createElement("span");
    avatar.className = "avatar";
    avatar.textContent = (item.site || "?").trim().charAt(0).toUpperCase();
    siteIcon(avatar);
    const text = document.createElement("span");
    text.className = "text";
    const site = document.createElement("span");
    site.className = "site";
    site.textContent = item.site;                 // textContent: данные из хранилища не исполняются
    const login = document.createElement("span");
    login.className = "login";
    login.textContent = item.login || "—";
    text.append(site, login);
    button.append(avatar, text);
    button.addEventListener("click", async (event) => {
      if (!trustedClick(event)) return;
      list.querySelectorAll("button").forEach((b) => (b.disabled = true));
      status(msg("filling"));
      showResult(await send({ kind: "menu_fill", index: item.index, login: item.login }));
    });
    const li = document.createElement("li");
    li.append(button);
    list.append(li);
  }
  resize();
}

document.addEventListener("keydown", (event) => {
  const buttons = [...document.querySelectorAll("button:not([hidden])")];
  if (event.key === "Escape") send({ kind: "menu_close" });
  if ((event.key === "ArrowDown" || event.key === "ArrowUp") && buttons.length) {
    event.preventDefault();
    const now = buttons.indexOf(document.activeElement);
    const step = event.key === "ArrowDown" ? 1 : -1;
    buttons[(now + step + buttons.length) % buttons.length].focus();
  }
});

// ↓ в поле страницы переводит сюда фокус (inline.js) — сразу на первый аккаунт
addEventListener("focus", () => {
  const first = document.querySelector("button:not([hidden]):not(:disabled)");
  if (first && !document.activeElement.matches("button")) first.focus();
});

chrome.runtime.onMessage.addListener((message) => {
  if (message.kind === "waiting") status(msg("waiting"));
  if (message.kind === "pairing") {
    status(msg("pairing"), "good");
    $("code").textContent = message.code;
    $("code").hidden = false;
    resize();
  }
});

async function main() {
  status(msg("connecting"));
  const reply = await send({ kind: "menu_open" });
  pageHost = reply.host || "";
  pageUrl = reply.page || "";
  if (reply.status !== "ok") return showResult(reply);
  if (reply.newPassword) showGenerate();
  showItems(reply.items, pageHost);
  showHideSite();
}

// форма регистрации или смены пароля: новый пароль генерирует WhoKey, расширение
// вписывает его в форму, а WhoKey сразу открывает новую запись — пароль не потеряется
function showGenerate() {
  const button = $("generate");
  button.textContent = msg("generate_password");
  button.hidden = false;
  button.onclick = async (event) => {
    if (!trustedClick(event)) return;
    button.disabled = true;
    status(msg("filling"));
    const reply = await send({ kind: "menu_generate" });
    button.disabled = false;
    showResult(reply);
  };
}

// «Не показывать на этом сайте» — значок пропадает сразу; вернуть — в настройках расширения
function showHideSite() {
  const button = $("hide_site");
  button.textContent = msg("hide_on_site");
  button.hidden = false;
  button.onclick = (event) => {
    if (trustedClick(event)) send({ kind: "menu_hide_site" });
  };
}

main();
