// Всплывающее окошко: список аккаунтов для открытого сайта и кнопка «заполнить».
// Сами запросы к WhoKey делает фоновая часть (background.js).

const $ = (id) => document.getElementById(id);
const msg = (key, ...subs) => chrome.i18n.getMessage(key, subs) || key;

function status(text, kind = "") {
  $("status").textContent = text;
  $("status").className = kind;
  $("code").hidden = true;
  // подсказка про горячую клавишу — только когда всё в порядке, под ошибкой она лишняя
  $("hint").hidden = kind === "bad";
}

// Что сказать человеку по ответу фоновой части
const TEXTS = {
  filled: ["filled", "good"],
  filled_login: ["filled_login", "good"],
  no_field: ["no_field", "bad"],
  moved: ["moved", "bad"],
  denied: ["denied", "bad"],
  locked: ["locked", "bad"],
  not_installed: ["not_installed", "bad"],
  bridge_closed: ["bridge_closed", "bad"],
  bad_page: ["bad_page", "bad"],
  not_found: ["not_found", "bad"],
  error: ["error", "bad"],
  busy: ["busy", "bad"],
  timeout: ["timeout", "bad"],
  fake_app: ["fake_app", "bad"],
  ambiguous: ["ambiguous", "bad"],
  window_busy: ["window_busy", "bad"],
  cancelled: ["connecting", ""],
  generated: ["generated", "good"],
  generated_not_filled: ["generated_not_filled", "bad"],
};

// Горячая клавиша окошка так, как её показывает сам браузер на этой системе
// (⇧⌘L на Mac, Ctrl+Shift+L на Windows; человек мог назначить и свою)
let shortcut = "";

async function loadShortcut() {
  try {
    const commands = await chrome.commands.getAll();
    const action = commands.find((c) => c.name === "_execute_action");
    if (action && action.shortcut) return action.shortcut;
  } catch (e) { /* нет доступа к списку — подставим обычную */ }
  const { os } = await chrome.runtime.getPlatformInfo();
  return os === "mac" ? "⌘⇧L" : "Ctrl+Shift+L";
}

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
  return context.getImageData(0, 0, 32, 32).data;
}

// Светлый значок (белый кот GitHub в тёмной теме) на белой плашке не виден —
// для него плашка тёмная. Светлый — если средняя яркость видимых точек высокая
function isLight(img) {
  const data = pixels(img);
  let sum = 0, count = 0;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 128) continue; // прозрачные точки не считаем
    sum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    count++;
  }
  return count > 0 && sum / count > 170;
}

let iconPromise = null; // один значок на всё окошко: все аккаунты в нём — с одного сайта

function loadSiteIcon(url) {
  iconPromise = iconPromise || (async () => {
    // глобус — то, что браузер отдаёт для сайта, где никто не бывал (.invalid не существует)
    const globe = await favicon("https://whokey.invalid/");
    const isGlobe = (img) => !img || (globe && pixels(img).join(",") === pixels(globe).join(","));
    // адрес страницы без параметров — браузер помнит значки по страницам; потом главная сайта
    const page = new URL(url);
    for (const address of [page.origin + page.pathname, page.origin + "/"]) {
      const icon = await favicon(address);
      if (!isGlobe(icon)) return { src: icon.src, light: isLight(icon) };
    }
    return null;
  })().catch(() => null);
  return iconPromise;
}

async function siteIcon(avatar, url) {
  const icon = await loadSiteIcon(url);
  if (!icon) return;
  const img = new Image(32, 32);
  img.alt = "";
  img.src = icon.src;
  avatar.textContent = "";
  avatar.classList.add("icon", icon.light ? "light" : "dark");
  avatar.append(img);
}

function showResult(reply, host) {
  const [key, kind] = TEXTS[reply.status] || ["error", "bad"];
  status(msg(key, key === "ambiguous" ? shortcut : host), kind);
  if (reply.status === "filled" || reply.status === "filled_login") setTimeout(() => window.close(), 700);
}

function showItems(tab, url, host, items, fromIcon) {
  const list = $("items");
  list.textContent = "";
  if (!items.length) {
    status(msg("no_entries", host));
    const add = $("add");
    add.textContent = msg("add_entry");
    add.hidden = false;
    add.addEventListener("click", async () => {
      add.disabled = true;
      const reply = await chrome.runtime.sendMessage({ kind: "show", url });
      if (reply.status === "ok") window.close(); // дальше — в окне WhoKey
      else showResult(reply, host);
    });
    add.focus();
    return;
  }
  status(msg("choose"));
  items.forEach((item, n) => {
    const button = document.createElement("button");
    const avatar = document.createElement("span");
    avatar.className = "avatar";                 // буква-кружок, как в окне WhoKey; потом — значок сайта
    avatar.textContent = (item.site || "?").trim().charAt(0).toUpperCase();
    siteIcon(avatar, url);
    const text = document.createElement("span");
    text.className = "text";
    const login = document.createElement("span");
    login.className = "login";
    login.textContent = item.login || "—";       // textContent, не innerHTML: данные из хранилища не исполняются
    const site = document.createElement("span");
    site.className = "site";
    site.textContent = item.site;
    text.append(login, site);
    button.append(avatar, text);
    if (n < 9) {
      const num = document.createElement("span");
      num.className = "keycap";                  // цифра — нажмите её, чтобы выбрать сразу
      num.textContent = String(n + 1);
      button.append(num);
    }
    button.addEventListener("click", async () => {
      list.querySelectorAll("button").forEach((b) => (b.disabled = true));
      status(msg("filling"));
      // открыли нажатием на значок в поле — заполняется форма того поля
      const reply = await chrome.runtime.sendMessage({
        kind: "fill", tabId: tab.id, url, index: item.index, login: item.login, useTarget: fromIcon });
      showResult(reply, host);
      if (reply.status !== "filled" && reply.status !== "filled_login") {
        list.querySelectorAll("button").forEach((b) => (b.disabled = false)); // можно выбрать ещё раз
      }
    });
    const li = document.createElement("li");
    li.append(button);
    list.append(li);
  });
  list.querySelector("button").focus(); // Enter — первый аккаунт
  document.addEventListener("keydown", (event) => {
    const buttons = [...list.querySelectorAll("button")];
    // ↑ ↓ — по списку аккаунтов (по кругу), цифры 1–9 — сразу нужный
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      const now = buttons.indexOf(document.activeElement);
      buttons[(now + step + buttons.length) % buttons.length].focus();
      return;
    }
    const n = Number(event.key);
    if (n >= 1 && n <= Math.min(items.length, 9)) buttons[n - 1].click();
  });
}

// форма регистрации или смены пароля (окошко открыто значком в поле нового пароля):
// новый пароль генерирует WhoKey, расширение вписывает его в форму, а WhoKey сразу
// открывает новую запись — пароль не потеряется
function showGenerate(tab, url, host) {
  const button = $("generate");
  button.textContent = msg("generate_password");
  button.hidden = false;
  button.addEventListener("click", async () => {
    button.disabled = true;
    status(msg("filling"));
    const reply = await chrome.runtime.sendMessage({ kind: "generate", tabId: tab.id, url });
    button.disabled = false;
    showResult(reply, host);
  });
}

// «Не показывать на этом сайте» — значок в полях пропадает сразу; вернуть — в настройках
function showHideSite(tab, url) {
  const button = $("hide_site");
  button.textContent = msg("hide_on_site");
  button.hidden = false;
  button.addEventListener("click", async () => {
    await chrome.runtime.sendMessage({ kind: "hide_site", tabId: tab.id, url });
    window.close();
  });
}

async function main() {
  document.documentElement.lang = chrome.i18n.getUILanguage();
  shortcut = await loadShortcut();
  $("keys").textContent = shortcut;
  $("hint_text").textContent = msg("hint_short");
  $("options").textContent = msg("settings_link");
  $("options").addEventListener("click", (event) => { event.preventDefault(); chrome.runtime.openOptionsPage(); });
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab && tab.url ? tab.url : "";
  let host = "";
  try {
    const parsed = new URL(url);
    host = parsed.hostname;
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname);
    if (parsed.protocol !== "https:" && !(parsed.protocol === "http:" && local)) {
      // http — сайт без защиты; chrome://, новая вкладка, файл — вовсе не сайт
      status(msg(parsed.protocol === "http:" ? "bad_page" : "not_a_site"), "bad");
      return;
    }
  } catch (e) {
    status(msg("not_a_site"), "bad");
    return;
  }
  $("host").textContent = host;
  status(msg("connecting"));
  chrome.runtime.onMessage.addListener((message) => {
    if (message.kind === "waiting") status(msg("waiting"));
    if (message.kind === "pairing") {
      status(msg("pairing"), "good");
      $("code").textContent = message.code; // крупно — его вводят в окне WhoKey
      $("code").hidden = false;
    }
  });
  const reply = await chrome.runtime.sendMessage({ kind: "open", tabId: tab.id, url });
  if (reply.status !== "ok") return showResult(reply, host);
  // кнопки — до списка: список ставит фокус на первый аккаунт, а без аккаунтов — на «Добавить»
  if (reply.newPassword) showGenerate(tab, url, host);
  if (reply.fromIcon) showHideSite(tab, url);
  showItems(tab, url, host, reply.items, reply.fromIcon === true);
}

main();
