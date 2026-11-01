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

function trustedClick(event) {
  if (!event.isTrusted) return false;
  if (!trackingWorks) return event.detail === 0 || performance.now() > 500; // Enter с клавиатуры — detail 0
  return visibleSince !== null && performance.now() - visibleSince >= 500;
}

// высоту меню знает только оно само — сообщаем странице, какой сделать фрейм
function resize() {
  // высота содержимого, а не документа: документ не бывает ниже самого фрейма
  send({ kind: "menu_size", height: Math.ceil($("menu").getBoundingClientRect().height) });
}

const TEXTS = {
  filled: ["filled", "good"], filled_login: ["filled_login", "good"], no_field: ["no_field", "bad"],
  moved: ["moved", "bad"], denied: ["denied", "bad"], locked: ["locked", "bad"],
  not_installed: ["not_installed", "bad"], bridge_closed: ["bridge_closed", "bad"], bad_page: ["bad_page", "bad"],
  not_found: ["not_found", "bad"], error: ["error", "bad"], busy: ["busy", "bad"], timeout: ["timeout", "bad"],
  fake_app: ["fake_app", "bad"], ambiguous: ["choose", ""], cancelled: ["connecting", ""],
};

function status(text, kind = "") {
  $("status").textContent = text;
  $("status").className = kind;
  $("code").hidden = true;
  resize();
}

let pageHost = ""; // сайт, на котором открыто меню (сообщает фоновая часть)

function showResult(reply) {
  const [key, kind] = TEXTS[reply.status] || ["error", "bad"];
  status(msg(key, pageHost), kind);
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
  if (reply.status === "ok") showItems(reply.items, pageHost);
  else showResult(reply);
}

main();
