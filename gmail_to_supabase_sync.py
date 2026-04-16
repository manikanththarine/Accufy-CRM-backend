from datetime import datetime, timezone

from gmail_reader import (
    get_gmail_service,
    list_all_messages,
    fetch_and_parse_message,
    extract_domain,
)
from supabase_db import (
    get_gmail_connection,
    upsert_account,
    upsert_contact,
    insert_account_email_activity,
)
from llm_agent import analyze_lead_with_llm


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ms_to_iso(ms_value):
    if not ms_value:
        return utc_now_iso()
    try:
        ts = int(ms_value) / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return utc_now_iso()


def score_email_with_ai(subject: str, snippet: str, sender_email: str, company_name: str):
    text = f"""
Sender: {sender_email}
Company: {company_name}
Subject: {subject or ''}
Message: {snippet or ''}
"""

    try:
        result = analyze_lead_with_llm(
            text=text,
            company=company_name,
            email=sender_email,
        ) or {}

        return {
            "leadScore": result.get("leadScore", result.get("score", 50)),
            "priority": result.get("priority", "medium"),
            "status": result.get("status", "Warm"),
            "aiNextAction": result.get("aiNextAction", result.get("next_action", "Manual review")),
            "reason": result.get("reason", "AI processed"),
            "owner": result.get("owner", "Unassigned"),
        }

    except Exception as e:
        print("AI ERROR:", str(e))
        return {
            "leadScore": 50,
            "priority": "medium",
            "status": "Warm",
            "aiNextAction": "Manual review",
            "reason": "AI fallback",
            "owner": "Unassigned",
        }


def sync_gmail_accounts_for_user(crm_user_email: str, max_pages: int = 1) -> dict:
    connection = get_gmail_connection(crm_user_email)

    if not connection:
        raise ValueError("Gmail not connected for this CRM user")

    refresh_token = connection.get("refresh_token")

    if not refresh_token:
        raise ValueError("Refresh token missing")

    service = get_gmail_service(refresh_token)

    messages = list_all_messages(
        service,
        label_ids=["INBOX"],
        max_pages=max_pages,
    )

    processed = 0
    skipped = 0
    accounts_updated = 0

    for i, msg in enumerate(messages):
        if i >= 3:
            break

        try:
            parsed = fetch_and_parse_message(service, msg["id"])

            sender_email = parsed.get("sender_email")
            sender_name = parsed.get("sender_name")
            domain = extract_domain(sender_email)

            if not sender_email or not domain:
                skipped += 1
                continue

            processed += 1

            company_name = domain.split(".")[0].title()
            received_at_iso = _ms_to_iso(parsed.get("received_at_unix_ms"))

            ai = score_email_with_ai(
                subject=parsed.get("subject"),
                snippet=parsed.get("snippet"),
                sender_email=sender_email,
                company_name=company_name,
            )

            account_payload = {
                "company_name": company_name,
                "domain": domain,
                "icon": company_name[:1].upper(),
                "industry": None,
                "revenue": None,
                "headcount": None,
                "last_funding": None,
                "linkedin": None,
                "website": f"https://{domain}",
                "owner": ai.get("owner"),
                "source": "gmail",
                "last_interaction": received_at_iso,
                "lead_score": ai.get("leadScore"),
                "priority": ai.get("priority"),
                "status": ai.get("status"),
                "ai_next_action": ai.get("aiNextAction"),
                "reason": ai.get("reason"),
                "updated_at": utc_now_iso(),
            }

            account = upsert_account(account_payload)

            if not account:
                continue

            try:
                upsert_contact(
                    {
                        "account_id": account["id"],
                        "name": sender_name,
                        "email": sender_email,
                        "title": None,
                        "linkedin": None,
                        "source": "gmail",
                        "updated_at": utc_now_iso(),
                    }
                )
            except Exception as e:
                print("CONTACT ERROR:", e)

            try:
                insert_account_email_activity(
                    {
                        "account_id": account["id"],
                        "sender_email": sender_email,
                        "subject": parsed.get("subject"),
                        "snippet": parsed.get("snippet"),
                        "received_at": received_at_iso,
                        "thread_id": parsed.get("thread_id"),
                        "gmail_message_id": parsed.get("gmail_message_id"),
                    }
                )
            except Exception as e:
                print("ACTIVITY ERROR:", e)

            accounts_updated += 1

        except Exception as e:
            print("GMAIL LOOP ERROR:", str(e))
            continue

    return {
        "status": "success",
        "crm_user_email": crm_user_email,
        "google_email": connection.get("google_email"),
        "processed_company_emails": processed,
        "skipped_non_company_emails": skipped,
        "accounts_updated": accounts_updated,
    } 
