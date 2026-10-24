<p align="center">
  <img src="gui/assets/icon.png" width="128" alt="WhoKey">
</p>

<h1 align="center">WhoKey</h1>

<p align="center">A small password manager for macOS · Простой менеджер паролей для macOS</p>

<p align="center"><a href="#english">English</a> · <a href="#русский">Русский</a></p>

---

## English

WhoKey keeps your logins in one encrypted file that only opens with your master password.

### Features

- **Encryption:** the key is derived from the master password with Argon2id, and entries are encrypted with Fernet (the `cryptography` library). Nothing is stored in plain text.
- **Clipboard:** copied passwords are wiped after 30 seconds and when the app quits. macOS clipboard history apps are told not to remember them.
- **Hidden by default:** a password you reveal hides itself again after 15 seconds.
- **Password generator** with length, letters, digits and symbols, plus a rough strength meter.
- **Search,** and right-click actions on any entry: show, copy password, copy login, edit, delete.
- **Backup copy:** if the vault file gets damaged, WhoKey offers to restore it from the backup.
- **English and Russian** interface.

Your vault lives in `~/Library/Application Support/EduPasswords/vault.dat`, which is not synced to iCloud.

> ⚠️ The master password **cannot be recovered**. If you forget it, the vault is gone.
> WhoKey is a hobby app that has not had a professional security audit. For important accounts, an established manager such as Bitwarden or KeePassXC is a safer choice.

### Install

1. Download **WhoKey Installer.dmg** from [Releases](../../releases).
2. Open it and drag WhoKey into **Applications**.
3. The app is not notarized by Apple, so macOS blocks the first launch. Go to **System Settings → Privacy & Security** and click **Open Anyway**.

### Run from source

Requires Python 3.9 or newer.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

To build `WhoKey.app` and the installer yourself, run `./build_dmg.sh`. The installer appears in `dist/`.

---

## Русский

WhoKey хранит логины и пароли в одном зашифрованном файле. Открыть его можно только мастер-паролем.

### Возможности

- **Шифрование:** ключ получается из мастер-пароля через Argon2id, записи шифруются Fernet (библиотека `cryptography`). Ничего не хранится открытым текстом.
- **Буфер обмена:** скопированный пароль стирается через 30 секунд и при выходе из программы. Программам истории буфера macOS запрещено его запоминать.
- **Пароли скрыты:** показанный пароль сам прячется через 15 секунд.
- **Генератор паролей:** длина, буквы, цифры, символы и примерная шкала надёжности.
- **Поиск** и действия с записью по правому клику: показать, скопировать пароль или логин, изменить, удалить.
- **Резервная копия:** если файл хранилища испортится, WhoKey предложит восстановить его из копии.
- Интерфейс на **русском и английском**.

Хранилище лежит в `~/Library/Application Support/EduPasswords/vault.dat`. Эта папка не синхронизируется с iCloud.

> ⚠️ Мастер-пароль **нельзя восстановить**. Забыли его — хранилище не открыть.
> WhoKey — любительская программа, профессиональной проверки безопасности она не проходила. Для важных аккаунтов надёжнее проверенные менеджеры, например Bitwarden или KeePassXC.

### Установка

1. Скачайте **WhoKey Installer.dmg** в разделе [Releases](../../releases).
2. Откройте его и перетащите WhoKey в «Программы».
3. Приложение не заверено Apple, поэтому macOS заблокирует первый запуск. Откройте «Системные настройки → Конфиденциальность и безопасность» и нажмите «Всё равно открыть».

### Запуск из исходников

Нужен Python 3.9 или новее.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Чтобы самому собрать `WhoKey.app` и установщик, запустите `./build_dmg.sh`. Установщик появится в папке `dist/`.

---

The Inter font is used under the SIL Open Font License (`gui/fonts/LICENSE.txt`).
Шрифт Inter распространяется по лицензии SIL Open Font License (`gui/fonts/LICENSE.txt`).
