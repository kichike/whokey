"""Проверка собранного WhoKey.exe в режиме моста (как его запускает браузер). Только для CI Windows.

Запуск: python tests/host_mode_check.py dist\\WhoKey\\WhoKey.exe
Браузер пишет мосту в stdin: 4 байта длины + JSON. На не-JSON мост должен ответить
{"status": "error"} и ничего не открывать — так видно, что программа с окнами
действительно получила каналы stdin/stdout и пишет в них в двоичном виде.
"""

import json
import struct
import subprocess
import sys

exe = sys.argv[1]
message = struct.pack("<I", 5) + b"nojso" + struct.pack("<I", 2) + b"[]"
result = subprocess.run([exe, "chrome-extension://pchmmhgfnhhkginkifminckbjcojodgl/", "--parent-window=0"],
                        input=message, capture_output=True, timeout=60)
data, replies = result.stdout, []
while len(data) >= 4:
    size = struct.unpack("<I", data[:4])[0]
    replies.append(json.loads(data[4:4 + size]))
    data = data[4 + size:]
print("код:", result.returncode, "ответы:", replies, "лишнее:", data)
ok = replies == [{"status": "error"}, {"status": "error"}] and not data
print("OK   мост в собранном WhoKey.exe отвечает браузеру" if ok else "FAIL мост не ответил как надо")
sys.exit(0 if ok else 1)
