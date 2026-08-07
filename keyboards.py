from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

import storage


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🧮 Быстрый расчёт", callback_data="calc:start")
    b.button(text="💬 Шаблоны ответов", callback_data="tpl:list")
    b.button(text="📒 Учёт сделок", callback_data="deals:menu")
    b.button(text="⭐️ Подписка", callback_data="sub:menu")
    if is_admin:
        b.button(text="🛠 Админ-панель", callback_data="admin:menu")
    b.adjust(1)
    return b.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ В меню", callback_data="menu")
    return b.as_markup()


def calc_source_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📡 Взять курс с Bybit P2P", callback_data="calc:auto_price")
    b.button(text="✍️ Ввести курс вручную", callback_data="calc:manual_price")
    b.button(text="⬅️ В меню", callback_data="menu")
    b.adjust(1)
    return b.as_markup()


async def templates_kb(user_id: int) -> InlineKeyboardMarkup:
    templates = await storage.list_templates(user_id)
    b = InlineKeyboardBuilder()
    for t in templates:
        b.button(text=t.title, callback_data=f"tpl:send:{t.id}")
    b.button(text="➕ Добавить шаблон", callback_data="tpl:add")
    b.button(text="⬅️ В меню", callback_data="menu")
    b.adjust(1)
    return b.as_markup()


def template_actions_kb(template_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🗑 Удалить", callback_data=f"tpl:delete:{template_id}")
    b.button(text="⬅️ К шаблонам", callback_data="tpl:list")
    b.adjust(1)
    return b.as_markup()


def deals_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Записать сделку", callback_data="deals:add")
    b.button(text="📈 Статистика за день", callback_data="deals:stats:1")
    b.button(text="📈 Статистика за неделю", callback_data="deals:stats:7")
    b.button(text="📈 Статистика за месяц", callback_data="deals:stats:30")
    b.button(text="📋 Последние сделки", callback_data="deals:last")
    b.button(text="⬅️ В меню", callback_data="menu")
    b.adjust(1)
    return b.as_markup()


def subscription_kb(is_subscribed: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not is_subscribed:
        b.button(text="💳 Оплатить картой", callback_data="sub:pay:card")
        b.button(text="📱 Оплатить через СБП", callback_data="sub:pay:sbp")
        b.button(text="⭐️ Оплатить Telegram Stars", callback_data="sub:pay:stars")
    b.button(text="⬅️ В меню", callback_data="menu")
    b.adjust(1)
    return b.as_markup()


def confirm_payment_kb(payment_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Я оплатил, отправить чек", callback_data=f"sub:sendcheck:{payment_id}")
    b.button(text="⬅️ В меню", callback_data="menu")
    b.adjust(1)
    return b.as_markup()


def admin_review_kb(payment_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data=f"admin:approve:{payment_id}")
    b.button(text="❌ Отклонить", callback_data=f"admin:reject:{payment_id}")
    b.adjust(2)
    return b.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🧾 Ожидающие платежи", callback_data="admin:pending")
    b.button(text="📊 Общая статистика", callback_data="admin:stats")
    b.button(text="📢 Рассылка", callback_data="admin:broadcast")
    b.button(text="⬅️ В меню", callback_data="menu")
    b.adjust(1)
    return b.as_markup()
