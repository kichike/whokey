#!/bin/zsh
# Собирает WhoKey.app (macOS) из app.py и кладёт его в ~/Applications.
# Запуск из любой папки:  ./build_app.sh
#
# Почему сборка идёт в ~/Library/Caches, а не рядом с проектом: «Рабочий стол»
# синхронизируется с iCloud, а iCloud и Finder ставят на файлы служебные пометки —
# с ними не проходит подпись. В папке Caches iCloud ничего не трогает.
set -e  # любая ошибка — сразу стоп, а не «Готово» со старой сборкой
cd "$(dirname "$0")"
P="$PWD"
BUILD="$HOME/Library/Caches/WhoKey-build"
APP="$BUILD/dist/WhoKey.app"
INSTALL="$HOME/Applications/WhoKey.app"
# окружение с библиотеками: .venv рядом со скриптом или в папке выше
VENV="$P/.venv"; [ -d "$VENV" ] || VENV="$P/../.venv"

rm -rf "$BUILD"  # старой сборки не остаётся — нечего случайно выдать за новую

# переводы окон: translations/*.ts -> *.qm (Qt Linguist)
"$VENV/bin/python" "$P/translations/build.py"

# картинки окон и переводы — все файлы папок (как в build_windows.py): новый файл не забудется
DATA=(--add-data "$P/gui/assets/icon.png:gui/assets")
for f in "$P"/gui/assets/*.svg; do DATA+=(--add-data "${f}:gui/assets"); done
for f in "$P"/translations/*.qm; do DATA+=(--add-data "${f}:translations"); done

"$VENV/bin/pyinstaller" --noconfirm --windowed --log-level WARN \
  --name WhoKey --icon "$P/gui/assets/WhoKey.icns" --osx-bundle-identifier ru.edu.whokey \
  --add-data "$P/gui/fonts:gui/fonts" \
  --add-data "$P/public_suffix_list.dat:." \
  "${DATA[@]}" \
  --paths "$P" \
  --exclude-module tkinter --exclude-module matplotlib --exclude-module pandas --exclude-module numpy \
  --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick \
  --exclude-module PySide6.QtPdf --exclude-module PySide6.QtVirtualKeyboard \
  --distpath "$BUILD/dist" --workpath "$BUILD/work" --specpath "$BUILD" \
  "$P/app.py"

# Лишние части Qt (~25 МБ): их тянут плагины, которые приложению не нужны —
# виртуальная клавиатура, чтение PDF как картинок, сенсорный экран.
# QtDBus НЕ трогаем: на нём держится QtGui. QtNetwork тоже нужен — через его
# локальный сокет WhoKey разговаривает с расширением браузера (gui/bridge.py).
QT="$APP/Contents/Frameworks/PySide6/Qt"
rm -f "$QT/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.dylib" \
      "$QT/plugins/imageformats/libqpdf.dylib" \
      "$QT/plugins/generic/libqtuiotouchplugin.dylib"
for lib in QtPdf QtQml QtQmlMeta QtQmlModels QtQmlWorkerScript QtQuick \
           QtVirtualKeyboard QtVirtualKeyboardQml; do
  rm -rf "$QT/lib/$lib.framework"
done
# PyInstaller кладёт в Contents/Frameworks ещё и ярлыки на эти библиотеки —
# после удаления они ведут в никуда, убираем и их
find "$APP" -type l ! -exec test -e {} \; -delete

# Версия в «Свойствах» приложения (иначе PyInstaller пишет 0.0.0) — та же,
# что у установщика Windows: номер версии хранится в одном месте, installer.iss
VERSION=$(sed -n 's/^ *#define AppVersion "\(.*\)"/\1/p' "$P/installer.iss")
[ -n "$VERSION" ] || { echo "Не нашёл AppVersion в installer.iss"; exit 1; }
plutil -replace CFBundleShortVersionString -string "$VERSION" "$APP/Contents/Info.plist"
plutil -replace CFBundleVersion -string "$VERSION" "$APP/Contents/Info.plist"

# Подпись «для себя» (ad-hoc): на Mac с процессором Apple без подписи программа
# не запустится. После удаления файлов подписываем заново.
xattr -cr "$APP"
# Постоянный сертификат «WhoKey Code Signing» (создаётся один раз: ./make_signing_identity.sh) —
# тогда macOS узнаёт WhoKey и после обновлений (Touch ID не просит пароль Mac).
# Нет сертификата — подпись «для себя» (ad-hoc), как раньше.
SIGN="-"
if security find-identity -v -p codesigning | grep -q "WhoKey Code Signing"; then
  SIGN="WhoKey Code Signing"
fi
echo "Подпись: ${SIGN/-/ad-hoc}"
# --options runtime — «усиленная защита среды выполнения»: чужой код через DYLD_* в WhoKey
# не подсунуть (права и объяснение — в WhoKey.entitlements)
codesign -s "$SIGN" --force --deep --options runtime --entitlements "$P/WhoKey.entitlements" "$APP"
codesign --verify --deep --strict "$APP"

# Устанавливаем в ~/Applications — личную папку программ (её видно в Launchpad)
mkdir -p "$HOME/Applications"
rm -rf "$INSTALL"
ditto "$APP" "$INSTALL"  # ditto сохраняет подпись и ссылки внутри .app
codesign --verify --deep --strict "$INSTALL"

echo "Готово: $INSTALL ($(du -sh "$INSTALL" | cut -f1))"
