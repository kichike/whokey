#!/bin/bash
# Один раз на Mac, где собирается WhoKey: создаёт постоянный сертификат подписи
# «WhoKey Code Signing» (самоподписанный, бесплатный) и кладёт его в Связку ключей.
#
# Зачем: без него build_app.sh подписывает WhoKey «сам собой» (ad-hoc), и macOS
# узнаёт программу по отпечатку конкретной сборки. После каждого обновления
# WhoKey для неё — новая программа, и запись Touch ID в Связке ключей просит
# пароль Mac. С постоянным сертификатом macOS узнаёт WhoKey и после обновлений.
#
# Это не подпись Apple: предупреждение «неизвестный разработчик» при первом
# запуске скачанного WhoKey останется. Закрытый ключ остаётся только в Связке
# ключей этого Mac. Удалить: «Связка ключей» → «Мои сертификаты» → WhoKey Code Signing.

set -e
NAME="WhoKey Code Signing"
# встроенный в macOS openssl (LibreSSL): OpenSSL 3 из Homebrew упаковывает .p12 так,
# что security его не читает («MAC verification failed … wrong password?»)
OPENSSL=/usr/bin/openssl
KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"

if security find-certificate -c "$NAME" "$KEYCHAIN" >/dev/null 2>&1; then
  echo "Сертификат «$NAME» уже есть — ничего не делаю."
  exit 0
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cat > "$WORK/cert.cnf" <<EOF
[req]
distinguished_name = dn
x509_extensions = ext
prompt = no
[dn]
CN = $NAME
[ext]
basicConstraints = critical, CA:false
keyUsage = critical, digitalSignature
extendedKeyUsage = critical, codeSigning
EOF

"$OPENSSL" req -x509 -newkey rsa:2048 -nodes -days 3650 -config "$WORK/cert.cnf" \
  -keyout "$WORK/key.pem" -out "$WORK/cert.pem" 2>/dev/null
PASS=$("$OPENSSL" rand -hex 16)
"$OPENSSL" pkcs12 -export -inkey "$WORK/key.pem" -in "$WORK/cert.pem" \
  -out "$WORK/whokey.p12" -passout "pass:$PASS"

# -T /usr/bin/codesign: подписывать этим ключом можно без лишних вопросов
security import "$WORK/whokey.p12" -k "$KEYCHAIN" -P "$PASS" -T /usr/bin/codesign
# доверять сертификату для подписи программ (macOS спросит пароль Mac — это нормально)
security add-trusted-cert -r trustRoot -p codeSign -k "$KEYCHAIN" "$WORK/cert.pem"

echo
echo "Готово. Теперь ./build_app.sh будет подписывать WhoKey этим сертификатом."
security find-identity -v -p codesigning | grep "$NAME" || true
