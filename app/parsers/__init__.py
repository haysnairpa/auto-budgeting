from . import bca, gopay

_REGISTRY = {
    "BCA": bca.parse,
    "GoPay": gopay.parse,
}


def dispatch(bank: str, email_id: str, subject: str, html: str) -> dict | None:
    parser = _REGISTRY.get(bank)
    if not parser:
        return None
    try:
        return parser(email_id, subject, html)
    except Exception as e:
        print(f"[parser:{bank}] error on {email_id}: {e}")
        return None
