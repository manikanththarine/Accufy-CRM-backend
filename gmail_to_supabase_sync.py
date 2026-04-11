from datetime import datetime, timezone

from gmail_reader import get_gmail_service, list_all_messages, fetch_and_parse_message, extract_domain
from company_enrichment import enrich_company_from_domain
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
        result = analyze_lead_with_llm(text)
        return {
            "lead_score": result.get("score"),
            "priority": result.get("priority"),
            "status": result.get("status"),
            "ai_next_action": result.get("next_action"),
            "reason": result.get("reason"),
        }
    except Exception:
        return {
            "lead_score": 50,
            "priority": "medium",
            "status": "Warm",
            "ai_next_action": "Manual review",
            "reason": "AI scoring fallback used during Gmail sync",
        }


def sync_gmail_accounts_for_user(crm_user_email: str, max_pages: int = 20) -> dict:
    connection = get_gmail_connection(crm_user_email)
    if not connection:
        raise ValueError("Gmail not connected for this CRM user")

    refresh_token = connection.get("refresh_token")
    if not refresh_token:
        raise ValueError("Refresh token not found for this CRM user")

    service = get_gmail_service(refresh_token)
    messages = list_all_messages(service, label_ids=["INBOX"], max_pages=max_pages)

    processed = 0
    skipped = 0
    accounts_updated = 0

    for msg in messages:
        parsed = fetch_and_parse_message(service, msg["id"])
        sender_email = parsed.get("sender_email")
        sender_name = parsed.get("sender_name")
        domain = extract_domain(sender_email)

        if not sender_email or not domain:
            skipped += 1
            continue

        processed += 1

        enriched = enrich_company_from_domain(domain)
        company_name = enriched.get("company_name") or domain.split(".")[0].title()
        received_at_iso = _ms_to_iso(parsed.get("received_at_unix_ms"))

        ai = score_email_with_ai(
            subject=parsed.get("subject"),
            snippet=parsed.get("snippet"),
            sender_email=sender_email,
            company_name=company_name,
        )

        account = upsert_account(
            {
                "company_name": company_name,
                "domain": domain,
                "icon": enriched.get("icon") or company_name[:1].upper(),
                "industry": enriched.get("industry"),
                "revenue": enriched.get("revenue"),
                "headcount": enriched.get("headcount"),
                "last_funding": enriched.get("last_funding"),
                "linkedin": enriched.get("linkedin"),
                "website": enriched.get("website") or f"https://{domain}",
                "owner": "Unassigned",
                "source": "gmail_apollo",
                "last_interaction": received_at_iso,
                "apollo_status": enriched.get("apollo_status", "pending"),
                "lead_score": ai.get("lead_score"),
                "priority": ai.get("priority"),
                "status": ai.get("status"),
                "ai_next_action": ai.get("ai_next_action"),
                "reason": ai.get("reason"),
                "updated_at": utc_now_iso(),
            }
        )

        if not account:
            continue

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

        accounts_updated += 1

    return {
        "status": "success",
        "crm_user_email": crm_user_email,
        "google_email": connection.get("google_email"),
        "processed_company_emails": processed,
        "skipped_non_company_emails": skipped,
        "accounts_updated": accounts_updated,
    } 