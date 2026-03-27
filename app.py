import os
import re
from datetime import datetime, timedelta, timezone
from llm_agent import analyze_with_openai

from dotenv import load_dotenv
from flask import Flask, request, render_template, redirect, url_for, jsonify

from llm_agent import analyze_with_openai
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
)

load_dotenv()
app = Flask(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_lead_id_from_address(address_text: str):
    if not address_text:
        return None
    match = re.search(r"lead-(\d+)@", address_text)
    if match:
        return int(match.group(1))
    return None


def create_initial_task(lead_id: int, analysis: dict, company: str):
    insert_task({
        "lead_id": lead_id,
        "title": analysis.get("task_title", "Follow up with lead"),
        "description": analysis.get(
            "task_description",
            f"Follow up with lead {lead_id}"
        ),
        "status": "open",
    })


@app.route("/", methods=["GET"])
def home():
    return render_template("form.html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/dashboard", methods=["GET"])
def dashboard():
    try:
        leads = get_all_leads()
        return render_template("dashboard.html", leads=leads)
    except Exception as e:
        return f"Error loading dashboard: {str(e)}", 500


@app.route("/lead/<int:lead_id>", methods=["GET"])
def lead_detail(lead_id: int):
    try:
        lead = get_lead_by_id(lead_id)
        messages = get_messages_by_lead(lead_id)
        tasks = get_tasks_by_lead(lead_id)
        return render_template(
            "lead_detail.html",
            lead=lead,
            messages=messages,
            tasks=tasks,
        )
    except Exception as e:
        return f"Error loading lead detail: {str(e)}", 500


@app.route("/submit", methods=["GET", "POST"])
def submit_lead():
    if request.method == "GET":
        return redirect(url_for("home"))

    try:
        name = request.form.get("name", "").strip()
        company = request.form.get("company", "").strip()
        job_title = request.form.get("job_title", "").strip()
        email = request.form.get("email", "").strip()
        source = request.form.get("source", "Website").strip()
        description = request.form.get("description", "").strip()

        analysis = analyze_with_openai(description)

        lead_data = {
            "name": name ,
            "company": company ,
            "job_title": job_title or None,
            "email": email or None,
            "source": source or "Website",
            "description": description or None,
            "intent": analysis.get("intent", "Interested lead"),
            "score": int(analysis.get("score", 60)),
            "priority": analysis.get("priority", "medium"),
            "reason": analysis.get("reason", "Lead submitted form"),
            "status": analysis.get("status", "Warm"),
            "email_subject": analysis.get("email_subject", "Thanks for reaching out"),
            "email_body": analysis.get("reply_message", "Thank you for contacting us."),
            "next_action": analysis.get("next_action", "send_followup"),
            "next_action_type": analysis.get("next_action_type", "send_followup"),
            "followup": (
                datetime.now(timezone.utc)
                + timedelta(days=int(analysis.get("followup_days", 3)))
            ).isoformat(),
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }

        print("LEAD DATA TO INSERT:", lead_data)

        inserted = insert_lead(lead_data)
        lead_id = inserted[0]["id"] if isinstance(inserted, list) else inserted["id"]

        create_initial_task(lead_id, analysis, company or "Unknown Company")

        if email:
            send_email(
                to_email=email,
                subject=analysis.get("email_subject", "Thanks for reaching out"),
                body=analysis.get("reply_message", "Thank you for contacting us."),
                lead_id=lead_id,
            )

        return redirect(url_for("dashboard"))

    except Exception as e:
        print("SUBMIT ERROR:", str(e))
        return f"Error while submitting lead: {str(e)}", 500


@app.route("/inbound-email", methods=["POST"])
def inbound_email():
    try:
        print("=== INBOUND EMAIL HIT ===")
        print("FORM DATA:", request.form)

        to_addr = request.form.get("to", "")
        from_addr = request.form.get("from", "")
        subject = request.form.get("subject", "")
        body = request.form.get("text", "") or request.form.get("html", "")

        lead_id = extract_lead_id_from_address(to_addr)
        print("EXTRACTED LEAD ID:", lead_id)

        if not lead_id:
            return "Lead id not found", 400

        insert_message({
            "lead_id": lead_id,
            "direction": "inbound",
            "subject": subject,
            "body": body,
            "sender_email": from_addr,
            "thread_key": f"lead-{lead_id}",
        })

        action = analyze_with_openai("email_body", body)

        update_lead(lead_id, {
            "intent": action.get("intent", "Interested lead"),
            "priority": action.get("priority", "medium"),
            "reason": action.get("reason", "Inbound reply received"),
            "status": action.get("status", "Warm"),
            "updated_at": utc_now_iso(),
        })

        insert_task({
            "lead_id": lead_id,
            "title": action.get("task_title", "Follow up"),
            "description": action.get("task_description", "Review inbound reply"),
            "status": "open",
            "priority": action.get("priority", "medium"),
            "due_at": None,
            "created_by": "ai",
            "assigned_to": "Sales Team",
        })

        if action.get("auto_reply", False):
            send_email(
                to_email=from_addr,
                subject=f"Re: {subject}",
                body=action.get("reply_message", "Thank you for your message."),
                lead_id=lead_id,
            )

        return "OK", 200

    except Exception as e:
        print("INBOUND ERROR:", str(e))
        return f"Error: {str(e)}", 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port) 