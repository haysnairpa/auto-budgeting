from . import database, gmail
from .parsers import dispatch


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
