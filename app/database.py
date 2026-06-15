import sqlite3
import os
from contextlib import contextmanager

DATA_DIR = os.environ.get("DATA_DIR", "./data")
DB_PATH = os.path.join(DATA_DIR, "budget.db")


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id         TEXT UNIQUE NOT NULL,
                bank             TEXT NOT NULL,
                amount           INTEGER NOT NULL,
                merchant         TEXT,
                transaction_type TEXT,
                transaction_date TEXT,
                status           TEXT,
                raw_subject      TEXT,
                created_at       TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_state (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_transaction(data: dict) -> bool:
    """Returns True if new, False if already stored."""
    try:
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO transactions
                    (email_id, bank, amount, merchant, transaction_type,
                     transaction_date, status, raw_subject)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["email_id"], data["bank"], data["amount"],
                    data.get("merchant"), data.get("transaction_type"),
                    data.get("transaction_date"), data.get("status"),
                    data.get("raw_subject"),
                ),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_transactions(limit: int = 100, offset: int = 0,
                     month: int = None, year: int = None) -> list[dict]:
    with _conn() as conn:
        params: list = []
        where = ""
        if month and year:
            where = "WHERE strftime('%Y-%m', transaction_date) = ?"
            params.append(f"{year}-{month:02d}")
        rows = conn.execute(
            f"SELECT * FROM transactions {where} "
            f"ORDER BY transaction_date DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return [dict(r) for r in rows]


def get_monthly_summary(year: int, month: int) -> dict:
    with _conn() as conn:
        ym = f"{year}-{month:02d}"
        rows = conn.execute(
            """
            SELECT bank, COUNT(*) AS count, SUM(amount) AS total
            FROM transactions
            WHERE strftime('%Y-%m', transaction_date) = ?
            GROUP BY bank
            """,
            (ym,),
        ).fetchall()
        totals = conn.execute(
            """
            SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE strftime('%Y-%m', transaction_date) = ?
            """,
            (ym,),
        ).fetchone()
    return {
        "month": ym,
        "total": totals["total"],
        "count": totals["count"],
        "by_bank": [dict(r) for r in rows],
    }


def get_monthly_totals() -> list[dict]:
    """Returns per-month totals for the last 6 months."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT strftime('%Y-%m', transaction_date) AS month,
                   COUNT(*) AS count,
                   SUM(amount) AS total
            FROM transactions
            GROUP BY month
            ORDER BY month DESC
            LIMIT 6
            """
        ).fetchall()
    return [dict(r) for r in rows]
