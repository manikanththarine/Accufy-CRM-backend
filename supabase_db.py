import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


def _table_url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def _raise_for_status(response: requests.Response):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"Supabase error {response.status_code}: {response.text}") from exc


def _insert(table: str, data, prefer: str = "return=representation"):
    headers = {**HEADERS, "Prefer": prefer}
    response = requests.post(_table_url(table), headers=headers, json=data, timeout=30)
    _raise_for_status(response)
    return response.json()


def _select(table: str, params=None):
    response = requests.get(_table_url(table), headers=HEADERS, params=params or {}, timeout=30)
    _raise_for_status(response)
    return response.json()


def _update(table: str, filters: dict, data: dict):
    headers = {**HEADERS, "Prefer": "return=representation"}
    response = requests.patch(
        _table_url(table),
        headers=headers,
        params=filters,
        json=data,
        timeout=30,
    )
    _raise_for_status(response)
    return response.json()


def _upsert(table: str, data: dict, conflict_col: str):
    headers = {
        **HEADERS,
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    response = requests.post(
        f"{_table_url(table)}?on_conflict={conflict_col}",
        headers=headers,
        json=data,
        timeout=30,
    )
    _raise_for_status(response)
    rows = response.json()
    return rows[0] if rows else None


# -----------------------------
# Users
# -----------------------------
def create_user(data: dict):
    payload = {
        "name": data.get("name"),
        "email": data.get("email"),
        "password": data.get("password"),
        "role": data.get("role", "user"),
        "isActive": data.get("isActive", True),
    }
    rows = _insert("users", payload)
    return rows[0] if rows else None


def get_user_by_email(email: str):
    rows = _select("users", {"select": "*", "email": f"eq.{email}", "limit": 1})
    return rows[0] if rows else None


def verify_user_credentials(email: str, password: str):
    user = get_user_by_email(email)
    if not user:
        return None
    if user.get("password") != password:
        return None
    return user


def update_user_password(email: str, new_password: str):
    rows = _update("users", {"email": f"eq.{email}"}, {"password": new_password})
    return rows[0] if rows else None


# -----------------------------
# Leads
# -----------------------------
def insert_lead(data: dict):
    rows = _insert("leads", data)
    return rows[0] if rows else None


def get_all_leads():
    return _select("leads", {"select": "*", "order": "id.desc"})


def get_lead_by_id(lead_id: int):
    rows = _select("leads", {"select": "*", "id": f"eq.{lead_id}", "limit": 1})
    return rows[0] if rows else None


def update_lead(lead_id: int, data: dict):
    rows = _update("leads", {"id": f"eq.{lead_id}"}, data)
    return rows[0] if rows else None


# -----------------------------
# Messages
# -----------------------------
def insert_message(data: dict):
    rows = _insert("messages", data)
    return rows[0] if rows else None


def get_messages_by_lead(lead_id: int):
    return _select("messages", {"select": "*", "lead_id": f"eq.{lead_id}", "order": "id.asc"})


# -----------------------------
# Tasks
# -----------------------------
def insert_task(data: dict):
    rows = _insert("tasks", data)
    return rows[0] if rows else None


def get_tasks_by_lead(lead_id: int):
    return _select("tasks", {"select": "*", "lead_id": f"eq.{lead_id}", "order": "id.desc"})


# -----------------------------
# Accounts
# -----------------------------
def get_all_accounts_raw():
    return _select("accounts", {"select": "*", "order": "updated_at.desc"})


def get_account_by_id(account_id: int):
    rows = _select("accounts", {"select": "*", "id": f"eq.{account_id}", "limit": 1})
    return rows[0] if rows else None


def get_account_by_domain(domain: str):
    rows = _select("accounts", {"select": "*", "domain": f"eq.{domain}", "limit": 1})
    return rows[0] if rows else None


def upsert_account(data: dict):
    return _upsert("accounts", data, "domain")


# -----------------------------
# Contacts
# -----------------------------
def get_contact_by_email(email: str):
    rows = _select("contacts", {"select": "*", "email": f"eq.{email}", "limit": 1})
    return rows[0] if rows else None


def upsert_contact(data: dict):
    existing = get_contact_by_email(data.get("email"))
    if existing:
        rows = _update("contacts", {"id": f"eq.{existing['id']}"}, data)
        return rows[0] if rows else None
    rows = _insert("contacts", data)
    return rows[0] if rows else None


# -----------------------------
# Gmail connections
# -----------------------------
def save_gmail_connection(data: dict):
    return _upsert("gmail_connections", data, "crm_user_email")


def get_gmail_connection(crm_user_email: str):
    rows = _select(
        "gmail_connections",
        {"select": "*", "crm_user_email": f"eq.{crm_user_email}", "limit": 1},
    )
    return rows[0] if rows else None


# -----------------------------
# Account email activity
# -----------------------------
def insert_account_email_activity(data: dict):
    existing = _select(
        "account_email_activity",
        {
            "select": "*",
            "gmail_message_id": f"eq.{data.get('gmail_message_id')}",
            "limit": 1,
        },
    )
    if existing:
        return existing[0]
    rows = _insert("account_email_activity", data)
    return rows[0] if rows else None


# -----------------------------
# Frontend mapping
# -----------------------------
def map_account_for_frontend(account: dict):
    website = (account.get("website") or "").strip()
    clean_website = website.replace("https://", "").replace("http://", "").rstrip("/")

    linkedin = (account.get("linkedin") or "").strip()
    linkedin_clean = (
        linkedin.replace("https://www.linkedin.com/company/", "")
        .replace("https://linkedin.com/company/", "")
        .strip("/")
    )

    account_name = (
        account.get("account")
        or account.get("company_name")
        or account.get("name")
        or "Unknown"
    )

    return {
        "id": account.get("id"),
        "name": account_name,
        "account": account_name,
        "title": None,
        "accountIcon": account.get("icon"),
        "icon": account.get("icon") or account_name[:1].upper(),
        "owner": account.get("owner") or "Unassigned",
        "industry": account.get("industry"),
        "status": account.get("status"),
        "stage": None,
        "amount": None,
        "revenue": account.get("revenue"),
        "headcount": account.get("headcount"),
        "leadScore": account.get("lead_score"),
        "aiNextAction": account.get("ai_next_action"),
        "lastInteraction": account.get("last_interaction"),
        "lastFunding": account.get("last_funding"),
        "linkedin": linkedin_clean or account.get("linkedin"),
        "website": clean_website or account.get("website"),
        "priority": account.get("priority"),
        "reason": account.get("reason"),
        "source": account.get("source"),
        "domain": account.get("domain"),
    }


def get_all_accounts():
    return [map_account_for_frontend(row) for row in get_all_accounts_raw()] 