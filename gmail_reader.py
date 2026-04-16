import base64
import os
from email.utils import parseaddr

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


def extract_domain(email: str):
    if not email or "@" not in email:
        return None
    return email.split("@")[-1].lower().strip()


def _get_access_token_from_refresh_token(refresh_token: str):
    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    creds.refresh(Request())
    return creds


def get_gmail_service(refresh_token: str):
    creds = _get_access_token_from_refresh_token(refresh_token)
    return build("gmail", "v1", credentials=creds)


def list_all_messages(service, label_ids=None, max_pages: int = 1):
    label_ids = label_ids or ["INBOX"]
    messages = []
    page_token = None
    pages_read = 0

    while pages_read < max_pages:
        result = service.users().messages().list(
            userId="me",
            labelIds=label_ids,
            maxResults=50,
            pageToken=page_token,
        ).execute()

        messages.extend(result.get("messages", []))
        page_token = result.get("nextPageToken")
        pages_read += 1

        if not page_token:
            break

    return messages


def _decode_base64url(data: str):
    if not data:
        return ""
    try:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode()).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_headers(payload):
    headers = payload.get("headers", []) or []
    header_map = {}
    for h in headers:
        name = (h.get("name") or "").lower()
        value = h.get("value") or ""
        header_map[name] = value
    return header_map


def _extract_text_from_payload(payload):
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    if mime_type == "text/plain" and body_data:
        return _decode_base64url(body_data)

    parts = payload.get("parts", []) or []
    for part in parts:
        part_type = part.get("mimeType", "")
        part_data = part.get("body", {}).get("data")
        if part_type == "text/plain" and part_data:
            return _decode_base64url(part_data)

    for part in parts:
        part_type = part.get("mimeType", "")
        part_data = part.get("body", {}).get("data")
        if part_type == "text/html" and part_data:
            return _decode_base64url(part_data)

    return ""


def fetch_and_parse_message(service, message_id: str):
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()

    payload = msg.get("payload", {}) or {}
    headers = _extract_headers(payload)

    from_header = headers.get("from", "")
    subject = headers.get("subject", "")
    sender_name, sender_email = parseaddr(from_header)

    body_text = _extract_text_from_payload(payload)
    snippet = msg.get("snippet") or body_text[:300]

    return {
        "gmail_message_id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "subject": subject,
        "sender_name": sender_name,
        "sender_email": sender_email.lower().strip() if sender_email else "",
        "snippet": snippet,
        "body": body_text,
        "received_at_unix_ms": msg.get("internalDate"),
    } 
