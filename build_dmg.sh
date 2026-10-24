#!/bin/zsh
# Собирает установщик «WhoKey Installer.dmg»: окно с иконкой WhoKey, стрелкой и папкой
# «Программы» — перетащил, и программа установлена. Всё встроенными средствами
# macOS (hdiutil, Finder), ничего ставить не нужно.
#
# Запуск из любой папки:  ./build_dmg.sh
# Готовый файл: dist/WhoKey Installer.dmg
set -e
cd "$(dirname "$0")"
P="$PWD"
BUILD="$HOME/Library/Caches/WhoKey-build"
APP="$BUILD/dist/WhoKey.app"
STAGE="$BUILD/dmg"          # что окажется внутри .dmg
RW="$BUILD/WhoKey-rw.dmg"   # черновик, который можно менять
OUT="$P/dist/WhoKey Installer.dmg"
VOL="WhoKey Installer"  # имя диска — так он подписан на Рабочем столе при установке
APPS_LINK="Программы"       # ярлык на /Applications внутри установщика
VENV="$P/.venv"; [ -d "$VENV" ] || VENV="$P/../.venv"

# 1. Свежая сборка .app (build_app.sh сам остановится на любой ошибке)
./build_app.sh

# 2. Содержимое установщика: приложение, ярлык на «Программы», спрятанный фон
rm -rf "$STAGE" "$RW"
mkdir -p "$STAGE/.background"
ditto "$APP" "$STAGE/WhoKey.app"
ln -s /Applications "$STAGE/$APPS_LINK"
"$VENV/bin/python" -B gui/assets/make_dmg_background.py "$STAGE/.background/background.png"

# 3. Черновой образ диска, который можно подключить и оформить
[ -d "/Volumes/$VOL" ] && hdiutil detach "/Volumes/$VOL" -force  # остался от упавшей сборки
hdiutil create -srcfolder "$STAGE" -volname "$VOL" -fs HFS+ -format UDRW -ov "$RW" >/dev/null
DEVICE=$(hdiutil attach -readwrite -noverify -noautoopen "$RW" | grep -E '^/dev/' | head -1 | awk '{print $1}')

# 4. Оформление окна: Finder запоминает его в самом образе (файл .DS_Store)
osascript <<EOF
tell application "Finder"
  tell disk "$VOL"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    -- 660×420 — размер фона (+28 на заголовок окна)
    set the bounds of container window to {200, 120, 860, 568}
    set opts to the icon view options of container window
    set arrangement of opts to not arranged
    set icon size of opts to 128
    set text size of opts to 13
    set background picture of opts to file ".background:background.png"
    set position of item "WhoKey.app" of container window to {170, 220}
    set position of item "$APPS_LINK" of container window to {490, 220}
    update without registering applications
    delay 2
    close
  end tell
end tell
EOF

# Иконка самого диска — ПОСЛЕ Finder: при оформлении окна Finder почему-то
# удаляет .VolumeIcon.icns (проверено). Флаг «у диска своя иконка» включаем тут же.
cp gui/assets/WhoKey.icns "/Volumes/$VOL/.VolumeIcon.icns"
SetFile -a C "/Volumes/$VOL"

# 5. Отключаем черновик и сжимаем в итоговый образ «только для чтения»
sync
hdiutil detach "$DEVICE" >/dev/null
mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"
hdiutil convert "$RW" -format UDZO -imagekey zlib-level=9 -o "$OUT" >/dev/null
rm -f "$RW"
hdiutil verify "$OUT" >/dev/null
echo "Готово: $OUT ($(du -h "$OUT" | cut -f1))"
