// Значок WhoKey в поле логина и пароля.
//
// Этот файл работает на каждой странице, но ничего не читает и никуда не отправляет:
// он только находит поля и рисует рядом с ними значок. Нажатие на значок открывает
// окошко WhoKey на панели браузера — список аккаунтов и выбор там, а не на странице:
// окошко — часть самого браузера, сайт не может его ни подделать, ни накрыть, ни спрятать.
// Пароль по-прежнему вставляет фоновая часть (background.js), только после выбора человеком.

(() => {
  if (window.top !== window) return; // только сама страница, не встроенные в неё фреймы

  // отметка поля для вставки (см. background.js): по ключу-символу, а не по имени —
  // элемент страницы с id="__whokeyTarget" подменил бы обычное свойство window
  const TARGET = Symbol.for("whokey.target");
  globalThis[TARGET] = null;
  const ICON = "data:image/png;base64,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";
  const SIZE = 20;      // значок, точек
  const GAP = 8;        // от правого края поля

  // всё своё — внутри закрытого «теневого» корня: стили сайта его не трогают,
  // а скрипты сайта не видят, что внутри
  const host = document.createElement("whokey-root");
  host.style.cssText = "all: initial !important; position: fixed !important; inset: 0 !important;"
    + " width: 0 !important; height: 0 !important; z-index: 2147483647 !important;";
  const root = host.attachShadow({ mode: "closed" });
  const style = document.createElement("style");
  style.textContent = `
    button { all: initial; position: fixed; width: ${SIZE}px; height: ${SIZE}px; cursor: pointer;
             background: url(${ICON}) center / contain no-repeat; border-radius: 5px; opacity: .85; }
    button:hover { opacity: 1; filter: drop-shadow(0 0 4px rgba(221, 170, 249, .9)); }`;
  root.append(style);

  const icons = new Map(); // поле -> его значок

  const visible = (el) => {
    if (!el.isConnected || el.disabled || el.readOnly) return false;
    if (el.checkVisibility && !el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return false;
    const box = el.getBoundingClientRect();
    return box.width >= 60 && box.height >= 16;
  };

  // поля, рядом с которыми нужен значок: каждое поле пароля и поле логина перед ним
  function targets() {
    const inputs = [...document.querySelectorAll("input")].filter(visible);
    const found = new Set();
    inputs.forEach((el, i) => {
      if (el.type !== "password") return;
      found.add(el);
      const scope = el.form ? inputs.filter((x) => x.form === el.form) : inputs.slice(0, i);
      const before = scope.slice(0, scope.indexOf(el) < 0 ? scope.length : scope.indexOf(el));
      const login = before.filter((x) => x.autocomplete === "username").pop()
        || before.filter((x) => ["text", "email", "tel"].includes(x.type)).pop();
      if (login) found.add(login);
    });
    // вход в два шага: сначала только логин или почта (GeoGuessr, Google, Microsoft).
    // Поле почты бывает и в подписке на рассылку или в комментариях — поэтому только
    // на страницах, где полей ввода мало, как на странице входа
    const textual = inputs.filter((x) => ["text", "email", "tel", ""].includes(x.type));
    if (!found.size && textual.length <= 3) {
      const loginLike = (x) => x.autocomplete === "username" || x.autocomplete === "email" || x.type === "email"
        || /e-?mail|login|user/i.test(`${x.name} ${x.id}`);
      const login = textual.find(loginLike);
      if (login) found.add(login);
    }
    return found;
  }

  // что сайт показывает в этой точке (без наших значков: они лежат в host)
  const pageAt = (x, y) => document.elementsFromPoint(x, y).find((el) => el !== host);
  const isField = (el, field) => el && (el === field || field.contains(el));
  // поверх поля часто лежит «плавающая» подпись — поле при этом видно
  const isFieldOrLabel = (el, field) => isField(el, field) || (el && el.closest("label") && el.closest("label").control === field);

  // поле нового пароля (регистрация, смена пароля) — в окошке будет «Сгенерировать пароль»
  function isNewPassword(field) {
    if (field.type !== "password") return false;
    const mark = (field.autocomplete || "").toLowerCase();
    if (mark === "new-password") return true;
    if (mark === "current-password") return false;
    const passwords = [...(field.form || document).querySelectorAll("input[type=password]")].filter(visible);
    // пароль + повтор — регистрация; «старый, новый, повтор» — новые все, кроме первого
    return passwords.length === 2 || (passwords.length >= 3 && passwords.indexOf(field) > 0);
  }

  function place(field, icon) {
    const box = field.getBoundingClientRect();
    const y = box.top + box.height / 2;
    // поле спрятано прокруткой внутри блока или накрыто — значок не нужен
    // (иначе он висел бы поверх чужого текста)
    const seen = [box.left + 6, box.left + box.width / 2, box.right - 6]
      .some((x) => x >= 0 && x <= innerWidth && isFieldOrLabel(pageAt(x, y), field));
    if (box.bottom < 0 || box.top > innerHeight || !seen) {
      icon.style.display = "none";
      return;
    }
    // справа в поле у сайта бывает своя кнопка («показать пароль»): тогда значок левее неё
    let x = box.right - SIZE - GAP;
    for (let step = 0; step < 4 && !isField(pageAt(x + SIZE / 2, y), field); step++) x -= SIZE + GAP;
    if (!isField(pageAt(x + SIZE / 2, y), field)) {
      icon.style.display = "none";
      return;
    }
    icon.style.left = `${x}px`;
    icon.style.top = `${y - SIZE / 2}px`;
    icon.style.display = "block";
  }

  function update() {
    const wanted = targets();
    for (const [field, icon] of icons) {
      if (!wanted.has(field)) { icon.remove(); icons.delete(field); }
    }
    for (const field of wanted) {
      let icon = icons.get(field);
      if (!icon) {
        icon = document.createElement("button");
        icon.title = "WhoKey";
        // mousedown — чтобы поле не теряло фокус, а нажатие не ушло странице
        icon.addEventListener("mousedown", (event) => { event.preventDefault(); event.stopPropagation(); });
        icon.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          if (!event.isTrusted) return;
          // отметка для вставки пароля (fillInPage в background.js): заполнять эту форму,
          // а не первую. Живёт в изолированном мире расширения — сайт её не видит
          globalThis[TARGET] = field;
          // фоновая часть открывает окошко на панели браузера; аккаунт выбирают там
          chrome.runtime.sendMessage({ kind: "icon_click", newPassword: isNewPassword(field) }).catch(() => {});
        });
        root.append(icon);
        icons.set(field, icon);
      }
      place(field, icon);
    }
    if (!host.isConnected && icons.size) document.documentElement.append(host);
  }

  // сообщения приходят только от самого расширения (страница их послать не может)
  chrome.runtime.onMessage.addListener((message) => {
    if (message.kind === "inline_off") stop(); // «Не показывать на этом сайте»
  });

  // поля появляются и двигаются (вход во всплывающем окне, одностраничные сайты) —
  // пересчитываем при изменениях страницы, но не чаще, чем раз в кадр
  let scheduled = false;
  const later = () => {
    if (scheduled || stopped) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; update(); });
  };
  const observer = new MutationObserver(later);
  let timer = null;
  let stopped = false;

  function start() {
    observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true });
    addEventListener("scroll", later, true);
    addEventListener("resize", later);
    timer = setInterval(later, 1000); // на случай анимаций, которые не меняют DOM
    update();
  }

  function stop() {
    stopped = true;
    observer.disconnect();
    removeEventListener("scroll", later, true);
    removeEventListener("resize", later);
    clearInterval(timer);
    globalThis[TARGET] = null;
    host.remove();
    icons.clear();
  }

  // значок выключен в настройках расширения (везде или на этом сайте) — ничего не рисуем
  chrome.runtime.sendMessage({ kind: "inline_state" })
    .then((reply) => { if (reply && reply.show && !stopped) start(); })
    .catch(() => {});
})();
