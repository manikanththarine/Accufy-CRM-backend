from datetime import datetime, timezone

from gmail_reader import (
    get_gmail_service,
    list_all_messages,
    fetch_and_parse_message,
    extract_domain,
)
from company_enrichment import enrich_company_from_domain
from supabase_db import (
    get_gmail_connection,
    upsert_account,
    upsert_contact,
    insert_account_email_activity,
)
from llm_agent import analyze_lead_with_llm


# -------------------------------------------------------------------
# Utility helpers
# -------------------------------------------------------------------
def utc_now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _ms_to_iso(ms_value):
    """
    Convert Gmail internal timestamp (milliseconds) to ISO datetime.
    If timestamp is missing or invalid, fallback to current UTC time.
    """
    if not ms_value:
        return utc_now_iso()

    try:
        ts = int(ms_value) / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return utc_now_iso()


def _safe_text(value, default=""):
    """Normalize text fields safely."""
    return (value or default).strip()


def build_logo_url(domain: str) -> str:
    """
    Build a lightweight favicon/logo URL from domain.
    This gives the frontend a logo-like image without Apollo.
    """
    if not domain:
        return ""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"


def build_icon_fallback(company_name: str) -> str:
    """
    Fallback single-letter icon when no image/logo is available.
    """
    if not company_name:
        return "?"
    return company_name[:1].upper()


# -------------------------------------------------------------------
# AI lead scoring from email content
# -------------------------------------------------------------------
def score_email_with_ai(
    subject: str,
    snippet: str,
    sender_email: str,
    company_name: str,
    title: str = None,
    enrichment: dict = None,
):
    enrichment = enrichment or {}
    text = f"""
    sender: {sender_email}
    company: {company_name}
    subject: {subject or ''}
    message: {snippet or ''}
    """
    try:
        result = analyze_lead_with_llm(
            text=text,
            company=company_name,
            email=sender_email,
            job_title=title or "",
            enrichment=enrichment,
        ) or {}

        return {
            "leadScore": result.get("leadScore", result.get("score", 50)),
            "priority": result.get("priority", "medium"),
            "status": result.get("status", "Warm"),
            "aiNextAction": result.get("aiNextAction", result.get("next_action", "Manual review")),
            "reason": result.get("reason", "AI scoring completed"),
            "stage": result.get("stage", "Lead"),
        }

    except Exception:
        return {
            "leadScore": 50,
            "priority": "medium",
            "status": "Warm",
            "aiNextAction": "Manual review",
            "reason": "AI scoring fallback used during Gmail sync",
            "stage": "Lead",
        }

# -------------------------------------------------------------------
# Main Gmail -> Supabase sync
# -------------------------------------------------------------------
def sync_gmail_accounts_for_user(crm_user_email: str, max_pages: int = 20) -> dict:
    """
    Sync Gmail inbox messages for a CRM user and convert them into
    structured CRM account/contact/email activity data.

    Flow:
    1. Load saved Gmail OAuth connection
    2. Build Gmail API service
    3. Read inbox messages
    4. Extract sender/company/domain
    5. Enrich company using AI
    6. Score lead using AI
    7. Upsert account/contact/activity into Supabase
    """
    connection = get_gmail_connection(crm_user_email)
    if not connection:
        raise ValueError("Gmail not connected for this CRM user")

    refresh_token = connection.get("refresh_token")
    if not refresh_token:
        raise ValueError("Refresh token not found for this CRM user")

    # Create Gmail service
    service = get_gmail_service(refresh_token)

    # Read inbox messages
    messages = list_all_messages(service, label_ids=["INBOX"], max_pages=max_pages)

    processed = 0
    skipped = 0
    accounts_updated = 0

    for msg in messages:
        parsed = fetch_and_parse_message(service, msg["id"])

        sender_email = _safe_text(parsed.get("sender_email"))
        sender_name = _safe_text(parsed.get("sender_name"))
        subject = _safe_text(parsed.get("subject"))
        snippet = _safe_text(parsed.get("snippet"))
        domain = extract_domain(sender_email)

        # Skip rows where sender/domain cannot be identified
        if not sender_email or not domain:
            skipped += 1
            continue

        processed += 1
        received_at_iso = _ms_to_iso(parsed.get("received_at_unix_ms"))

        # -------------------------------------------------------------------
        # AI-based company enrichment
        # -------------------------------------------------------------------
        # This now uses company_enrichment.py -> llm_agent.py instead of Apollo.
        enriched = enrich_company_from_domain(
            domain=domain,
            sender_name=sender_name,
            sender_email=sender_email,
            subject=subject,
            snippet=snippet,
        )

        company_name = enriched.get("company_name") or domain.split(".")[0].title()
        logo_url = enriched.get("accountIcon") or build_logo_url(domain)
        icon_fallback = enriched.get("icon") or build_icon_fallback(company_name)

        # -------------------------------------------------------------------
        # AI-based lead scoring
        # -------------------------------------------------------------------
        ai = score_email_with_ai(
            subject=subject,
            snippet=snippet,
            sender_email=sender_email,
            company_name=company_name,
            title=enriched.get("title"),
            enrichment={
                "account": company_name,
                "title": enriched.get("title"),
                "industry": enriched.get("industry"),
                "revenue": enriched.get("revenue"),
                "headcount": enriched.get("headcount"),
                "linkedin": enriched.get("linkedin"),
                "website": enriched.get("website"),
            },
        )

        # -------------------------------------------------------------------
        # Account upsert payload
        # -------------------------------------------------------------------
        # IMPORTANT:
        # We are now storing frontend-friendly CRM fields directly.
        account_payload = {
            "company_name": company_name,
            "icon": icon_fallback,
            "owner": ai.get("owner", "Unassigned"),
            "industry": enriched.get("industry"),
            "status": ai.get("status"),
            "revenue": enriched.get("revenue"),
            "headcount": enriched.get("headcount"),
            "lead_score": ai.get("leadScore"),
            "ai_next_action": ai.get("aiNextAction"),
            "last_interaction": received_at_iso,
            "last_funding": enriched.get("last_funding"),
            "linkedin": enriched.get("linkedin"),
            "website": enriched.get("website") or f"https://{domain}",
            "priority": ai.get("priority"),
            "reason": ai.get("reason"),
            "source": "gmail_ai",
            "domain": domain,
            "updated_at": utc_now_iso(),
        }

        account = upsert_account(account_payload)
        if not account:
            continue

        # -------------------------------------------------------------------
        # Contact upsert
        # -------------------------------------------------------------------
        upsert_contact(
            {
                "account_id": account["id"],
                "name": sender_name or sender_email.split("@")[0],
                "email": sender_email,
                "title": enriched.get("title"),
                "linkedin": None,
                "source": "gmail_ai",
                "updated_at": utc_now_iso(),
            }
        )

        # -------------------------------------------------------------------
        # Store email activity for audit/timeline/history
        # -------------------------------------------------------------------
        insert_account_email_activity(
            {
                "account_id": account["id"],
                "sender_email": sender_email,
                "subject": subject,
                "snippet": snippet,
                "received_at": received_at_iso,
                "thread_id": parsed.get("thread_id"),
                "gmail_message_id": parsed.get("gmail_message_id"),
            }
        )

        accounts_updated += 1

    # -------------------------------------------------------------------
    # Final sync summary
    # -------------------------------------------------------------------
    return {
        "status": "success",
        "crm_user_email": crm_user_email,
        "google_email": connection.get("google_email"),
        "processed_company_emails": processed,
        "skipped_non_company_emails": skipped,
        "accounts_updated": accounts_updated,
    } 
