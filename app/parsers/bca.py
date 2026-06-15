"""
Parser for BCA transaction notification emails.

BCA emails contain a label : value table, e.g.
    Status               : Successful
    Transaction Date     : 31 May 2026 17:56:32
    Transaction Type     : QRIS Payment
    Payment to           : AYAM BAKAR MA YUYUM BNI
    Total Payment        : IDR 19,000.00
"""
import re
from bs4 import BeautifulSoup

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse(email_id: str, subject: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    fields = _extract_fields(soup)

    amount = _parse_idr(fields.get("Total Payment", ""))
    if amount is None:
        return None

    merchant = (
        fields.get("Payment to")
        or fields.get("Transfer to")
        or fields.get("Beneficiary Name")
        or fields.get("Merchant Name")
        or ""
    ).strip()

    return {
        "email_id": email_id,
        "bank": "BCA",
        "amount": amount,
        "merchant": merchant,
        "transaction_type": fields.get("Transaction Type", "").strip(),
        "transaction_date": _parse_date(fields.get("Transaction Date", "")),
        "status": fields.get("Status", "").strip(),
        "raw_subject": subject,
    }


def _extract_fields(soup: BeautifulSoup) -> dict:
    """
    Try table-cell extraction first, then fall back to line-based text parsing.
    Handles both 2-column tables and plain "Key : Value" text lines.
    """
    fields: dict[str, str] = {}

    # Method 1: table rows with 2–3 cells
    for row in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in row.find_all(["td", "th"])]
        if len(cells) == 2:
            key, val = cells
            val = re.sub(r"^\s*:\s*", "", val)
            if key and val:
                fields[key.strip()] = val.strip()
        elif len(cells) == 3 and cells[1].strip() == ":":
            if cells[0] and cells[2]:
                fields[cells[0].strip()] = cells[2].strip()

    if fields.get("Total Payment"):
        return fields

    # Method 2: plain text line parsing
    text = soup.get_text("\n")
    for line in text.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # Skip lines where key looks like a URL or timestamp fragment
        if key and val and len(key) < 40 and not key.startswith("http"):
            fields.setdefault(key, val)

    return fields


def _parse_idr(text: str) -> int | None:
    """'IDR 19,000.00'  →  19000"""
    m = re.search(r"IDR\s*([\d,]+)", text, re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1).replace(",", "").split(".")[0])


def _parse_date(text: str) -> str | None:
    """'31 May 2026 17:56:32'  →  '2026-05-31 17:56:32'"""
    m = re.match(
        r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s+(\d{2}:\d{2}:\d{2})",
        text.strip(),
    )
    if not m:
        return None
    day, mon_str, year, time = m.groups()
    month = _MONTHS.get(mon_str[:3].lower())
    if not month:
        return None
    return f"{year}-{month:02d}-{int(day):02d} {time}"
