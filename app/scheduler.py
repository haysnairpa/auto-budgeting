from apscheduler.schedulers.background import BackgroundScheduler
from . import database, gmail
from .parsers import dispatch

_scheduler = BackgroundScheduler(timezone="Asia/Jakarta")


def sync_now() -> int:
    """Pull latest banking emails and store new transactions. Returns count of new rows."""
    emails = gmail.fetch_new_emails(max_results=50)
    new_count = 0
    for email_id, sender, subject, html in emails:
        bank = gmail.detect_bank(sender, html)
        if not bank:
            continue
        tx = dispatch(bank, email_id, subject, html)
        if tx and database.insert_transaction(tx):
            new_count += 1
            print(f"[sync] +1 {bank} | {tx.get('merchant')} | {tx.get('amount')}")
    return new_count


def _job():
    try:
        n = sync_now()
        if n:
            print(f"[scheduler] synced {n} new transaction(s)")
    except ValueError:
        pass  # not authenticated yet
    except Exception as e:
        print(f"[scheduler] error: {e}")


def start():
    _scheduler.add_job(_job, "interval", minutes=15, id="email_sync", replace_existing=True)
    _scheduler.start()
    print("[scheduler] started — polling every 15 min")


def stop():
    _scheduler.shutdown(wait=False)
