import os
import requests
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing in .env")

HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}



# Helper for timestamps
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# --- USER AUTH FUNCTIONS ---

def create_user(data: dict):
    """Signup logic: Hashes password and inserts user."""
    url = f"{SUPABASE_URL}/rest/v1/users"
    
    # Hash the password before saving
    hashed_pw = generate_password_hash(data['password'])
    
    user_payload = {
        "name": data['name'].strip(),
        "email": data['email'].strip().lower(),
        "password": hashed_pw,
        "role": data.get('role', 'user'),
        "isActive": True,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso()
    }
    
    response = requests.post(url, headers=HEADERS, json=user_payload, timeout=30)
    if not response.ok:
        raise ValueError(f"Signup failed: {response.text}")
    return response.json()

def get_user_by_email(email: str):
    """Signin/Forgot logic: Retrieves user by email."""
    url = f"{SUPABASE_URL}/rest/v1/users?email=eq.{email.lower()}&select=*"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data[0] if data else None

def update_user_password(email: str, new_password: str):
    """Forgot Password logic: Updates the hash."""
    url = f"{SUPABASE_URL}/rest/v1/users?email=eq.{email.lower()}"
    hashed_pw = generate_password_hash(new_password)
    
    payload = {
        "password": hashed_pw,
        "updated_at": utc_now_iso()
    }
    
    response = requests.patch(url, headers=HEADERS, json=payload, timeout=30)
    response.raise_for_status()
    return True
def verify_user_credentials(email, provided_password):
    """
    Fetches user by email and validates the hashed password.
    """
    url = f"{SUPABASE_URL}/rest/v1/users?email=eq.{email.lower()}&select=*"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    
    users = response.json()
    if not users:
        return None  # No user found with that email
    
    user = users[0]
    
    # Check if the provided plain-text password matches the stored hash
    if check_password_hash(user['password'], provided_password):
        # Remove sensitive data before returning the user object
        user.pop('password')
        return user
        
    return None  # Password did not match

def insert_lead(data: dict):
    url = f"{SUPABASE_URL}/rest/v1/leads"
    response = requests.post(url, headers=HEADERS, json=data, timeout=30)
    print("Insert lead status:", response.status_code)
    print("Insert lead response:", response.text)

    if not response.ok:
        raise ValueError(f"Supabase lead insert failed: {response.text}")

    return response.json() 


def get_all_leads():
    url = f"{SUPABASE_URL}/rest/v1/leads?select=*&order=id.desc"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def get_lead_by_id(lead_id: int):
    url = f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead_id}&select=*"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data[0] if data else None


def update_lead(lead_id: int, data: dict):
    url = f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead_id}"
    response = requests.patch(url, headers=HEADERS, json=data, timeout=30)
    print("Update lead:", response.status_code, response.text)
    response.raise_for_status()
    return response.json() if response.text else []


def insert_message(data: dict):
    url = f"{SUPABASE_URL}/rest/v1/messages"
    response = requests.post(url, headers=HEADERS, json=data, timeout=30)
    print("Insert message:", response.status_code, response.text)
    response.raise_for_status()
    return response.json()


def get_messages_by_lead(lead_id: int):
    url = f"{SUPABASE_URL}/rest/v1/messages?lead_id=eq.{lead_id}&select=*&order=id.asc"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def insert_task(data: dict):
    url = f"{SUPABASE_URL}/rest/v1/tasks"
    response = requests.post(url, headers=HEADERS, json=data, timeout=30)
    print("Insert task:", response.status_code, response.text)
    response.raise_for_status()
    return response.json()


def get_tasks_by_lead(lead_id: int):
    url = f"{SUPABASE_URL}/rest/v1/tasks?lead_id=eq.{lead_id}&select=*&order=id.desc"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()