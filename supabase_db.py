import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def _url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"


def get_all_leads():
    response = requests.get(
        _url("leads"),
        headers=HEADERS,
        params={"select": "*", "order": "created_at.desc"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_lead_by_id(lead_id):
    response = requests.get(
        _url("leads"),
        headers=HEADERS,
        params={"select": "*", "id": f"eq.{lead_id}"},
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def insert_lead(lead_data):
    response = requests.post(
        _url("leads"),
        headers=HEADERS,
        json=lead_data,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def update_lead(lead_id, update_data):
    response = requests.patch(
        _url("leads"),
        headers=HEADERS,
        params={"id": f"eq.{lead_id}"},
        json=update_data,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def insert_message(message_data):
    response = requests.post(
        _url("messages"),
        headers=HEADERS,
        json=message_data,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_messages_by_lead(lead_id):
    response = requests.get(
        _url("messages"),
        headers=HEADERS,
        params={"select": "*", "lead_id": f"eq.{lead_id}", "order": "created_at.asc"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def insert_task(task_data):
    response = requests.post(
        _url("tasks"),
        headers=HEADERS,
        json=task_data,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()

def find_lead_by_email(email):
    response = requests.get(
        _url("leads"),
        headers=HEADERS,
        params={"select": "*", "email": f"eq.{email}", "limit": 1},
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def find_lead_by_website(website):
    response = requests.get(
        _url("leads"),
        headers=HEADERS,
        params={"select": "*", "website": f"eq.{website}", "limit": 1},
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None 


def get_tasks_by_lead(lead_id):
    response = requests.get(
        _url("tasks"),
        headers=HEADERS,
        params={"select": "*", "lead_id": f"eq.{lead_id}", "order": "created_at.desc"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json() 