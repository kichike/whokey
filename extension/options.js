// Настройки расширения: показывать ли значок WhoKey в полях входа — везде и на отдельных сайтах.
// Хранятся в chrome.storage.local (их читает фоновая часть, см. inlineAllowed в background.js)

const $ = (id) => document.getElementById(id);
const msg = (key) => chrome.i18n.getMessage(key) || key;

document.documentElement.lang = chrome.i18n.getUILanguage();
$("title").textContent = msg("options_title");
$("inline_label").textContent = msg("options_inline");
$("inline_hint").textContent = msg("options_inline_hint");
$("off_title").textContent = msg("options_off_sites");

async function render() {
  const { inlineEnabled = true, inlineOff = [] } = await chrome.storage.local.get(["inlineEnabled", "inlineOff"]);
  $("inline").checked = inlineEnabled;
  $("inline_hint").hidden = inlineEnabled;
  const list = $("off");
  list.textContent = "";
  if (!inlineOff.length) {
    const li = document.createElement("li");
    li.className = "muted";
    li.textContent = msg("options_none");
    list.append(li);
  }
  for (const host of inlineOff) {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = host;
    const back = document.createElement("button");
    back.textContent = msg("options_show_again");
    back.addEventListener("click", async () => {
      await chrome.storage.local.set({ inlineOff: inlineOff.filter((h) => h !== host) });
      render();
    });
    li.append(name, back);
    list.append(li);
  }
}

$("inline").addEventListener("change", async (event) => {
  await chrome.storage.local.set({ inlineEnabled: event.target.checked });
  render();
});

render();
