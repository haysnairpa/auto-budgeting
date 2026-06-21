import os
from contextlib import contextmanager
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")


@contextmanager
def _conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id               SERIAL PRIMARY KEY,
                    email_id         TEXT UNIQUE NOT NULL,
                    bank             TEXT NOT NULL,
                    amount           INTEGER NOT NULL,
                    merchant         TEXT,
                    transaction_type TEXT,
                    transaction_date TEXT,
                    status           TEXT,
                    raw_subject      TEXT,
                    created_at       TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sync_state (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)


def insert_transaction(data: dict) -> bool:
    """Returns True if inserted as new, False if already exists."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO transactions
                        (email_id, bank, amount, merchant, transaction_type,
                         transaction_date, status, raw_subject)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        data["email_id"], data["bank"], data["amount"],
                        data.get("merchant"), data.get("transaction_type"),
                        data.get("transaction_date"), data.get("status"),
                        data.get("raw_subject"),
                    ),
                )
        return True
    except psycopg2.errors.UniqueViolation:
        return False


def get_transactions(limit: int = 100, offset: int = 0,
                     month: int = None, year: int = None) -> list[dict]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            params: list = []
            where = ""
            if month and year:
                where = "WHERE LEFT(transaction_date, 7) = %s"
                params.append(f"{year}-{month:02d}")
            cur.execute(
                f"SELECT * FROM transactions {where} "
                f"ORDER BY transaction_date DESC NULLS LAST LIMIT %s OFFSET %s",
                params + [limit, offset],
            )
            return [dict(r) for r in cur.fetchall()]


def get_monthly_summary(year: int, month: int) -> dict:
    ym = f"{year}-{month:02d}"
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT bank, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total
                FROM transactions
                WHERE LEFT(transaction_date, 7) = %s
                GROUP BY bank
                """,
                (ym,),
            )
            by_bank = [dict(r) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total
                FROM transactions
                WHERE LEFT(transaction_date, 7) = %s
                """,
                (ym,),
            )
            totals = dict(cur.fetchone())

    return {
        "month": ym,
        "total": totals["total"],
        "count": totals["count"],
        "by_bank": by_bank,
    }


def get_monthly_totals() -> list[dict]:
    """Last 6 months of spending totals."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT LEFT(transaction_date, 7) AS month,
                       COUNT(*) AS count,
                       SUM(amount) AS total
                FROM transactions
                WHERE transaction_date IS NOT NULL
                GROUP BY month
                ORDER BY month DESC
                LIMIT 6
                """
            )
            return [dict(r) for r in cur.fetchall()]
