#!/bin/sh
# Удаляет программу WhoKey. Хранилище (~/.local/share/EduPasswords) остаётся на месте.
set -eu

DATA=${XDG_DATA_HOME:-$HOME/.local/share}
CONFIG=${XDG_CONFIG_HOME:-$HOME/.config}

if pgrep -u "$(id -u)" -ix whokey >/dev/null 2>&1; then
    echo "WhoKey сейчас работает. Закройте его и браузер с расширением, затем запустите удаление снова."
    exit 1
fi
rm -f "$HOME/.local/bin/whokey" "$DATA/applications/whokey.desktop" \
      "$DATA/icons/hicolor/512x512/apps/whokey.png"
for browser in google-chrome google-chrome-beta google-chrome-unstable chromium microsoft-edge \
               BraveSoftware/Brave-Browser vivaldi yandex-browser net.imput.helium; do
    rm -f "$CONFIG/$browser/NativeMessagingHosts/ru.edu.whokey.json"
done
rm -rf "$HOME/.local/opt/WhoKey"
update-desktop-database "$DATA/applications" >/dev/null 2>&1 || true
echo "WhoKey удалён. Хранилище осталось в $DATA/EduPasswords."
