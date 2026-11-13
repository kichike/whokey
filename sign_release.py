"""Подпись релиза WhoKey для обновления по кнопке (gui/updater.py).

WhoKey ставит обновление, только если релиз подписан этим ключом: открытая половина
встроена в программу (updater.PUBLIC_KEY), секретная лежит только на компьютере автора.
Взломают GitHub или подменят файл по дороге — подпись не сойдётся, и WhoKey ничего не поставит.

    python3 sign_release.py init                    — один раз: создать ключ (печатает открытую половину)
    python3 sign_release.py 1.10.0 dist/SHA256SUMS  — подписать: рядом появится WhoKey-release.sig

Подписывается не только SHA256SUMS, но и номер версии: старый подписанный релиз нельзя выдать за новый.
Ключ — ~/.config/whokey-release/signing-key.pem (только для владельца). Потеряете его —
обновления по кнопке перестанут ставиться (нужен будет новый ключ и один ручной выпуск).
Сделайте копию в надёжном месте, например заметкой в самом WhoKey.
"""

import base64
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gui.updater import SIGNATURE_NAME, parse_version, signed_message  # noqa: E402

KEY_FILE = Path.home() / ".config" / "whokey-release" / "signing-key.pem"


def init():
    if KEY_FILE.exists():
        sys.exit(f"Ключ уже есть: {KEY_FILE}. Новый не создаю — старые программы его бы не приняли.")
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(KEY_FILE.parent, 0o700)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(pem)
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print("Ключ:", KEY_FILE)
    print("Открытая половина (в gui/updater.py, PUBLIC_KEY):", public.hex())


def sign(version, sums_path):
    if parse_version(version) is None:
        sys.exit(f"Версия должна быть вида 1.10.0, а не {version!r}")
    key = serialization.load_pem_private_key(KEY_FILE.read_bytes(), password=None)
    sums = Path(sums_path).read_bytes()
    signature = key.sign(signed_message(version, sums))
    target = Path(sums_path).with_name(SIGNATURE_NAME)
    target.write_text(base64.b64encode(signature).decode() + "\n")
    print("Подпись:", target)


if __name__ == "__main__":
    if sys.argv[1:] == ["init"]:
        init()
    elif len(sys.argv) == 3:
        sign(sys.argv[1], sys.argv[2])
    else:
        sys.exit(__doc__)
