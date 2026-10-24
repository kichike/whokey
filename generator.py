"""Генератор паролей и проверка надёжности пароля.

Для паролей используется модуль secrets, а не random: random предсказуем
(его «случайность» можно восстановить по нескольким выданным числам),
secrets берёт случайность у операционной системы и создан как раз для паролей.
"""

import math
import secrets
import string

LOWER = string.ascii_lowercase       # abc...z
UPPER = string.ascii_uppercase       # ABC...Z
DIGITS = string.digits               # 0123456789
SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?/"

MIN_LENGTH = 8
MAX_LENGTH = 128


def generate_password(length=16, lower=True, upper=True, digits=True, symbols=True):
    """Создаёт случайный пароль. В нём будет хотя бы один символ каждого выбранного вида."""
    groups = [chars for chars, use in
              [(LOWER, lower), (UPPER, upper), (DIGITS, digits), (SYMBOLS, symbols)] if use]
    if not groups:
        raise ValueError("нужно выбрать хотя бы один вид символов")
    if not MIN_LENGTH <= length <= MAX_LENGTH:
        raise ValueError(f"длина должна быть от {MIN_LENGTH} до {MAX_LENGTH}")

    alphabet = "".join(groups)
    # по одному символу из каждого выбранного вида, остальное — из всех сразу
    chars = [secrets.choice(group) for group in groups]
    chars += [secrets.choice(alphabet) for _ in range(length - len(groups))]
    # перемешиваем, чтобы обязательные символы не стояли всегда в начале
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def entropy_bits(length, lower=True, upper=True, digits=True, symbols=True):
    """Сколько бит случайности в сгенерированном пароле.

    Каждый бит удваивает число вариантов для перебора: 80 бит и больше
    сегодня считается очень надёжно.
    """
    size = (len(LOWER) * lower + len(UPPER) * upper
            + len(DIGITS) * digits + len(SYMBOLS) * symbols)
    return length * math.log2(size)


def estimate_bits(password):
    """Примерная надёжность пароля, который человек придумал сам (для шкалы в окне).

    Считаем, будто каждый символ выбран случайно из тех видов символов, что
    есть в пароле. Для придуманных людьми паролей это завышено, поэтому
    частые слова и повторы сильно снижают оценку.
    """
    if not password:
        return 0.0
    # любой символ попадает хотя бы в один вид, поэтому хоть один будет True
    bits = entropy_bits(len(password),
                        lower=any(c.islower() for c in password),
                        upper=any(c.isupper() for c in password),
                        digits=any(c.isdigit() for c in password),
                        symbols=any(not c.isalnum() for c in password))
    reasons = weakness_reasons(password)
    if "weak_common" in reasons or "weak_repeat" in reasons:
        bits /= 3
    return bits


# Пароли, которые первыми пробуют при взломе (самые частые в утечках)
COMMON = ["password", "пароль", "qwerty", "йцукен", "123456", "111111", "abc123",
          "admin", "letmein", "welcome", "iloveyou", "monkey", "dragon", "asdfgh"]


def weakness_reasons(password, min_length=12):
    """Список причин, почему пароль слабый (ключи для texts.py). Пусто — пароль нормальный."""
    reasons = []
    if len(password) < min_length:
        reasons.append("weak_short")
    lowered = password.lower()
    if any(word in lowered for word in COMMON):
        reasons.append("weak_common")
    kinds = sum([any(c.islower() for c in password),
                 any(c.isupper() for c in password),
                 any(c.isdigit() for c in password),
                 any(not c.isalnum() for c in password)])
    if kinds <= 1:
        reasons.append("weak_one_kind")
    # один и тот же символ 4 раза подряд: aaaa, 1111
    if any(password[i] * 4 == password[i:i + 4] for i in range(len(password) - 3)):
        reasons.append("weak_repeat")
    return reasons
