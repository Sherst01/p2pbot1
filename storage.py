"""
Хранилище данных бота на SQLite (через aiosqlite, без ORM — просто и надёжно).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import aiosqlite

from config import DB_PATH, DEFAULT_TEMPLATES

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    subscribed_until TEXT,     -- ISO дата окончания подписки, NULL если нет подписки
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    amount_fiat REAL NOT NULL,
    buy_price REAL,
    sell_price REAL,
    bank TEXT,
    commission_percent REAL,
    profit REAL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    method TEXT NOT NULL,       -- 'sbp' | 'card' | 'stars'
    amount TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | confirmed | rejected
    screenshot_file_id TEXT,
    created_at TEXT NOT NULL
);
"""


@dataclass
class Deal:
    id: int
    user_id: int
    ts: str
    amount_fiat: float
    buy_price: float | None
    sell_price: float | None
    bank: str | None
    commission_percent: float | None
    profit: float | None
    note: str | None


@dataclass
class Template:
    id: int
    user_id: int
    title: str
    body: str


@dataclass
class Payment:
    id: int
    user_id: int
    method: str
    amount: str | None
    status: str
    screenshot_file_id: str | None
    created_at: str


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def ensure_user(user_id: int, username: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
        exists = await cur.fetchone()
        if not exists:
            await db.execute(
                "INSERT INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
                (user_id, username, dt.datetime.utcnow().isoformat()),
            )
            for title, body in DEFAULT_TEMPLATES:
                await db.execute(
                    "INSERT INTO templates (user_id, title, body) VALUES (?, ?, ?)",
                    (user_id, title, body),
                )
            await db.commit()
        else:
            await db.execute(
                "UPDATE users SET username=? WHERE user_id=?", (username, user_id)
            )
            await db.commit()


async def is_subscribed(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT subscribed_until FROM users WHERE user_id=?", (user_id,)
        )
        row = await cur.fetchone()
        if not row or not row[0]:
            return False
        return dt.datetime.fromisoformat(row[0]) > dt.datetime.utcnow()


async def subscribed_until(user_id: int) -> dt.datetime | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT subscribed_until FROM users WHERE user_id=?", (user_id,)
        )
        row = await cur.fetchone()
        if not row or not row[0]:
            return None
        return dt.datetime.fromisoformat(row[0])


async def extend_subscription(user_id: int, days: int) -> dt.datetime:
    current = await subscribed_until(user_id)
    base = current if current and current > dt.datetime.utcnow() else dt.datetime.utcnow()
    new_until = base + dt.timedelta(days=days)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET subscribed_until=? WHERE user_id=?",
            (new_until.isoformat(), user_id),
        )
        await db.commit()
    return new_until


# ---------- Сделки ----------

async def add_deal(
    user_id: int,
    amount_fiat: float,
    buy_price: float | None,
    sell_price: float | None,
    bank: str | None,
    commission_percent: float | None,
    profit: float | None,
    note: str | None = None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO deals
               (user_id, ts, amount_fiat, buy_price, sell_price, bank, commission_percent, profit, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                dt.datetime.utcnow().isoformat(),
                amount_fiat,
                buy_price,
                sell_price,
                bank,
                commission_percent,
                profit,
                note,
            ),
        )
        await db.commit()
        return cur.lastrowid


async def deals_stats(user_id: int, since: dt.datetime) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT COUNT(*), COALESCE(SUM(profit), 0), COALESCE(SUM(amount_fiat), 0)
               FROM deals WHERE user_id=? AND ts >= ?""",
            (user_id, since.isoformat()),
        )
        count, profit_sum, volume_sum = await cur.fetchone()
        return {"count": count, "profit": profit_sum, "volume": volume_sum}


async def list_deals(user_id: int, limit: int = 10) -> list[Deal]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM deals WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cur.fetchall()
        return [Deal(**dict(r)) for r in rows]


# ---------- Шаблоны ----------

async def list_templates(user_id: int) -> list[Template]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM templates WHERE user_id=? ORDER BY id", (user_id,)
        )
        rows = await cur.fetchall()
        return [Template(**dict(r)) for r in rows]


async def add_template(user_id: int, title: str, body: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO templates (user_id, title, body) VALUES (?, ?, ?)",
            (user_id, title, body),
        )
        await db.commit()
        return cur.lastrowid


async def delete_template(template_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM templates WHERE id=? AND user_id=?", (template_id, user_id)
        )
        await db.commit()
        return cur.rowcount > 0


# ---------- Платежи ----------

async def create_payment(user_id: int, method: str, amount: str | None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO payments (user_id, method, amount, created_at) VALUES (?, ?, ?, ?)",
            (user_id, method, amount, dt.datetime.utcnow().isoformat()),
        )
        await db.commit()
        return cur.lastrowid


async def attach_screenshot(payment_id: int, file_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET screenshot_file_id=? WHERE id=?", (file_id, payment_id)
        )
        await db.commit()


async def set_payment_status(payment_id: int, status: str) -> Payment | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE payments SET status=? WHERE id=?", (status, payment_id)
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM payments WHERE id=?", (payment_id,))
        row = await cur.fetchone()
        return Payment(**dict(row)) if row else None


async def get_payment(payment_id: int) -> Payment | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM payments WHERE id=?", (payment_id,))
        row = await cur.fetchone()
        return Payment(**dict(row)) if row else None


async def pending_payments() -> list[Payment]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM payments WHERE status='pending' ORDER BY id"
        )
        rows = await cur.fetchall()
        return [Payment(**dict(r)) for r in rows]


# ---------- Общая статистика для админа ----------

async def total_users() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        (count,) = await cur.fetchone()
        return count


async def total_subscribers() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM users WHERE subscribed_until > ?",
            (dt.datetime.utcnow().isoformat(),),
        )
        (count,) = await cur.fetchone()
        return count


async def all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users")
        rows = await cur.fetchall()
        return [r[0] for r in rows]
