from __future__ import annotations

import asyncio
import datetime as dt
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    LabeledPrice,
    PreCheckoutQuery,
)

import config
import storage
import keyboards as kb
from bybit_p2p import BybitP2PClient
import calculator

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

router = Router()

# Дефолтный список банков для сравнения. Отредактируй под себя.
DEFAULT_BANKS = [
    ("Сбербанк", 0.0),
    ("Т-Банк", 0.0),
    ("СБП (любой банк)", 0.5),
    ("Альфа-Банк", 1.0),
]


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


# ---------------- FSM состояния ----------------

class CalcStates(StatesGroup):
    waiting_amount = State()
    waiting_manual_price = State()
    waiting_markup = State()


class DealStates(StatesGroup):
    waiting_amount = State()
    waiting_buy_price = State()
    waiting_sell_price = State()
    waiting_bank = State()


class TemplateStates(StatesGroup):
    waiting_title = State()
    waiting_body = State()


class BroadcastStates(StatesGroup):
    waiting_text = State()


class PaymentStates(StatesGroup):
    waiting_screenshot = State()


# ---------------- Старт / меню ----------------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await storage.ensure_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "Привет! Это твой помощник для P2P-сделок.\n\n"
        "🧮 Быстрый расчёт курса и прибыли\n"
        "💬 Готовые шаблоны ответов клиенту\n"
        "📒 Учёт сделок и статистика\n\n"
        "Выбирай раздел:",
        reply_markup=kb.main_menu(is_admin(message.from_user.id)),
    )


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "Главное меню:", reply_markup=kb.main_menu(is_admin(call.from_user.id))
    )
    await call.answer()


# ---------------- Быстрый расчёт ----------------

@router.callback_query(F.data == "calc:start")
async def cb_calc_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(CalcStates.waiting_amount)
    await call.message.edit_text(
        "Введи сумму сделки (в USDT):", reply_markup=kb.back_to_menu()
    )
    await call.answer()


@router.message(CalcStates.waiting_amount)
async def calc_got_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Не понял число, попробуй ещё раз (например: 100):")
        return
    await state.update_data(amount=amount)
    await message.answer(
        "Откуда взять рыночный курс?", reply_markup=kb.calc_source_kb()
    )
    await state.set_state(None)


@router.callback_query(F.data == "calc:auto_price")
async def cb_calc_auto_price(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data.get("amount")
    if amount is None:
        await call.answer("Сначала введи сумму", show_alert=True)
        return
    await call.answer("Запрашиваю курс с Bybit…")
    try:
        async with BybitP2PClient() as client:
            price = await client.best_price("USDT", "RUB", "sell")
    except Exception as e:
        log.warning("Ошибка запроса к Bybit: %s", e)
        price = None

    if price is None:
        await call.message.edit_text(
            "Не удалось получить курс с Bybit. Введи курс вручную:",
            reply_markup=kb.back_to_menu(),
        )
        await state.set_state(CalcStates.waiting_manual_price)
        return

    await state.update_data(market_price=price)
    await call.message.edit_text(
        f"Курс с Bybit P2P (USDT/RUB): <b>{price:,.2f}</b>\n\n"
        "Теперь введи свою наценку в % (например: 1.5):".replace(",", " "),
        reply_markup=kb.back_to_menu(),
    )
    await state.set_state(CalcStates.waiting_markup)


@router.callback_query(F.data == "calc:manual_price")
async def cb_calc_manual_price(call: CallbackQuery, state: FSMContext):
    await state.set_state(CalcStates.waiting_manual_price)
    await call.message.edit_text(
        "Введи рыночный курс вручную:", reply_markup=kb.back_to_menu()
    )
    await call.answer()


@router.message(CalcStates.waiting_manual_price)
async def calc_got_manual_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Не понял число, попробуй ещё раз:")
        return
    await state.update_data(market_price=price)
    await message.answer("Теперь введи свою наценку в % (например: 1.5):")
    await state.set_state(CalcStates.waiting_markup)


@router.message(CalcStates.waiting_markup)
async def calc_got_markup(message: Message, state: FSMContext):
    try:
        markup = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Не понял число, попробуй ещё раз:")
        return

    data = await state.get_data()
    amount = data["amount"]
    market_price = data["market_price"]

    results = calculator.compare_banks(amount, market_price, markup, DEFAULT_BANKS)
    text = calculator.format_comparison(results) + "\n\n" + calculator.format_result(results[0])

    await message.answer(text, reply_markup=kb.back_to_menu())
    await state.clear()


# ---------------- Шаблоны ответов ----------------

@router.callback_query(F.data == "tpl:list")
async def cb_tpl_list(call: CallbackQuery, state: FSMContext):
    await state.clear()
    markup = await kb.templates_kb(call.from_user.id)
    await call.message.edit_text("💬 Шаблоны ответов:", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("tpl:send:"))
async def cb_tpl_send(call: CallbackQuery):
    template_id = int(call.data.split(":")[2])
    templates = await storage.list_templates(call.from_user.id)
    tpl = next((t for t in templates if t.id == template_id), None)
    if not tpl:
        await call.answer("Шаблон не найден", show_alert=True)
        return
    await call.message.answer(tpl.body)
    await call.answer("Скопируй текст выше и отправь клиенту 👆")


@router.callback_query(F.data == "tpl:add")
async def cb_tpl_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(TemplateStates.waiting_title)
    await call.message.edit_text(
        "Введи короткое название шаблона (например: «Оплата»):",
        reply_markup=kb.back_to_menu(),
    )
    await call.answer()


@router.message(TemplateStates.waiting_title)
async def tpl_got_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text[:50])
    await message.answer("Теперь введи текст шаблона:")
    await state.set_state(TemplateStates.waiting_body)


@router.message(TemplateStates.waiting_body)
async def tpl_got_body(message: Message, state: FSMContext):
    data = await state.get_data()
    await storage.add_template(message.from_user.id, data["title"], message.text)
    await state.clear()
    markup = await kb.templates_kb(message.from_user.id)
    await message.answer("Шаблон добавлен ✅", reply_markup=markup)


@router.callback_query(F.data.startswith("tpl:delete:"))
async def cb_tpl_delete(call: CallbackQuery):
    template_id = int(call.data.split(":")[2])
    await storage.delete_template(template_id, call.from_user.id)
    markup = await kb.templates_kb(call.from_user.id)
    await call.message.edit_text("Шаблон удалён. 💬 Шаблоны ответов:", reply_markup=markup)
    await call.answer()


# ---------------- Учёт сделок ----------------

@router.callback_query(F.data == "deals:menu")
async def cb_deals_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("📒 Учёт сделок:", reply_markup=kb.deals_menu_kb())
    await call.answer()


@router.callback_query(F.data == "deals:add")
async def cb_deals_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(DealStates.waiting_amount)
    await call.message.edit_text(
        "Сумма сделки (в USDT или фиате — как удобно):",
        reply_markup=kb.back_to_menu(),
    )
    await call.answer()


@router.message(DealStates.waiting_amount)
async def deal_got_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Не понял число, попробуй ещё раз:")
        return
    await state.update_data(amount=amount)
    await message.answer("Курс покупки:")
    await state.set_state(DealStates.waiting_buy_price)


@router.message(DealStates.waiting_buy_price)
async def deal_got_buy(message: Message, state: FSMContext):
    try:
        buy_price = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Не понял число, попробуй ещё раз:")
        return
    await state.update_data(buy_price=buy_price)
    await message.answer("Курс продажи:")
    await state.set_state(DealStates.waiting_sell_price)


@router.message(DealStates.waiting_sell_price)
async def deal_got_sell(message: Message, state: FSMContext):
    try:
        sell_price = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Не понял число, попробуй ещё раз:")
        return
    await state.update_data(sell_price=sell_price)
    await message.answer("Банк/способ оплаты (можно просто название):")
    await state.set_state(DealStates.waiting_bank)


@router.message(DealStates.waiting_bank)
async def deal_got_bank(message: Message, state: FSMContext):
    data = await state.get_data()
    amount = data["amount"]
    buy_price = data["buy_price"]
    sell_price = data["sell_price"]
    bank = message.text[:50]
    profit = amount * (sell_price - buy_price)

    await storage.add_deal(
        message.from_user.id, amount, buy_price, sell_price, bank, None, profit
    )
    await state.clear()
    await message.answer(
        f"Сделка записана ✅\n"
        f"Сумма: {amount:,.2f}\nКупил по: {buy_price:,.4f}\nПродал по: {sell_price:,.4f}\n"
        f"Банк: {bank}\n💰 Прибыль: <b>{profit:,.2f}</b>".replace(",", " "),
        reply_markup=kb.deals_menu_kb(),
    )


@router.callback_query(F.data.startswith("deals:stats:"))
async def cb_deals_stats(call: CallbackQuery):
    days = int(call.data.split(":")[2])
    since = dt.datetime.utcnow() - dt.timedelta(days=days)
    stats = await storage.deals_stats(call.from_user.id, since)
    period = {1: "день", 7: "неделю", 30: "месяц"}.get(days, f"{days} дн.")
    await call.message.edit_text(
        f"📈 Статистика за {period}:\n\n"
        f"Сделок: {stats['count']}\n"
        f"Оборот: {stats['volume']:,.2f}\n"
        f"Прибыль: <b>{stats['profit']:,.2f}</b>".replace(",", " "),
        reply_markup=kb.deals_menu_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "deals:last")
async def cb_deals_last(call: CallbackQuery):
    deals = await storage.list_deals(call.from_user.id, limit=10)
    if not deals:
        await call.message.edit_text("Сделок пока нет.", reply_markup=kb.deals_menu_kb())
        await call.answer()
        return
    lines = ["📋 <b>Последние сделки:</b>\n"]
    for d in deals:
        date_str = dt.datetime.fromisoformat(d.ts).strftime("%d.%m %H:%M")
        lines.append(
            f"{date_str} — {d.amount_fiat:,.2f} @ {d.bank or '—'}, "
            f"прибыль {d.profit:,.2f}".replace(",", " ")
        )
    await call.message.edit_text("\n".join(lines), reply_markup=kb.deals_menu_kb())
    await call.answer()


# ---------------- Подписка / платежи ----------------

@router.callback_query(F.data == "sub:menu")
async def cb_sub_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    subscribed = await storage.is_subscribed(call.from_user.id)
    if subscribed:
        until = await storage.subscribed_until(call.from_user.id)
        text = f"⭐️ У тебя активна подписка до <b>{until.strftime('%d.%m.%Y')}</b>."
    else:
        text = (
            f"⭐️ Подписка открывает полный доступ ко всем функциям.\n\n"
            f"Стоимость: <b>{config.SUBSCRIPTION_PRICE_RUB} ₽</b> "
            f"или <b>{config.SUBSCRIPTION_PRICE_STARS} ⭐</b> "
            f"за {config.SUBSCRIPTION_DAYS} дней.\n\n"
            "Выбери способ оплаты:"
        )
    await call.message.edit_text(text, reply_markup=kb.subscription_kb(subscribed))
    await call.answer()


@router.callback_query(F.data == "sub:pay:stars")
async def cb_sub_pay_stars(call: CallbackQuery):
    await call.message.answer_invoice(
        title="Подписка на P2P-помощника",
        description=f"Доступ на {config.SUBSCRIPTION_DAYS} дней",
        payload=f"subscription:{call.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label="Подписка", amount=config.SUBSCRIPTION_PRICE_STARS)],
    )
    await call.answer()


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    until = await storage.extend_subscription(message.from_user.id, config.SUBSCRIPTION_DAYS)
    await message.answer(
        f"Оплата получена ✅ Подписка активна до <b>{until.strftime('%d.%m.%Y')}</b>.",
        reply_markup=kb.main_menu(is_admin(message.from_user.id)),
    )


@router.callback_query(F.data.in_({"sub:pay:card", "sub:pay:sbp"}))
async def cb_sub_pay_manual(call: CallbackQuery):
    method = "card" if call.data.endswith("card") else "sbp"
    payment_id = await storage.create_payment(
        call.from_user.id, method, str(config.SUBSCRIPTION_PRICE_RUB)
    )

    if method == "card":
        requisites = (
            f"💳 Номер карты: <code>{config.CARD_NUMBER or 'не задано в конфиге'}</code>\n"
            f"Получатель: {config.CARD_HOLDER or '—'}"
        )
    else:
        requisites = (
            f"📱 Номер телефона (СБП): <code>{config.SBP_PHONE or 'не задано в конфиге'}</code>\n"
            f"Банк: {config.SBP_BANK or '—'}"
        )

    await call.message.edit_text(
        f"Сумма к оплате: <b>{config.SUBSCRIPTION_PRICE_RUB} ₽</b>\n\n{requisites}\n\n"
        "После оплаты нажми кнопку ниже и пришли скриншот/чек перевода.",
        reply_markup=kb.confirm_payment_kb(payment_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("sub:sendcheck:"))
async def cb_sub_sendcheck(call: CallbackQuery, state: FSMContext):
    payment_id = int(call.data.split(":")[2])
    await state.update_data(pending_payment_id=payment_id)
    await state.set_state(PaymentStates.waiting_screenshot)
    await call.message.edit_text(
        "Пришли, пожалуйста, скриншот или файл чека одним сообщением.",
        reply_markup=kb.back_to_menu(),
    )
    await call.answer()


@router.message(PaymentStates.waiting_screenshot, F.photo | F.document)
async def got_payment_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    payment_id = data.get("pending_payment_id")
    if not payment_id:
        await message.answer("Не нашёл ожидающий платёж, начни заново через /start")
        await state.clear()
        return

    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    await storage.attach_screenshot(payment_id, file_id)
    payment = await storage.get_payment(payment_id)
    await state.clear()

    await message.answer(
        "Чек получен, отправил админу на проверку ✅ Как только подтвердят — подписка активируется автоматически.",
        reply_markup=kb.main_menu(is_admin(message.from_user.id)),
    )

    caption = (
        f"🧾 Новый платёж #{payment_id}\n"
        f"От: {message.from_user.full_name} (@{message.from_user.username or '—'}, id {message.from_user.id})\n"
        f"Способ: {payment.method}\nСумма: {payment.amount} ₽"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            if message.photo:
                await message.bot.send_photo(
                    admin_id, file_id, caption=caption, reply_markup=kb.admin_review_kb(payment_id)
                )
            else:
                await message.bot.send_document(
                    admin_id, file_id, caption=caption, reply_markup=kb.admin_review_kb(payment_id)
                )
        except Exception as e:
            log.warning("Не удалось уведомить админа %s: %s", admin_id, e)


# ---------------- Админ-панель ----------------

@router.callback_query(F.data == "admin:menu")
async def cb_admin_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Недоступно", show_alert=True)
        return
    await state.clear()
    await call.message.edit_text("🛠 Админ-панель:", reply_markup=kb.admin_menu_kb())
    await call.answer()


@router.callback_query(F.data == "admin:pending")
async def cb_admin_pending(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Недоступно", show_alert=True)
        return
    payments = await storage.pending_payments()
    if not payments:
        await call.message.edit_text("Нет ожидающих платежей.", reply_markup=kb.admin_menu_kb())
        await call.answer()
        return
    for p in payments:
        caption = f"🧾 Платёж #{p.id} от user {p.user_id}\nСпособ: {p.method}\nСумма: {p.amount}"
        if p.screenshot_file_id:
            await call.message.answer_photo(
                p.screenshot_file_id, caption=caption, reply_markup=kb.admin_review_kb(p.id)
            )
        else:
            await call.message.answer(
                caption + "\n(чек ещё не прислан)", reply_markup=kb.admin_review_kb(p.id)
            )
    await call.answer()


@router.callback_query(F.data.startswith("admin:approve:"))
async def cb_admin_approve(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Недоступно", show_alert=True)
        return
    payment_id = int(call.data.split(":")[2])
    payment = await storage.set_payment_status(payment_id, "confirmed")
    if payment:
        until = await storage.extend_subscription(payment.user_id, config.SUBSCRIPTION_DAYS)
        try:
            await call.bot.send_message(
                payment.user_id,
                f"Оплата подтверждена ✅ Подписка активна до <b>{until.strftime('%d.%m.%Y')}</b>.",
            )
        except Exception as e:
            log.warning("Не удалось уведомить пользователя: %s", e)
    await call.message.edit_caption(caption=(call.message.caption or "") + "\n\n✅ Подтверждено")
    await call.answer("Подтверждено")


@router.callback_query(F.data.startswith("admin:reject:"))
async def cb_admin_reject(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Недоступно", show_alert=True)
        return
    payment_id = int(call.data.split(":")[2])
    payment = await storage.set_payment_status(payment_id, "rejected")
    if payment:
        try:
            await call.bot.send_message(
                payment.user_id, "Оплата не подтверждена ❌ Свяжись с админом, если это ошибка."
            )
        except Exception as e:
            log.warning("Не удалось уведомить пользователя: %s", e)
    await call.message.edit_caption(caption=(call.message.caption or "") + "\n\n❌ Отклонено")
    await call.answer("Отклонено")


@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Недоступно", show_alert=True)
        return
    users = await storage.total_users()
    subs = await storage.total_subscribers()
    await call.message.edit_text(
        f"📊 Всего пользователей: {users}\nАктивных подписок: {subs}",
        reply_markup=kb.admin_menu_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "admin:broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Недоступно", show_alert=True)
        return
    await state.set_state(BroadcastStates.waiting_text)
    await call.message.edit_text(
        "Пришли текст рассылки одним сообщением:", reply_markup=kb.back_to_menu()
    )
    await call.answer()


@router.message(BroadcastStates.waiting_text)
async def admin_got_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    user_ids = await storage.all_user_ids()
    sent, failed = 0, 0
    status = await message.answer(f"Рассылаю на {len(user_ids)} пользователей…")
    for uid in user_ids:
        try:
            await message.bot.copy_message(uid, message.chat.id, message.message_id)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # чтобы не упереться в лимиты Telegram
    await status.edit_text(f"Готово ✅ Отправлено: {sent}, ошибок: {failed}")


# ---------------- Запуск ----------------

async def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN в переменных окружения")

    await storage.init_db()

    bot = Bot(token=config.BOT_TOKEN, parse_mode="HTML")
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
