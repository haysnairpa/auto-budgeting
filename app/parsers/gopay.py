"""
Parser for GoPay transaction notification emails.

GoPay emails show:
    BERHASIL                   11 Jun 2026, 22:16
    ID Pembayaran - ...
    PLN Token                  Rp21.400        ← service + total on same "row"
    ...
    TOTAL BAYAR                RP19.500        ← base amount (before admin fee)
    Total                      Rp21.400        ← final amount charged

We use "Total" (final) as the transaction amount and the service name
(the line that appears right before the first Rp amount) as the merchant.
"""
import re
from bs4 import BeautifulSoup

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse(email_id: str, subject: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    lines = [l.strip() for l in soup.get_text("\n").splitlines() if l.strip()]

    amount = _find_total(lines)
    if amount is None:
        return None

    merchant = _find_merchant(lines)
    tx_date = _find_date(lines)

    return {
        "email_id": email_id,
        "bank": "GoPay",
        "amount": amount,
        "merchant": merchant or "GoPay Payment",
        "transaction_type": "Payment",
        "transaction_date": tx_date,
        "status": "Successful",
        "raw_subject": subject,
    }


def _find_total(lines: list[str]) -> int | None:
    """
    Look for the final "Total" line followed by an Rp amount.
    Falls back to the first Rp amount found near a TOTAL keyword.
    """
    for i, line in enumerate(lines):
        if line.strip().lower() == "total" and i + 1 < len(lines):
            amount = _parse_rp(lines[i + 1])
            if amount:
                return amount
        # "Total   Rp21.400" on a single line
        if re.match(r"^total\b", line, re.IGNORECASE):
            amount = _parse_rp(line)
            if amount:
                return amount

    # Fallback: TOTAL BAYAR
    for i, line in enumerate(lines):
        if "total bayar" in line.lower():
            amount = _parse_rp(line) or (
                _parse_rp(lines[i + 1]) if i + 1 < len(lines) else None
            )
            if amount:
                return amount

    return None


def _find_merchant(lines: list[str]) -> str | None:
    """
    The service/merchant name appears just before the first "Rp…" amount
    after the payment ID line.
    """
    past_id = False
    for i, line in enumerate(lines):
        if "id pembayaran" in line.lower() or "id payment" in line.lower():
            past_id = True
            continue
        if past_id and re.search(r"Rp[\d.,]+", line, re.IGNORECASE):
            # The name is on the same line (before Rp) or the previous line
            name_inline = re.sub(r"\s*Rp[\d.,]+.*", "", line, flags=re.IGNORECASE).strip()
            if name_inline:
                return name_inline
            if i > 0:
                return lines[i - 1]
    return None


def _find_date(lines: list[str]) -> str | None:
    """'11 Jun 2026, 22:16'  →  '2026-06-11 22:16:00'"""
    for line in lines:
        m = re.search(
            r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})[,\s]+(\d{2}:\d{2})",
            line,
        )
        if m:
            day, mon_str, year, hm = m.groups()
            month = _MONTHS.get(mon_str[:3].lower())
            if month:
                return f"{year}-{month:02d}-{int(day):02d} {hm}:00"
    return None


def _parse_rp(text: str) -> int | None:
    """
    'Rp21.400' or 'RP19.500' or 'Rp 21,400'  →  integer rupiah.
    In Indonesian formatting, dots are thousand separators.
    """
    m = re.search(r"Rp\.?\s*([\d.,]+)", text, re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).replace(".", "").replace(",", "")
    try:
        return int(raw)
    except ValueError:
        return None
