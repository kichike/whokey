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
  cancelled: ["connecting", ""],
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

function showResult(reply, host) {
  const [key, kind] = TEXTS[reply.status] || ["error", "bad"];
  status(msg(key, key === "ambiguous" ? shortcut : host), kind);
  if (reply.status === "filled" || reply.status === "filled_login") setTimeout(() => window.close(), 700);
}

function showItems(tab, url, host, items) {
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
    const num = document.createElement("span");
    num.className = "num";
    num.textContent = n < 9 ? String(n + 1) : "";
    const login = document.createElement("span");
    login.className = "login";
    login.textContent = item.login || "—";       // textContent, не innerHTML: данные из хранилища не исполняются
    const site = document.createElement("span");
    site.className = "site";
    site.textContent = item.site;
    button.append(num, login, site);
    button.addEventListener("click", async () => {
      list.querySelectorAll("button").forEach((b) => (b.disabled = true));
      status(msg("filling"));
      showResult(await chrome.runtime.sendMessage({ kind: "fill", tabId: tab.id, url, index: item.index, login: item.login }), host);
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
    if (n >= 1 && n <= items.length) buttons[n - 1].click();
  });
}

async function main() {
  document.documentElement.lang = chrome.i18n.getUILanguage();
  shortcut = await loadShortcut();
  $("hint").textContent = msg("hint", shortcut);
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
  if (reply.status === "ok") showItems(tab, url, host, reply.items);
  else showResult(reply, host);
}

main();
