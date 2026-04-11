import os
import re
import base64
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def get_gmail_service():
    creds = None

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def get_recent_messages(service, max_results=20):
    results = service.users().messages().list(
        userId='me',
        maxResults=max_results,
        q="category:primary -from:me"
    ).execute()

    return results.get('messages', [])


def _decode_base64_data(data):
    if not data:
        return ""
    try:
        decoded_bytes = base64.urlsafe_b64decode(data.encode("UTF-8"))
        return decoded_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_plain_text_from_payload(payload):
    if not payload:
        return ""

    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {}) or {}

    if mime_type == "text/plain":
        return _decode_base64_data(body.get("data"))

    parts = payload.get("parts", [])
    if parts:
        collected = []
        for part in parts:
            part_mime = part.get("mimeType", "")
            if part_mime == "text/plain":
                text = _decode_base64_data((part.get("body") or {}).get("data"))
                if text:
                    collected.append(text)
            else:
                nested = _extract_plain_text_from_payload(part)
                if nested:
                    collected.append(nested)
        return "\n".join([p for p in collected if p]).strip()

    return _decode_base64_data(body.get("data"))


def _extract_html_text_from_payload(payload):
    if not payload:
        return ""

    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {}) or {}

    if mime_type == "text/html":
        return _decode_base64_data(body.get("data"))

    parts = payload.get("parts", [])
    if parts:
        collected = []
        for part in parts:
            part_mime = part.get("mimeType", "")
            if part_mime == "text/html":
                text = _decode_base64_data((part.get("body") or {}).get("data"))
                if text:
                    collected.append(text)
            else:
                nested = _extract_html_text_from_payload(part)
                if nested:
                    collected.append(nested)
        return "\n".join([p for p in collected if p]).strip()

    return ""


def _strip_html_tags(html_text):
    if not html_text:
        return ""
    text = re.sub(r"<style.*?>.*?</style>", " ", html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script.*?>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_message_detail(service, msg_id):
    msg = service.users().messages().get(userId='me', id=msg_id, format="full").execute()
    payload = msg.get("payload", {}) or {}
    headers = payload.get("headers", [])

    subject = ""
    from_value = ""
    date_value = ""

    for h in headers:
        name = h.get("name", "")
        value = h.get("value", "")
        if name == "Subject":
            subject = value
        elif name == "From":
            from_value = value
        elif name == "Date":
            date_value = value

    plain_text = _extract_plain_text_from_payload(payload)
    html_text = _extract_html_text_from_payload(payload)

    body_text = plain_text.strip()
    if not body_text and html_text:
        body_text = _strip_html_tags(html_text)

    return {
        "subject": subject,
        "from": from_value,
        "date": date_value,
        "body": body_text[:12000],
    }


def extract_email(from_text):
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', from_text or "")
    return match.group(0).lower() if match else None


def extract_domain(email):
    if not email or "@" not in email:
        return None

    domain = email.split("@")[-1].lower().strip()

    blocked = {
        "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
        "icloud.com", "proton.me", "protonmail.com"
    }

    if domain in blocked:
        return None

    return domain


def extract_sender_name(from_text):
    if not from_text:
        return None

    cleaned = re.sub(r'<.*?>', '', from_text).strip().strip('"')
    return cleaned if cleaned else None


def extract_companies_from_gmail(max_results=20):
    service = get_gmail_service()
    messages = get_recent_messages(service, max_results=max_results)

    results = []
    seen_domains = set()

    for msg in messages:
        detail = get_message_detail(service, msg['id'])

        sender_email = extract_email(detail["from"])
        domain = extract_domain(sender_email)
        sender_name = extract_sender_name(detail["from"])

        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            results.append({
                "sender_name": sender_name,
                "sender_email": sender_email,
                "domain": domain,
                "subject": detail["subject"],
                "body": detail["body"],
                "date": detail["date"],
                "raw_from": detail["from"]
            })

    return results 