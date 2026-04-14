import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS

from llm_agent import analyze_lead_with_llm, analyze_reply_action
from email_sender import send_email
from supabase_db import (
    insert_lead,
    get_all_leads,
    get_lead_by_id,
    get_messages_by_lead,
    get_tasks_by_lead,
    insert_task,
    insert_message,
    update_lead,
    create_user,
    verify_user_credentials,
    get_user_by_email,
    update_user_password,
    save_gmail_connection,
    get_gmail_connection,
    get_all_accounts,
    get_account_by_id,
)
from gmail_to_supabase_sync import sync_gmail_accounts_for_user

load_dotenv()

app = Flask(__name__)
CORS(app)

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:1000")


def utc_now():
    return datetime.now(timezone.utc)


def utc_now_iso():
    return utc_now().isoformat()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def extract_email(text: str):
    if not text:
        return None
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    return match.group(0).lower() if match else None


def build_google_auth_url(crm_user_email: str) -> str:
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/userinfo.email openid",
        "access_type": "offline",
        "prompt": "consent",
        "state": crm_user_email,
    }
    return f"{base_url}?{urlencode(params)}"


def exchange_code_for_tokens(code: str) -> dict:
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "code": code,
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
        "grant_type": "authorization_code",
    }
    response = requests.post(token_url, data=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def get_google_profile(access_token: str) -> dict:
    response = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def create_followup_task_if_needed(lead_id: int, result: dict):
    followup_days = result.get("followup_days")
    task_title = result.get("task_title")
    task_description = result.get("task_description")

    if not followup_days or not task_title:
        return None

    due_date = (utc_now() + timedelta(days=int(followup_days))).isoformat()
    print(f"Current UTC time: {datetime.now()}")

    task = insert_task(
        {
            "lead_id": lead_id,
            "title": task_title,
            "description": task_description,
            "status": "open",
            # "due_date": due_date,
        }
    )
    return task



@app.route('/api/update-lead-stage', methods=['PATCH'])
def update_stage():
    data = request.json
    lead_id = data.get('lead_id')
    new_stage = data.get('stage')

    if not lead_id or not new_stage:
        return jsonify({"error": "Missing lead_id or stage"}), 400

    # 1. Create the payload
    # We update the stage and the 'last_interaction' timestamp automatically
    update_payload = {
        "stage": new_stage,
        "last_interaction": datetime.now(timezone.utc).isoformat()
    }

    try:
        # 2. Call the update function
        # Note: In this route context, lead_id comes directly from the request
        update_lead(lead_id, update_payload)
        
        return jsonify({
            "status": "success", 
            "message": f"Lead {lead_id} moved to {new_stage}"
        }), 200
        
    except Exception as e:
        print(f"Error updating lead stage: {e}")
        return jsonify({"error": str(e)}), 500
    
# @app.route("/", methods=["GET"])
# def health():
#     return jsonify({"status": "success", "message": "Accufy CRM backend running"}), 200


# -----------------------------
# Auth
# -----------------------------
@app.route("/api/signup", methods=["POST"])
def api_signup():
    try:
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        email = normalize_email(data.get("email"))
        password = (data.get("password") or "").strip()

        if not name or not email or not password:
            return jsonify({"status": "error", "message": "name, email and password are required"}), 400

        existing = get_user_by_email(email)
        if existing:
            return jsonify({"status": "error", "message": "User already exists"}), 409

        user = create_user(
            {
                "name": name,
                "email": email,
                "password": password,
                "role": "Admin",
                "isActive": True,
            }
        )
        return jsonify({"status": "success", "user": user}), 201

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/login", methods=["POST"])
def api_login():
    try:
        
        data = request.get_json() or {}
        email = normalize_email(data.get("email"))
        password = (data.get("password") or "").strip()
        print("Login attempt for email:", email)

        if not email or not password:
            return jsonify({"status": "error", "message": "email and password are required"}), 400

        user = verify_user_credentials(email, password)
        if not user:
            return jsonify({"status": "error", "message": "Invalid credentials"}), 401

        return jsonify({"status": "success", "user": user}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/forgot-password", methods=["POST"])
def api_forgot_password():
    try:
        data = request.get_json() or {}
        email = normalize_email(data.get("email"))
        new_password = (data.get("newPassword") or "").strip()

        if not email or not new_password:
            return jsonify({"status": "error", "message": "email and newPassword are required"}), 400

        updated = update_user_password(email, new_password)
        if not updated:
            return jsonify({"status": "error", "message": "User not found"}), 404

        return jsonify({"status": "success", "message": "Password updated successfully"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# -----------------------------
# Lead submission + AI scoring
# -----------------------------
@app.route("/submit", methods=["POST"])
def submit_lead():
    try:
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        email = normalize_email(data.get("email"))
        company = (data.get("company") or "").strip()
        source = (data.get("source") or "manual").strip()
        description = (data.get("description") or "").strip()
        jobTitle = (data.get("jobTitle") or "").strip()
        if not name and not email and not company and not description:
            return jsonify({"status": "error", "message": "At least one lead field is required"}), 400

        # 2. Get AI Analysis
        # Ensure result is always a dict to prevent .get() errors
        result = analyze_lead_with_llm(
            text=description, 
            company=company, 
            email=email, 
            job_title=jobTitle, 
            enrichment={}
        ) or {}
        

        # 3. Build Lead Payload with Type Safety
        lead_payload = {
            "name": name,
            "email": email,
            "company": company,
            "source": source,
            "job_title": jobTitle,
            "description": description,
            "intent": result.get("intent"),
            "score": int(result.get("score", 0)) if result.get("score") is not None else 0,
            "priority": result.get("priority", "medium"),
            "status": result.get("status", "New"),
            "reason": result.get("reason"),
            # "reply_message": result.get("reply_message"),
            "email_subject": result.get("email_subject"),
            # "followup_days": int(result.get("followup_days", 0)) if result.get("followup_days") is not None else 0,
            # "task_title": result.get("task_title"),
            # "task_description": result.get("task_description"),
            "next_action": result.get("next_action"),
            "next_action_type": result.get("next_action_type"),
            "auto_reply": bool(result.get("auto_reply", False)),
            "stage": result.get("stage", "Lead"),
            "amount": result.get("amount"), 
            # "leadScore": int(result.get("leadScore", 0)) if result.get("leadScore") is not None else 0,
            # "aiNextAction": result.get("aiNextAction"),
            "owner": result.get("owner", "Unassigned"),
        }
        print("AI Analysis Result:", lead_payload)

        # 4. Database Operations
        lead = insert_lead(lead_payload)

        if lead:
            # Save the inbound message history
            if description:
                insert_message({
                    "lead_id": lead["id"],
                    "direction": "inbound",
                    # "sender": email,
                    # "recipient": "",
                    "subject": company or "Lead submission",
                    "body": description,
                })

            # Create follow-up tasks based on AI suggestions
            task = create_followup_task_if_needed(lead["id"], result)

            return jsonify({
                "status": "success",
                "lead": lead,
                "task": task,
                "ai": result,
            }), 201
        else:
            return jsonify({"status": "error", "message": "Failed to insert lead into database"}), 500

    except Exception as e:
        print(f"Error in submit_lead: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# -----------------------------
# Inbound email handling
# -----------------------------
@app.route("/inbound-email", methods=["POST"])
def inbound_email():
    try:
        data = request.get_json(silent=True) or {}
        sender = normalize_email(data.get("from") or data.get("sender"))
        subject = (data.get("subject") or "").strip()
        body = (data.get("text") or data.get("body") or data.get("html") or "").strip()

        if not sender and not body:
            return jsonify({"status": "error", "message": "Email sender/body missing"}), 400

        ai_result = analyze_reply_action(subject=subject, body=body)

        leads = get_all_leads()
        matched_lead = None
        for lead in leads:
            lead_email = normalize_email(lead.get("email"))
            if sender and lead_email == sender:
                matched_lead = lead
                break

        if matched_lead:
            insert_message(
                {
                    "lead_id": matched_lead["id"],
                    "direction": "inbound",
                    "sender": sender,
                    "recipient": "",
                    "subject": subject,
                    "body": body,
                }
            )

            update_payload = {}
            if ai_result.get("status"):
                update_payload["status"] = ai_result["status"]
            if ai_result.get("next_action"):
                update_payload["next_action"] = ai_result["next_action"]

            if update_payload:
                update_lead(matched_lead["id"], update_payload)

        return jsonify(
            {
                "status": "success",
                "matched_lead_id": matched_lead["id"] if matched_lead else None,
                "ai": ai_result,
            }
        ), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# -----------------------------
# Leads / Dashboard
# -----------------------------
@app.route("/api/leads", methods=["GET"])
def api_leads():
    try:
        leads = get_all_leads()
        return jsonify({"status": "success", "leads": leads}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/leads/<int:lead_id>", methods=["GET"])
def api_lead_detail(lead_id: int):
    try:
        lead = get_lead_by_id(lead_id)
        if not lead:
            return jsonify({"status": "error", "message": "Lead not found"}), 404

        messages = get_messages_by_lead(lead_id)
        tasks = get_tasks_by_lead(lead_id)

        return jsonify(
            {
                "status": "success",
                "lead": lead,
                "messages": messages,
                "tasks": tasks,
            }
        ), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/dashboard-stats", methods=["GET"])
def api_dashboard_stats():
    try:
        leads = get_all_leads()

        total = len(leads)
        high_priority = sum(1 for l in leads if (l.get("priority") or "").lower() == "high")
        warm = sum(1 for l in leads if (l.get("status") or "").lower() == "warm")
        hot = sum(1 for l in leads if (l.get("status") or "").lower() == "hot")

        return jsonify(
            {
                "status": "success",
                "stats": {
                    "totalLeads": total,
                    "highPriority": high_priority,
                    "warmLeads": warm,
                    "hotLeads": hot,
                },
                "leads": leads,
            }
        ), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# -----------------------------
# Gmail integration
# -----------------------------
@app.route("/api/gmail/connect", methods=["GET"])
def api_gmail_connect():
    try:
        crm_user_email = normalize_email(request.args.get("crm_user_email"))
        if not crm_user_email:
            return jsonify({"status": "error", "message": "crm_user_email is required"}), 400

        auth_url = build_google_auth_url(crm_user_email)
        return jsonify({"status": "success", "auth_url": auth_url}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/gmail/callback", methods=["GET"])
def api_gmail_callback():
    try:
        code = request.args.get("code")
        crm_user_email = normalize_email(request.args.get("state"))

        if not code or not crm_user_email:
            return jsonify({"status": "error", "message": "Missing code or state"}), 400

        token_data = exchange_code_for_tokens(code)
        access_token = token_data.get("access_token")
        existing = get_gmail_connection(crm_user_email)
        refresh_token = token_data.get("refresh_token") or (existing or {}).get("refresh_token")

        if not access_token:
            return jsonify({"status": "error", "message": "No access token received"}), 400
        if not refresh_token:
            return jsonify({"status": "error", "message": "No refresh token available"}), 400

        profile = get_google_profile(access_token)
        google_email = normalize_email(profile.get("email"))

        save_gmail_connection(
            {
                "crm_user_email": crm_user_email,
                "google_email": google_email,
                "refresh_token": refresh_token,
                "scopes": "gmail.readonly",
                "updated_at": utc_now_iso(),
            }
        )

        return jsonify(
            {
                "status": "success",
                "message": "Gmail connected successfully",
                "crm_user_email": crm_user_email,
                "google_email": google_email,
            }
        ), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/gmail/status", methods=["GET"])
def api_gmail_status():
    try:
        crm_user_email = normalize_email(request.args.get("crm_user_email"))
        if not crm_user_email:
            return jsonify({"status": "error", "message": "crm_user_email is required"}), 400

        connection = get_gmail_connection(crm_user_email)

        return jsonify(
            {
                "status": "success",
                "connected": bool(connection),
                "google_email": connection.get("google_email") if connection else None,
                "crm_user_email": crm_user_email,
            }
        ), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/gmail/sync", methods=["POST"])
def api_gmail_sync():
    try:
        data = request.get_json() or {}
        crm_user_email = normalize_email(data.get("crm_user_email"))
        max_pages = int(data.get("max_pages", 20))

        if not crm_user_email:
            return jsonify({"status": "error", "message": "crm_user_email is required"}), 400

        result = sync_gmail_accounts_for_user(crm_user_email, max_pages=max_pages)
        return jsonify(result), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# -----------------------------
# Accounts API for frontend
# -----------------------------
@app.route("/api/accounts", methods=["GET"])
def api_accounts():
    try:
        accounts = get_all_accounts()
        return jsonify({"status": "success", "accounts": accounts}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/accounts/<int:account_id>", methods=["GET"])
def api_account_detail(account_id: int):
    try:
        account = get_account_by_id(account_id)
        if not account:
            return jsonify({"status": "error", "message": "Account not found"}), 404
        return jsonify({"status": "success", "account": account}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "1000"))
    app.run(host="0.0.0.0", port=port, debug=True) 
# changed api key
