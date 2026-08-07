"""
Конфигурация. Все секреты берутся из переменных окружения —
никогда не хардкодь токен бота или реквизиты прямо в коде.
"""

from __future__ import annotations

import os

BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")

# ID администраторов бота (через запятую в переменной окружения ADMIN_IDS)
ADMIN_IDS: set[int] = {
    int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()
}

# Реквизиты для ручной оплаты подпиской
SBP_PHONE: str = os.environ.get("SBP_PHONE", "")
SBP_BANK: str = os.environ.get("SBP_BANK", "")
CARD_NUMBER: str = os.environ.get("CARD_NUMBER", "")
CARD_HOLDER: str = os.environ.get("CARD_HOLDER", "")

# Стоимость и срок подписки
SUBSCRIPTION_PRICE_RUB: int = int(os.environ.get("SUBSCRIPTION_PRICE_RUB", "999"))
SUBSCRIPTION_PRICE_STARS: int = int(os.environ.get("SUBSCRIPTION_PRICE_STARS", "500"))
SUBSCRIPTION_DAYS: int = int(os.environ.get("SUBSCRIPTION_DAYS", "30"))

DB_PATH: str = os.environ.get("DB_PATH", "p2p_assistant.sqlite3")

DEFAULT_TEMPLATES: list[tuple[str, str]] = [
    ("Оплата", "Оплатите, пожалуйста, в течение 15 минут и пришлите чек."),
    ("Чек", "Пришлите, пожалуйста, чек/скриншот перевода."),
    ("Ожидание", "Платёж пока не поступил, ожидаю зачисления."),
    ("Закрыто", "Сделка закрыта, спасибо! Хорошего дня 🙌"),
    ("Реквизиты", "Реквизиты для перевода: [укажите свои]."),
]
