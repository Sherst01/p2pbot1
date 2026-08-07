"""
Расчёт итогового курса и прибыли по сделке P2P.

Логика:
- market_price — рыночный курс (например, лучшая цена на Bybit P2P)
- markup_percent — твоя наценка сверху рынка (в %)
- bank_commission_percent — комиссия банка/карты за перевод (в %)

final_rate = market_price * (1 + markup_percent/100)
итоговая сумма клиенту = amount * final_rate
комиссия банка = итоговая сумма * bank_commission_percent/100
чистая прибыль = итоговая сумма - amount*market_price - комиссия банка
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CalcResult:
    amount: float
    market_price: float
    markup_percent: float
    final_rate: float
    gross_total: float
    bank_commission_percent: float
    bank_commission_amount: float
    net_profit: float
    bank_name: str | None = None


def calculate(
    amount: float,
    market_price: float,
    markup_percent: float,
    bank_commission_percent: float = 0.0,
    bank_name: str | None = None,
) -> CalcResult:
    final_rate = market_price * (1 + markup_percent / 100)
    gross_total = amount * final_rate
    base_cost = amount * market_price
    bank_commission_amount = gross_total * (bank_commission_percent / 100)
    net_profit = gross_total - base_cost - bank_commission_amount

    return CalcResult(
        amount=amount,
        market_price=market_price,
        markup_percent=markup_percent,
        final_rate=final_rate,
        gross_total=gross_total,
        bank_commission_percent=bank_commission_percent,
        bank_commission_amount=bank_commission_amount,
        net_profit=net_profit,
        bank_name=bank_name,
    )


def compare_banks(
    amount: float,
    market_price: float,
    markup_percent: float,
    banks: list[tuple[str, float]],
) -> list[CalcResult]:
    """banks — список (название_банка, комиссия_в_процентах)."""
    results = [
        calculate(amount, market_price, markup_percent, commission, name)
        for name, commission in banks
    ]
    results.sort(key=lambda r: r.net_profit, reverse=True)
    return results


def format_result(r: CalcResult) -> str:
    lines = []
    if r.bank_name:
        lines.append(f"🏦 <b>{r.bank_name}</b>")
    lines.append(f"Сумма: {r.amount:,.2f}".replace(",", " "))
    lines.append(f"Рыночный курс: {r.market_price:,.4f}".replace(",", " "))
    lines.append(f"Курс с наценкой ({r.markup_percent:+.2f}%): <b>{r.final_rate:,.4f}</b>".replace(",", " "))
    lines.append(f"Итог клиенту: {r.gross_total:,.2f}".replace(",", " "))
    if r.bank_commission_percent:
        lines.append(
            f"Комиссия банка ({r.bank_commission_percent:.2f}%): -{r.bank_commission_amount:,.2f}".replace(",", " ")
        )
    lines.append(f"💰 Чистая прибыль: <b>{r.net_profit:,.2f}</b>".replace(",", " "))
    return "\n".join(lines)


def format_comparison(results: list[CalcResult]) -> str:
    lines = ["📊 <b>Сравнение банков</b>\n"]
    for i, r in enumerate(results, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        rate_str = f"{r.final_rate:,.4f}".replace(",", " ")
        profit_str = f"{r.net_profit:,.2f}".replace(",", " ")
        lines.append(f"{medal} {r.bank_name}: курс {rate_str}; прибыль {profit_str}")
    return "\n".join(lines)
