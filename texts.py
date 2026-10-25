"""Тексты консольной версии менеджера паролей (manager.py) на русском и английском.

У приложения с окнами свой перевод — Qt Linguist, папка translations/ (см. gui/i18n.py).
"""

LANG = "ru"  # текущий язык; меняется через set_language()


def set_language(lang):
    global LANG
    LANG = lang


def t(key, **values):
    """Текст по ключу на текущем языке."""
    return TEXTS[LANG][key].format(**values)


TEXTS = {
    "ru": {
        # общее
        "choice": "Ваш выбор: ",
        "bye": "До свидания!",
        "clipboard_cleared": "Скопированный пароль удалён из буфера обмена.",
        "no_option": "Нет такого пункта — нажмите цифру из меню.",
        "cancelled": "Отменено.",
        "yes_no": "1 — да, 0 — нет: ",
        "save_failed": "⚠ Не удалось сохранить: {error}. Изменение не применено, файл на диске не тронут.",
        "backup_failed": "⚠ Изменение сохранено, но резервная копия не обновилась: {error}.",
        "bad_input": "Не удалось прочитать ввод (сломанная буква?) — введите ещё раз.",
        "unexpected": "⚠ Непредвиденная ошибка: {error}.\nФайл хранилища цел: изменения записываются через временный файл.",
        "back_prompt": "0 — назад в меню: ",

        # создание и вход
        "no_vault": "Хранилище {path} не найдено.",
        "create_or_exit": "1. Создать новое хранилище\n0. Выход",
        "new_master_rules": "Придумайте мастер-пароль: не короче 12 символов. "
                            "Его нельзя восстановить — если забудете, пароли пропадут.",
        "new_master": "Новый мастер-пароль (символы не видны; Enter без пароля — отмена): ",
        "repeat_master": "Повторите мастер-пароль: ",
        "too_short": "Слишком короткий: {n} симв., нужно не меньше 12.",
        "mismatch": "Пароли не совпадают, попробуйте ещё раз.",
        "weak_header": "⚠ Пароль слабый:",
        "use_anyway": "Всё равно использовать? 1 — да, 0 — придумать другой: ",
        "vault_created": "Хранилище создано: {path}",
        "icloud_warning": "⚠ Похоже, эта папка синхронизируется с iCloud («Рабочий стол и Документы»).\n"
                          "Хранилище там зашифровано, но оно и его старые версии будут лежать в облаке.\n"
                          "Если не хотите этого, храните его в другой папке: "
                          "../.venv/bin/python manager.py ~/vault.dat",
        "main_missing": "Основной файл {name} не найден, но есть резервная копия {backup}.",
        "missing_options": "1. Восстановить из резервной копии\n"
                           "2. Создать новое пустое хранилище (старая копия сохранится под другим именем)\n"
                           "0. Выход",
        "old_backup_kept": "Старая резервная копия отложена как {name} (скрытый файл рядом с хранилищем).",
        "enter_master": "Мастер-пароль: ",
        "wrong_password": "Неверный мастер-пароль.",
        "too_many": "Слишком много неудачных попыток. Программа закрывается.\n"
                    "(Если вы точно уверены в пароле — возможно, файл повреждён.)",
        "vault_damaged": "Файл {path} повреждён или не является хранилищем паролей.",
        "try_backup": "Есть резервная копия {name} — попробуем открыть её.",
        "main_damaged": "Основной файл хранилища повреждён, но резервная копия открылась этим паролем\n"
                        "(в ней может не быть самых последних изменений).",
        "restore_question": "Восстановить хранилище из резервной копии? ",
        "restored": "Хранилище восстановлено из резервной копии.",
        "restore_declined": "Восстановление отменено, хранилище не изменено.",
        "vault_locked": "Это хранилище уже открыто в другом окне. Закройте его там и попробуйте снова.",
        "lock_error": "Не удалось открыть хранилище {path}: {error}",
        "unlocked": "Хранилище открыто, записей: {n}.",

        # причины слабости пароля
        "weak_short": "короче 12 символов",
        "weak_common": "содержит очень частое слово или комбинацию (qwerty, 123456, password...)",
        "weak_one_kind": "только один вид символов — добавьте буквы разного регистра, цифры, знаки",
        "weak_repeat": "один символ повторяется 4 раза подряд",

        # меню
        "menu_header": "Хранилище: {name} · записей: {n}",
        "m_list": "1. Все записи",
        "m_search": "2. Найти",
        "m_add": "3. Добавить",
        "m_edit": "4. Изменить",
        "m_delete": "5. Удалить",
        "m_show": "6. Показать / скопировать пароль",
        "m_generate": "7. Генератор паролей",
        "m_master": "8. Сменить мастер-пароль",
        "m_exit": "0. Выход",

        # список и выбор записи
        "col_site": "Сайт",
        "col_login": "Логин",
        "col_password": "Пароль",
        "col_note": "Заметка",
        "empty_vault": "Записей пока нет — добавьте первую (пункт 3).",
        "nothing_found": "Ничего не найдено.",
        "search_prompt": "Что искать (сайт, логин или заметка): ",
        "pick_entry": "Номер записи (Enter — отмена): ",
        "bad_number": "Нет записи с таким номером.",

        # добавление и изменение
        "site": "Сайт или сервис: ",
        "login": "Логин: ",
        "note": "Заметка (можно пусто): ",
        "site_required": "Сайт нужно указать.",
        "password_how": "Пароль:\n1. Сгенерировать\n2. Ввести самому\n0. Отмена",
        "enter_password": "Пароль (символы не видны; Enter без пароля — отмена): ",
        "repeat_password": "Повторите пароль: ",
        "password_not_changed": "Пароль НЕ изменён.",
        "site_password_weak": "Сайт может требовать простой пароль, поэтому сохраняю, но лучше сгенерировать.",
        "added": "Запись «{site}» добавлена.",
        "edit_hint": "Enter — оставить как было, «-» — очистить поле.",
        "edit_field": "{label} [{value}]: ",
        "password_edit": "Пароль:\n1. Оставить\n2. Сгенерировать новый\n3. Ввести самому",
        "updated": "Запись «{site}» изменена.",
        "nothing_changed": "Ничего не изменено.",
        "confirm_delete": "Удалить «{site}» ({login})? ",
        "deleted": "Запись «{site}» удалена.",

        # просмотр и буфер
        "entry_details": "Сайт:     {site}\nЛогин:    {login}\nЗаметка:  {note}\nИзменено: {updated}",
        "show_what": "1. Показать пароль на экране\n2. Скопировать пароль в буфер (очистится через {sec} с)\n0. Назад",
        "password_is": "Пароль:   {password}",
        "screen_warning": "(пароль остался в истории окна терминала — закройте окно, если за компьютером не только вы)",
        "copied": "Пароль скопирован. Буфер очистится через {sec} с или при выходе из программы.",
        "copy_failed": "Не получилось скопировать пароль в буфер обмена.",
        "copy_now": "Скопировать пароль в буфер? ",

        # генератор
        "gen_header": "Генератор паролей:",
        "gen_presets": ("1. Надёжный — 20 знаков, все виды символов\n"
                        "2. Без спецсимволов — 16 знаков (для сайтов, которые их не принимают)\n"
                        "3. Свои настройки\n"
                        "0. Назад"),
        "gen_length": "Длина ({low}–{high}, Enter — 16): ",
        "gen_bad_length": "Длина должна быть числом от {low} до {high}.",
        "gen_use_lower": "Строчные буквы (abc)? ",
        "gen_use_upper": "Заглавные буквы (ABC)? ",
        "gen_use_digits": "Цифры (123)? ",
        "gen_use_symbols": "Спецсимволы (!@#)? ",
        "gen_nothing": "Нужно выбрать хотя бы один вид символов.",
        "gen_strength": "Пароль создан. Надёжность: ≈{bits:.0f} бит ({verdict}).",
        "gen_hidden": "Пароль на экран не выводится: скопируйте его сейчас или посмотрите позже (пункт 6).",
        "verdict_strong": "очень надёжно",
        "verdict_ok": "надёжно",
        "verdict_weak": "слабовато — увеличьте длину",

        # смена мастер-пароля
        "current_master": "Текущий мастер-пароль: ",
        "master_changed": "Мастер-пароль изменён, хранилище перешифровано.",
    },

    "en": {
        "choice": "Your choice: ",
        "bye": "Goodbye!",
        "clipboard_cleared": "The copied password was removed from the clipboard.",
        "no_option": "No such option — press a digit from the menu.",
        "cancelled": "Cancelled.",
        "yes_no": "1 — yes, 0 — no: ",
        "save_failed": "⚠ Could not save: {error}. The change was not applied, the file on disk is untouched.",
        "backup_failed": "⚠ The change is saved, but the backup was not updated: {error}.",
        "bad_input": "Could not read the input (broken character?) — please type it again.",
        "unexpected": "⚠ Unexpected error: {error}.\nThe vault file is intact: changes are written via a temporary file.",
        "back_prompt": "0 — back to menu: ",

        "no_vault": "Vault {path} not found.",
        "create_or_exit": "1. Create a new vault\n0. Exit",
        "new_master_rules": "Choose a master password: at least 12 characters. "
                            "It cannot be recovered — if you forget it, your passwords are lost.",
        "new_master": "New master password (input hidden; Enter with no password — cancel): ",
        "repeat_master": "Repeat master password: ",
        "too_short": "Too short: {n} characters, at least 12 required.",
        "mismatch": "Passwords don't match, try again.",
        "weak_header": "⚠ Weak password:",
        "use_anyway": "Use it anyway? 1 — yes, 0 — choose another: ",
        "vault_created": "Vault created: {path}",
        "icloud_warning": "⚠ This folder seems to be synced with iCloud (\"Desktop & Documents\").\n"
                          "The vault is encrypted there, but it and its old versions will be stored in the cloud.\n"
                          "If you don't want that, keep it in another folder: "
                          "../.venv/bin/python manager.py ~/vault.dat",
        "main_missing": "The main file {name} was not found, but there is a backup {backup}.",
        "missing_options": "1. Restore from the backup\n"
                           "2. Create a new empty vault (the old backup will be kept under another name)\n"
                           "0. Exit",
        "old_backup_kept": "The old backup was set aside as {name} (a hidden file next to the vault).",
        "enter_master": "Master password: ",
        "wrong_password": "Wrong master password.",
        "too_many": "Too many failed attempts. Exiting.\n"
                    "(If you are sure the password is right, the file may be damaged.)",
        "vault_damaged": "{path} is damaged or is not a password vault.",
        "try_backup": "There is a backup {name} — trying to open it.",
        "main_damaged": "The main vault file is damaged, but the backup opened with this password\n"
                        "(it may lack the most recent changes).",
        "restore_question": "Restore the vault from the backup? ",
        "restored": "Vault restored from the backup.",
        "restore_declined": "Restore cancelled, the vault was not changed.",
        "vault_locked": "This vault is already open in another window. Close it there and try again.",
        "lock_error": "Could not open the vault {path}: {error}",
        "unlocked": "Vault unlocked, entries: {n}.",

        "weak_short": "shorter than 12 characters",
        "weak_common": "contains a very common word or pattern (qwerty, 123456, password...)",
        "weak_one_kind": "only one kind of characters — mix upper/lower case, digits, symbols",
        "weak_repeat": "one character repeated 4 times in a row",

        "menu_header": "Vault: {name} · entries: {n}",
        "m_list": "1. All entries",
        "m_search": "2. Search",
        "m_add": "3. Add",
        "m_edit": "4. Edit",
        "m_delete": "5. Delete",
        "m_show": "6. Show / copy password",
        "m_generate": "7. Password generator",
        "m_master": "8. Change master password",
        "m_exit": "0. Exit",

        "col_site": "Site",
        "col_login": "Login",
        "col_password": "Password",
        "col_note": "Note",
        "empty_vault": "No entries yet — add the first one (option 3).",
        "nothing_found": "Nothing found.",
        "search_prompt": "Search for (site, login or note): ",
        "pick_entry": "Entry number (Enter — cancel): ",
        "bad_number": "No entry with this number.",

        "site": "Site or service: ",
        "login": "Login: ",
        "note": "Note (may be empty): ",
        "site_required": "Site is required.",
        "password_how": "Password:\n1. Generate\n2. Type it myself\n0. Cancel",
        "enter_password": "Password (input hidden; Enter with no password — cancel): ",
        "repeat_password": "Repeat password: ",
        "password_not_changed": "The password was NOT changed.",
        "site_password_weak": "The site may require a simple password, so it is saved, but generating one is better.",
        "added": "Entry \"{site}\" added.",
        "edit_hint": "Enter — keep the current value, \"-\" — clear the field.",
        "edit_field": "{label} [{value}]: ",
        "password_edit": "Password:\n1. Keep\n2. Generate a new one\n3. Type it myself",
        "updated": "Entry \"{site}\" updated.",
        "nothing_changed": "Nothing changed.",
        "confirm_delete": "Delete \"{site}\" ({login})? ",
        "deleted": "Entry \"{site}\" deleted.",

        "entry_details": "Site:     {site}\nLogin:    {login}\nNote:     {note}\nUpdated:  {updated}",
        "show_what": "1. Show password on screen\n2. Copy password to clipboard (cleared in {sec} s)\n0. Back",
        "password_is": "Password: {password}",
        "screen_warning": "(the password stays in the terminal window history — close the window if others use this computer)",
        "copied": "Password copied. The clipboard will be cleared in {sec} s or when you exit.",
        "copy_failed": "Could not copy the password to the clipboard.",
        "copy_now": "Copy the password to the clipboard? ",

        "gen_header": "Password generator:",
        "gen_presets": ("1. Strong — 20 characters, all kinds\n"
                        "2. No symbols — 16 characters (for sites that reject them)\n"
                        "3. Custom settings\n"
                        "0. Back"),
        "gen_length": "Length ({low}–{high}, Enter — 16): ",
        "gen_bad_length": "Length must be a number from {low} to {high}.",
        "gen_use_lower": "Lowercase letters (abc)? ",
        "gen_use_upper": "Uppercase letters (ABC)? ",
        "gen_use_digits": "Digits (123)? ",
        "gen_use_symbols": "Symbols (!@#)? ",
        "gen_nothing": "Choose at least one kind of characters.",
        "gen_strength": "Password generated. Strength: ≈{bits:.0f} bits ({verdict}).",
        "gen_hidden": "The password is not shown on screen: copy it now or view it later (option 6).",
        "verdict_strong": "very strong",
        "verdict_ok": "strong",
        "verdict_weak": "weak-ish — increase the length",

        "current_master": "Current master password: ",
        "master_changed": "Master password changed, vault re-encrypted.",
    },
}
