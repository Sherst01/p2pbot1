"""
Клиент для публичного API объявлений Bybit P2P.

Использует открытый (не требующий авторизации) эндпоинт, которым
пользуется сам веб-интерфейс Bybit для отображения ленты объявлений:
POST https://api2.bybit.com/fiat/otc/item/online

Никакие приватные/торговые действия здесь не выполняются — это
только чтение публичного списка объявлений (аналог открытия страницы
P2P в браузере).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import aiohttp

log = logging.getLogger(__name__)

BYBIT_P2P_ONLINE_URL = "https://api2.bybit.com/fiat/otc/item/online"

Side = Literal["buy", "sell"]

# side в запросе Bybit: "1" = продавцы (мы покупаем), "0" = покупатели (мы продаём)
_SIDE_MAP = {"buy": "1", "sell": "0"}


@dataclass
class P2PAd:
    nickname: str
    price: float
    available_qty: float
    min_amount: float
    max_amount: float
    payments: list[str]
    order_completion_rate: float | None
    finish_num: int | None

    @property
    def payments_str(self) -> str:
        return ", ".join(self.payments) if self.payments else "—"


class BybitP2PClient:
    def __init__(self, session: aiohttp.ClientSession | None = None):
        self._session = session
        self._own_session = session is None

    async def __aenter__(self) -> "BybitP2PClient":
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *exc):
        if self._own_session and self._session:
            await self._session.close()

    async def get_ads(
        self,
        token_id: str = "USDT",
        currency_id: str = "RUB",
        side: Side = "buy",
        page: int = 1,
        size: int = 10,
        payment_ids: list[str] | None = None,
    ) -> list[P2PAd]:
        """Возвращает список объявлений, отсортированный биржей по цене (лучшие первыми)."""
        if self._session is None:
            raise RuntimeError("Используйте 'async with BybitP2PClient() as client'")

        payload = {
            "userId": "",
            "tokenId": token_id,
            "currencyId": currency_id,
            "payment": payment_ids or [],
            "side": _SIDE_MAP[side],
            "size": str(size),
            "page": str(page),
            "amount": "",
            "authMaker": False,
            "canTrade": False,
        }
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (compatible; P2PMonitorBot/1.0)",
        }

        async with self._session.post(
            BYBIT_P2P_ONLINE_URL, json=payload, headers=headers, timeout=15
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

        if data.get("ret_code") != 0:
            log.warning("Bybit P2P вернул ошибку: %s", data.get("ret_msg"))
            return []

        items = (data.get("result") or {}).get("items") or []
        ads: list[P2PAd] = []
        for it in items:
            try:
                ads.append(
                    P2PAd(
                        nickname=it.get("nickName", "—"),
                        price=float(it["price"]),
                        available_qty=float(it.get("lastQuantity", 0)),
                        min_amount=float(it.get("minAmount", 0)),
                        max_amount=float(it.get("maxAmount", 0)),
                        payments=[
                            p.get("paymentType", "") for p in it.get("payments", [])
                        ]
                        if isinstance(it.get("payments"), list)
                        else [],
                        order_completion_rate=(
                            float(it["recentExecuteRate"]) / 100
                            if it.get("recentExecuteRate")
                            else None
                        ),
                        finish_num=it.get("finishNum"),
                    )
                )
            except (KeyError, ValueError, TypeError) as e:
                log.debug("Пропускаю некорректное объявление: %s", e)
                continue
        return ads

    async def best_price(
        self, token_id: str = "USDT", currency_id: str = "RUB", side: Side = "buy"
    ) -> float | None:
        ads = await self.get_ads(token_id, currency_id, side, size=1)
        return ads[0].price if ads else None
