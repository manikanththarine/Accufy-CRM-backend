import os
import email.utils
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


PERSONAL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "proton.me",
    "protonmail.com",
}


def get_gmail_service(refresh_token: str):
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    return build("gmail", "v1", credentials=creds)


def list_all_messages(service, label_ids=None, max_pages: int = 20):
    all_messages = []
    page_token = None
    pages = 0

    while pages < max_pages:
        result = (
            service.users()
            .messages()
            .list(
                userId="me",
                labelIds=label_ids or ["INBOX"],
                maxResults=100,
                pageToken=page_token,
            )
            .execute()
        )
        all_messages.extend(result.get("messages", []))
        page_token = result.get("nextPageToken")
        pages += 1

        if not page_token:
            break

    return all_messages


def _get_header(headers, name: str) -> str:
    for item in headers:
        if item.get("name", "").lower() == name.lower():
            return item.get("value", "")
    return ""


def extract_domain(email_address: str) -> Optional[str]:
    if not email_address or "@" not in email_address:
        return None
    domain = email_address.split("@")[-1].strip().lower()
    if domain in PERSONAL_DOMAINS:
        return None
    return domain

def parse_email_address(raw_from: str):
    name, email_address = email.utils.parseaddr(raw_from or "")
    return {
        "sender_name": name.strip() or None,
        "sender_email": email_address.strip().lower() or None,
    }


def fetch_and_parse_message(service, message_id: str):
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )

    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    internal_date_ms = msg.get("internalDate")

    from_raw = _get_header(headers, "From")
    subject = _get_header(headers, "Subject")

    parsed_sender = parse_email_address(from_raw)
    snippet = msg.get("snippet", "")

    return {
        "gmail_message_id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "subject": subject,
        "snippet": snippet,
        "sender_name": parsed_sender.get("sender_name"),
        "sender_email": parsed_sender.get("sender_email"),
        "received_at_unix_ms": internal_date_ms,
    } 