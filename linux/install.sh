#!/bin/sh
# Ставит WhoKey для этого пользователя, без прав администратора:
#   программа — ~/.local/opt/WhoKey, команда — ~/.local/bin/whokey, значок — в меню приложений.
# Хранилище и настройки не трогает. При обновлении запустите заново из новой распакованной папки.
set -eu

FROM=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DATA=${XDG_DATA_HOME:-$HOME/.local/share}
TO=$HOME/.local/opt/WhoKey

if [ ! -x "$FROM/WhoKey" ]; then
    echo "Рядом с install.sh нет программы WhoKey. Распакуйте архив целиком."
    exit 1
fi
if [ "$FROM" = "$TO" ]; then
    echo "Запустите install.sh из распакованного архива, а не из установленной папки."
    exit 1
fi
# при обновлении по кнопке WhoKey уже закрылся, а мост расширения (тот же файл WhoKey,
# его запускает браузер) может работать: Linux позволяет заменить программу, пока она открыта
if [ -z "${WHOKEY_UPDATING:-}" ] && pgrep -u "$(id -u)" -ix whokey >/dev/null 2>&1; then
    echo "WhoKey сейчас работает. Закройте его и браузер с расширением, затем запустите установку снова."
    exit 1
fi

mkdir -p "$HOME/.local/opt" "$HOME/.local/bin" "$DATA/applications" "$DATA/icons/hicolor/512x512/apps"
rm -rf "$TO.new"
cp -R "$FROM" "$TO.new"
rm -rf "$TO"
mv "$TO.new" "$TO"
chmod 755 "$TO/WhoKey" "$TO/uninstall.sh"
ln -sfn "$TO/WhoKey" "$HOME/.local/bin/whokey"
cp "$TO/whokey.png" "$DATA/icons/hicolor/512x512/apps/whokey.png"
# путь — в кавычках и с экранированием по правилам .desktop: в домашней папке бывает что угодно
EXEC=$(printf '%s' "$TO/WhoKey" | sed 's/[\\"`$]/\\&/g; s/%/%%/g; s/\\/\\\\/g')
{ sed '/^Exec=/d' "$TO/whokey.desktop"; printf 'Exec="%s"\n' "$EXEC"; } > "$DATA/applications/whokey.desktop"
update-desktop-database "$DATA/applications" >/dev/null 2>&1 || true
gtk-update-icon-cache -q "$DATA/icons/hicolor" >/dev/null 2>&1 || true

echo "Готово. WhoKey есть в меню приложений, команда: $HOME/.local/bin/whokey"
