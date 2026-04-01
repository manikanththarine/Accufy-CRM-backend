import os
import re
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from flask import Flask, request, render_template, redirect, url_for, jsonify

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
            f"Follow up with lead from {company}."
        ),
        "status": "open"
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

        total_leads = len(leads)
        hot_leads = len([l for l in leads if l.get("status") == "Hot"])
        warm_leads = len([l for l in leads if l.get("status") == "Warm"])
        cold_leads = len([l for l in leads if l.get("status") == "Cold"])

        scores = [int(l.get("score", 0)) for l in leads if l.get("score") is not None]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0

        needs_action = [
            l for l in leads
            if l.get("next_action_type") or l.get("status") == "Hot"
        ]

        recent_leads = leads[:5]

        return render_template(
            "dashboard.html",
            leads=leads,
            total_leads=total_leads,
            hot_leads=hot_leads,
            warm_leads=warm_leads,
            cold_leads=cold_leads,
            avg_score=avg_score,
            needs_action=needs_action,
            recent_leads=recent_leads,
        )
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
        phone = request.form.get("phone", "").strip()
        ocr_text = request.form.get("ocr_text", "").strip()

        analysis = analyze_lead_with_llm(description)

        lead_data = {
            "name": name or None,
            "company": company or "Unknown Company",
            "job_title": job_title or None,
            "email": email or None,
            "phone": phone or None,
            "ocr_text": ocr_text or None,
            "source": source or "Website",
            "description": description or None,
            "intent": analysis.get("intent", "Interested lead"),
            "score": int(analysis.get("score", 60)),
            "priority": analysis.get("priority", "medium"),
            "reason": analysis.get("reason", "Lead submitted form"),
            "status": analysis.get("status", "Warm"),
            "email_subject": analysis.get("email_subject", "Thanks for reaching out"),
            "email_body": analysis.get("reply_message", "Thank you for contacting us."),
            "next_action": analysis.get("next_action", "Send follow-up"),
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

        action = analyze_reply_action(body)

        update_lead(lead_id, {
            "intent": action.get("intent", "Interested lead"),
            "score": int(action.get("score", 60)),
            "priority": action.get("priority", "medium"),
            "reason": action.get("reason", "Inbound reply received"),
            "status": action.get("status", "Warm"),
            "next_action": action.get("next_action", "Send follow-up"),
            "next_action_type": action.get("next_action_type", "send_followup"),
            "updated_at": utc_now_iso(),
        })

        insert_task({
            "lead_id": lead_id,
            "title": action.get("task_title", "Review inbound reply"),
            "description": action.get("task_description", "Review inbound reply and continue conversation."),
            "status": "open"
        })

        if action.get("auto_reply", False):
            send_email(
                to_email=from_addr,
                subject=action.get("email_subject", f"Re: {subject}"),
                body=action.get("reply_message", "Thank you for your message."),
                lead_id=lead_id,
            )

        return "OK", 200

    except Exception as e:
        print("INBOUND ERROR:", str(e))
        return f"Error: {str(e)}", 500

@app.route("/run-action/<int:lead_id>", methods=["POST"])
def run_action(lead_id: int):
    try:
        lead = get_lead_by_id(lead_id)
        if not lead:
            return "Lead not found", 404

        action_type = lead.get("next_action_type")
        email = lead.get("email")
        company = lead.get("company") or "your team"

        if action_type == "send_pricing":
            if email:
                send_email(
                    to_email=email,
                    subject="Pricing details",
                    body="Thank you for your interest. Please find our pricing details. Let us know if you would like a quotation call.",
                    lead_id=lead_id,
                )

        elif action_type == "schedule_demo":
            if email:
                send_email(
                    to_email=email,
                    subject="Schedule a demo",
                    body="We would be happy to schedule a demo. Please share your available time slots.",
                    lead_id=lead_id,
                )

        elif action_type == "send_followup":
            if email:
                send_email(
                    to_email=email,
                    subject="Follow-up from our team",
                    body=f"Hello, this is a follow-up regarding your interest in our solution for {company}. Please let us know how we can help further.",
                    lead_id=lead_id,
                )

        elif action_type == "close_lead":
            update_lead(lead_id, {
                "status": "Cold",
                "updated_at": utc_now_iso(),
            })

        else:
            return "Unknown action type", 400

        insert_task({
            "lead_id": lead_id,
            "title": f"Executed action: {action_type}",
            "description": f"AI recommended action '{action_type}' was executed.",
            "status": "open"
        })

        update_lead(lead_id, {
            "updated_at": utc_now_iso(),
        })

        return redirect(url_for("lead_detail", lead_id=lead_id))

    except Exception as e:
        return f"Error running action: {str(e)}", 500
@app.route("/api/leads", methods=["GET"])
def api_get_all_leads():
    try:
        leads = get_all_leads()
        return jsonify(leads), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/api/leads", methods=["POST"])
def api_create_lead():
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "Invalid or missing JSON body"}), 400

        name = (data.get("name") or "").strip()
        company = (data.get("company") or "").strip()
        job_title = (data.get("job_title") or "").strip()
        email = (data.get("email") or "").strip()
        source = (data.get("source") or "API").strip()
        description = (data.get("description") or "").strip()

        analysis = analyze_lead_with_llm(description)

        lead_data = {
            "name": name or None,
            "company": company or "Unknown Company",
            "job_title": job_title or None,
            "email": email or None,
            "source": source,
            "description": description or None,
            "intent": analysis.get("intent", "Interested lead"),
            "score": int(analysis.get("score", 60)),
            "priority": analysis.get("priority", "medium"),
            "reason": analysis.get("reason", "Lead submitted via API"),
            "status": analysis.get("status", "Warm"),
            "email_subject": analysis.get("email_subject", "Thanks for reaching out"),
            "email_body": analysis.get("reply_message", "Thank you for contacting us."),
            "next_action": analysis.get("next_action", "Send follow-up"),
            "next_action_type": analysis.get("next_action_type", "send_followup"),
            "followup": (
                datetime.now(timezone.utc)
                + timedelta(days=int(analysis.get("followup_days", 3)))
            ).isoformat(),
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }

        inserted = insert_lead(lead_data)
        lead = inserted[0] if isinstance(inserted, list) else inserted
        lead_id = lead["id"]

        create_initial_task(lead_id, analysis, company or "Unknown Company")

        if email:
            send_email(
                to_email=email,
                subject=analysis.get("email_subject", "Thanks for reaching out"),
                body=analysis.get("reply_message", "Thank you for contacting us."),
                lead_id=lead_id,
            )

        return jsonify({
            "message": "Lead created successfully",
            "lead_id": lead_id,
            "lead": lead
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/api/leads/<int:lead_id>/messages", methods=["GET"])
def api_get_messages_by_lead(lead_id):
    try:
        lead = get_lead_by_id(lead_id)
        if not lead:
            return jsonify({"error": "Lead not found"}), 404

        messages = get_messages_by_lead(lead_id)
        return jsonify({
            "lead_id": lead_id,
            "count": len(messages),
            "messages": messages
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500 

@app.route("/api/leads/<int:lead_id>", methods=["GET"])
def api_get_lead(lead_id):
    try:
        lead = get_lead_by_id(lead_id)
        if not lead:
            return jsonify({"error": "Lead not found"}), 404
        return jsonify(lead), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/api/leads/<int:lead_id>/tasks", methods=["GET"])
def api_get_tasks_by_lead_route(lead_id):
    try:
        lead = get_lead_by_id(lead_id)
        if not lead:
            return jsonify({"error": "Lead not found"}), 404

        tasks = get_tasks_by_lead(lead_id)
        return jsonify({
            "lead_id": lead_id,
            "count": len(tasks),
            "tasks": tasks
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500  

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)