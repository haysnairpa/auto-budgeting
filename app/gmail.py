import os
import base64
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

DATA_DIR = os.environ.get("DATA_DIR", "./data")
TOKEN_PATH = os.path.join(DATA_DIR, "token.json")
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Gmail search query — catches BCA and GoPay notification emails
GMAIL_QUERY = (
    "from:bca.co.id OR from:klikbca.com OR "
    "from:gopay.co.id OR from:gojek.com"
)


def _client_config() -> dict:
    return {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [os.environ["REDIRECT_URI"]],
        }
    }


def get_flow(state: str = None) -> Flow:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        state=state,
        redirect_uri=os.environ["REDIRECT_URI"],
    )
    return flow


def get_credentials() -> Credentials | None:
    if not os.path.exists(TOKEN_PATH):
        return None
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
        except Exception:
            return None
    return creds if (creds and creds.valid) else None


def _save_credentials(creds: Credentials):
    os.makedirs(DATA_DIR, exist_ok=True)
    Path(TOKEN_PATH).write_text(creds.to_json())


def save_credentials_from_flow(flow: Flow):
    _save_credentials(flow.credentials)


def revoke():
    try:
        os.remove(TOKEN_PATH)
    except FileNotFoundError:
        pass


def _gmail_service():
    creds = get_credentials()
    if not creds:
        raise ValueError("Not authenticated with Gmail")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _decode_body(payload: dict) -> str:
    """Recursively find and decode the HTML body of an email part."""
    mime = payload.get("mimeType", "")
    if mime == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        result = _decode_body(part)
        if result:
            return result
    # Fallback: plain text
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    return ""


def _fetch_message(service, msg_id: str) -> tuple[str, str, str]:
    """Returns (email_id, sender, subject, html_body)."""
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()

    subject = ""
    sender = ""
    for h in msg["payload"].get("headers", []):
        if h["name"] == "Subject":
            subject = h["value"]
        elif h["name"] == "From":
            sender = h["value"]

    html = _decode_body(msg["payload"])
    return msg_id, sender, subject, html


def fetch_new_emails(max_results: int = 50) -> list[tuple]:
    """
    Returns list of (email_id, sender, subject, html_body).
    Fetches up to max_results recent banking notification emails.
    Deduplication is handled by the DB's UNIQUE constraint on email_id.
    """
    service = _gmail_service()
    results = service.users().messages().list(
        userId="me",
        q=GMAIL_QUERY,
        maxResults=max_results,
    ).execute()

    messages = results.get("messages", [])
    emails = []
    for m in messages:
        try:
            emails.append(_fetch_message(service, m["id"]))
        except Exception as e:
            print(f"[gmail] skip {m['id']}: {e}")
    return emails


def detect_bank(sender: str, html: str) -> str | None:
    s = sender.lower()
    h = html.lower()[:800]

    if "bca.co.id" in s or "klikbca" in s:
        return "BCA"
    if "gopay" in s or "gojek.com" in s:
        return "GoPay"

    # Fallback on body content
    if "total payment" in h and "idr" in h:
        return "BCA"
    if "total bayar" in h and "gopay" in h:
        return "GoPay"

    return None
