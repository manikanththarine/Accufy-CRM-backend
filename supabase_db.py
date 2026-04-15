import os
import requests
from dotenv import load_dotenv

load_dotenv()

# -------------------------------------------------------------------
# Supabase configuration
# -------------------------------------------------------------------
# Service role key is used because this backend needs full DB access.
# Keep this only on the backend. Never expose it in frontend code.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


# -------------------------------------------------------------------
# Low-level helper functions
# -------------------------------------------------------------------
def _table_url(table: str) -> str:
    """Build the REST URL for a Supabase table."""
    return f"{SUPABASE_URL}/rest/v1/{table}"


def _raise_for_status(response: requests.Response):
    """
    Raise a readable runtime error if Supabase returns a non-2xx response.
    This helps debugging API/database issues faster.
    """
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Supabase error {response.status_code}: {response.text}"
        ) from exc


def _insert(table: str, data, prefer: str = "return=representation"):
    """
    Insert one or more rows into a table.
    By default, Supabase returns the inserted row(s).
    """
    headers = {**HEADERS, "Prefer": prefer}
    response = requests.post(_table_url(table), headers=headers, json=data, timeout=30)
    _raise_for_status(response)
    return response.json()


def _select(table: str, params=None):
    """Fetch rows from a table using Supabase REST filters."""
    response = requests.get(
        _table_url(table),
        headers=HEADERS,
        params=params or {},
        timeout=30,
    )
    _raise_for_status(response)
    return response.json()


def _update(table: str, filters: dict, data: dict):
    """
    Update rows in a table using REST filters.
    Example filter: {"id": "eq.1"}
    """
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
    """
    Upsert a row using an on_conflict column.
    If a row with the same conflict column exists, it is updated.
    Otherwise, it is inserted.
    """
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


# -------------------------------------------------------------------
# Users
# -------------------------------------------------------------------
def create_user(data: dict):
    """Create a new CRM user."""
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
    """Fetch a user by email."""
    rows = _select("users", {"select": "*", "email": f"eq.{email}", "limit": 1})
    return rows[0] if rows else None


def verify_user_credentials(email: str, password: str):
    """
    Basic credential verification.
    In production, passwords should be hashed, not stored in plain text.
    """
    user = get_user_by_email(email)
    if not user:
        return None
    if user.get("password") != password:
        return None
    return user


def update_user_password(email: str, new_password: str):
    """Update password for an existing user."""
    rows = _update("users", {"email": f"eq.{email}"}, {"password": new_password})
    return rows[0] if rows else None


# -------------------------------------------------------------------
# Leads
# -------------------------------------------------------------------
def insert_lead(data: dict):
    """Insert a lead into the leads table."""
    rows = _insert("leads", data)
    return rows[0] if rows else None


def get_all_leads():
    """Fetch all leads ordered by latest first."""
    return _select("leads", {"select": "*", "order": "id.desc"})


def get_lead_by_id(lead_id: int):
    """Fetch a single lead by ID."""
    rows = _select("leads", {"select": "*", "id": f"eq.{lead_id}", "limit": 1})
    return rows[0] if rows else None


def update_lead(lead_id: int, data: dict):
    """Update an existing lead by ID."""
    rows = _update("leads", {"id": f"eq.{lead_id}"}, data)
    return rows[0] if rows else None


# -------------------------------------------------------------------
# Messages
# -------------------------------------------------------------------
def insert_message(data: dict):
    """Insert a message linked to a lead."""
    rows = _insert("messages", data)
    return rows[0] if rows else None


def get_messages_by_lead(lead_id: int):
    """Fetch all messages for a lead, oldest first."""
    return _select(
        "messages",
        {"select": "*", "lead_id": f"eq.{lead_id}", "order": "id.asc"},
    )


# -------------------------------------------------------------------
# Tasks
# -------------------------------------------------------------------
def insert_task(data: dict):
    """Insert a follow-up or workflow task."""
    rows = _insert("tasks", data)
    return rows[0] if rows else None


def get_tasks_by_lead(lead_id: int):
    """Fetch tasks for a lead, latest first."""
    return _select(
        "tasks",
        {"select": "*", "lead_id": f"eq.{lead_id}", "order": "id.desc"},
    )


# -------------------------------------------------------------------
# Accounts
# -------------------------------------------------------------------
def get_all_accounts_raw():
    """
    Fetch raw account rows from the accounts table.
    We keep this raw version separate from frontend mapping so the backend
    can reuse the original DB shape if needed.
    """
    return _select("accounts", {"select": "*", "order": "updated_at.desc"})


def get_account_by_id(account_id: int):
    """Fetch one account by its ID."""
    rows = _select("accounts", {"select": "*", "id": f"eq.{account_id}", "limit": 1})
    return rows[0] if rows else None


def get_account_by_domain(domain: str):
    """Fetch one account by company domain."""
    rows = _select("accounts", {"select": "*", "domain": f"eq.{domain}", "limit": 1})
    return rows[0] if rows else None


def upsert_account(data: dict):
    """
    Upsert account using domain as unique conflict key.
    Domain is the safest practical company identifier in this design.
    """
    return _upsert("accounts", data, "domain")


# -------------------------------------------------------------------
# Contacts
# -------------------------------------------------------------------
def get_contact_by_email(email: str):
    """Fetch a contact by email."""
    rows = _select("contacts", {"select": "*", "email": f"eq.{email}", "limit": 1})
    return rows[0] if rows else None


def upsert_contact(data: dict):
    """
    Upsert a contact using email as the natural unique key.
    If the contact exists, update it. Otherwise, insert it.
    """
    existing = get_contact_by_email(data.get("email"))
    if existing:
        rows = _update("contacts", {"id": f"eq.{existing['id']}"}, data)
        return rows[0] if rows else None

    rows = _insert("contacts", data)
    return rows[0] if rows else None


# -------------------------------------------------------------------
# Gmail connections
# -------------------------------------------------------------------
def save_gmail_connection(data: dict):
    """
    Save or update Gmail OAuth connection details for a CRM user.
    crm_user_email is used as the unique conflict key.
    """
    return _upsert("gmail_connections", data, "crm_user_email")


def get_gmail_connection(crm_user_email: str):
    """Fetch Gmail connection details for a CRM user."""
    rows = _select(
        "gmail_connections",
        {"select": "*", "crm_user_email": f"eq.{crm_user_email}", "limit": 1},
    )
    return rows[0] if rows else None


# -------------------------------------------------------------------
# Account email activity
# -------------------------------------------------------------------
def insert_account_email_activity(data: dict):
    """
    Store a Gmail activity row against an account.
    To avoid duplicates, we first check gmail_message_id.
    """
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


# -------------------------------------------------------------------
# Frontend mapping
# -------------------------------------------------------------------
def map_account_for_frontend(account: dict):
    """
    Convert raw DB account fields into the exact frontend contract.

    This is important because:
    - database may use snake_case
    - frontend may expect camelCase
    - some fields may need cleaning or fallback values
    """
    website = (account.get("website") or "").strip()
    clean_website = website.replace("https://", "").replace("http://", "").rstrip("/")

    linkedin = (account.get("linkedin") or "").strip()
    linkedin_clean = (
        linkedin.replace("https://www.linkedin.com/company/", "")
        .replace("https://linkedin.com/company/", "")
        .strip("/")
    )

    # Support both old DB field names and new frontend-friendly field names.
    # This makes the API more robust while the schema evolves.
    account_name = (
        account.get("account")
        or account.get("company_name")
        or account.get("name")
        or "Unknown"
    )

    icon_value = (
        account.get("accountIcon")
        or account.get("icon")
        or account_name[:1].upper()
    )

    return {
        # Primary identifiers / display fields
        "id": account.get("id"),
        "name": account.get("name") or account_name,
        "account": account.get("account") or account_name,
        "title": account.get("title"),

        # Icon / branding fields
        "accountIcon": account.get("accountIcon") or account.get("logo") or account.get("icon"),
        "icon": account.get("icon") or account_name[:1].upper(),

        # CRM ownership / business fields
        "owner": account.get("owner") or "Unassigned",
        "industry": account.get("industry"),
        "status": account.get("status"),
        "stage": account.get("stage"),
        "amount": account.get("amount"),

        # Company enrichment fields
        "revenue": account.get("revenue"),
        "headcount": account.get("headcount"),
        "lastFunding": account.get("lastFunding") or account.get("last_funding"),
        "linkedin": linkedin_clean or account.get("linkedin"),
        "website": clean_website or account.get("website"),

        # AI / activity fields
        "leadScore": account.get("leadScore") or account.get("lead_score"),
        "aiNextAction": account.get("aiNextAction") or account.get("ai_next_action"),
        "lastInteraction": account.get("lastInteraction") or account.get("last_interaction"),

        # Extra metadata that may still be useful in frontend/debugging
        "priority": account.get("priority"),
        "reason": account.get("reason"),
        "source": account.get("source"),
        "domain": account.get("domain"),

        # Optional helper field if UI wants to use it directly
        "displayIcon": icon_value,
    }


def get_all_accounts():
    """
    Fetch accounts and map them into the frontend-friendly structure.
    Frontend should call this instead of get_all_accounts_raw().
    """
    return [map_account_for_frontend(row) for row in get_all_accounts_raw()] 
