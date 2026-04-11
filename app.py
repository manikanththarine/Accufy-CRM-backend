import os
import re
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask import CORS # cors added

from company_enrichment import enrich_company_profile
from email_sender import send_email
from llm_agent import analyze_lead_with_llm, analyze_reply_action
from supabase_db import (
    get_all_leads,
    get_lead_by_id,
    get_messages_by_lead,
    get_tasks_by_lead,
    insert_lead,
    insert_message,
    insert_task,
    update_lead,
)

load_dotenv()
app = Flask(__name__)

CORS(app) # cors enabled

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()

def extract_lead_id_from_address(address_text : str):
    if not address_text:
        return None
    match = re.search(r"lead-(\d+)@", address_text)
    if match:
        return int(match.group(1))
    return None

def get_request_payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form


def create_initial_task(lead_id, analysis, company):
    insert_task(
        {
            "lead_id": lead_id,
            "title": analysis.get("task_title", "Review lead"),
            "description": analysis.get(
                "task_description",
                f"Review and follow up with {company}.",
            ),
            "status": "open",
        }
    )


def merge_enrichment_and_ai(
    enrichment,
    analysis,
    name,
    company,
    job_title,
    email,
    phone,
    source,
    description,
    ocr_text=""
):
    account = enrichment.get("account") or company or "Unknown Company"
    score = int(analysis.get("score", enrichment.get("leadScore", 60)))
    lead_score = int(analysis.get("leadScore", score))
    followup_days = int(analysis.get("followup_days", 3))

    return {
        "name": name or account,
        "company": company or account,
        "account": account,
        "job_title": job_title or None,
        "title": enrichment.get("title") or job_title or "New Business",
        "email": email or None,
        "phone": phone or None,
        "ocr_text": ocr_text or None,
        "source": source or "Website",
        "description": description or None,
        "intent": analysis.get("intent", "Interested lead"),
        "score": score,
        "priority": analysis.get("priority", "medium"),
        "reason": analysis.get("reason", "Lead submitted form"),
        "status": analysis.get("status", enrichment.get("status", "New")),
        "stage": analysis.get("stage", enrichment.get("stage", "Lead")),
        "amount": analysis.get("amount", enrichment.get("amount")),
        "revenue": enrichment.get("revenue", "Unknown"),
        "headcount": enrichment.get("headcount", "Unknown"),
        "industry": enrichment.get("industry", "Unknown"),
        "lead_score": lead_score,
        "ai_next_action": analysis.get(
            "aiNextAction",
            enrichment.get("aiNextAction", "Review and qualify lead"),
        ),
        "next_action": analysis.get("next_action", "Review and qualify lead"),
        "next_action_type": analysis.get("next_action_type", "manual_review"),
        "owner": analysis.get("owner", enrichment.get("owner", "Unassigned")),
        "account_icon": enrichment.get("accountIcon"),
        "icon": enrichment.get("icon"),
        "last_interaction": "Just now",
        "last_funding": enrichment.get("lastFunding", "Unknown"),
        "linkedin": enrichment.get("linkedin"),
        "website": enrichment.get("website"),
        "logo": enrichment.get("logo"),
        "email_subject": analysis.get("email_subject", "Thanks for reaching out"),
        "email_body": analysis.get("reply_message", "Thank you for contacting us."),
        "followup": (
            datetime.now(timezone.utc) + timedelta(days=followup_days)
        ).isoformat(),
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }

def signup():
    data = request.json
    try:
        # Check if user already exists
        if get_user_by_email(data.get('email')):
            return jsonify({"status": "error", "message": "Email already registered"}), 400
        
        create_user(data)
        return jsonify({"status": "success", "message": "User created"}), 201
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({"status": "error", "message": "Missing credentials"}), 400

        # Use the helper to verify credentials
        user = verify_user_credentials(email, password)
        
        if user:
            # Check if account is active based on your model
            if not user.get('isActive', True):
                return jsonify({"status": "error", "message": "Account is disabled"}), 403
                
            return jsonify({
                "status": "success",
                "message": "Login successful",
                "user": user
            }), 200
        else:
            return jsonify({"status": "error", "message": "Invalid email or password"}), 401

    except Exception as e:
        print(f"LOGIN ERROR: {str(e)}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500
    
@app.route('/api/forgot-password', methods=['PATCH'])
def forgot_password():
    data = request.json
    email = data.get('email')
    new_password = data.get('newPassword')
    
    user = get_user_by_email(email)
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404
        
    update_user_password(email, new_password)
    return jsonify({"status": "success", "message": "Password updated"}), 200

def update_stage():
    try:
        data = request.json
        lead_id = data.get('leadId')
        new_stage = data.get('stage')
        print(f"Received request to update Lead {lead_id} to stage {new_stage}")
        if not lead_id or not new_stage:
            return jsonify({"status": "error", "message": "Missing leadId or stage"}), 400

        # Create the update dictionary
        update_data = {
            "stage": new_stage,
            "updated_at": utc_now_iso() # Keeps your timestamps in sync
        }

        # Use your existing database helper function
        # Note: lead_id might need to be cast to int if your DB expects it
        update_lead(int(lead_id), update_data)
        
        print(f"Successfully updated Lead {lead_id} to stage {new_stage}")
        return jsonify({
            "status": "success", 
            "message": f"Lead {lead_id} updated to {new_stage}"
        }), 200

    except Exception as e:
        print(f"UPDATE STAGE ERROR: {str(e)}")
        return jsonify({
            "status": "error", 
            "message": str(e)
        }), 500
        
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/api/dashboard-stats", methods=["GET"])
def api_dashboard_stats():
    leads = get_all_leads()
    
    return jsonify({
        "total_leads": len(leads),
        "leads": leads,
        "hot_leads": len([l for l in leads if l.get("status") == "Hot"]),
        "warm_leads": len([l for l in leads if l.get("status") == "Warm"]),
        "cold_leads": len([l for l in leads if l.get("status") == "Cold"]),
        "avg_score": round(sum([int(l.get("score", 0)) for l in leads]) / len(leads), 1) if leads else 0
    }), 200

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
        needs_action = [l for l in leads if l.get("next_action_type") or l.get("status") == "Hot"]
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
def lead_detail(lead_id):
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


@app.route("/submit", methods=["POST"])
def submit_lead():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Invalid or missing JSON body"}), 400

        name = (data.get("name") or "").strip()
        company = (data.get("company") or data.get("account") or "").strip()
        job_title = (data.get("job_title") or data.get("title") or "").strip()
        email = (data.get("email") or "").strip()
        phone = (data.get("phone") or "").strip()
        source = (data.get("source") or "Website").strip()
        description = (data.get("description") or "").strip()
        
        
        enrichment = enrich_company_profile(company_name=company, email=email)

        analysis = analyze_lead_with_llm(
            text=description or f"New lead from {company or email or 'unknown source'}",
            company=company,
            email=email,
            job_title=job_title,
            enrichment=enrichment,
        )

        lead_data = merge_enrichment_and_ai(
            enrichment=enrichment,
            analysis=analysis,
            name=name,
            company=company,
            job_title=job_title,
            email=email,
            phone=phone,
            source=source,
            description=description,
            ocr_text=ocr_text,
        )

        inserted = insert_lead(lead_data)
        lead = inserted[0] if isinstance(inserted, list) else inserted
        lead_id = lead["id"]

        create_initial_task(
            lead_id,
            analysis,
            company or enrichment.get("account") or "Unknown Company",
        )

        if email:
            send_email(
                to_email=email,
                subject=analysis.get("email_subject", "Thanks for reaching out"),
                body=analysis.get("reply_message", "Thank you for contacting us."),
                lead_id=lead_id,
            )

        if request.is_json:
            return jsonify(
                {
                    "message": "Lead created successfully",
                    "lead_id": lead_id,
                    "lead": lead_data,
                }
            ), 201

        return redirect(url_for("dashboard"))
    except Exception as e:
        print("SUBMIT ERROR:", str(e))
        if request.is_json:
            return jsonify({"error": str(e)}), 500
        return f"Error while submitting lead: {str(e)}", 500


@app.route("/api/leads/enrich", methods=["POST"])
def api_enrich_lead():
    try:
        data = request.get_json() or {}
        company = (data.get("company") or data.get("account") or "").strip()
        email = (data.get("email") or "").strip()
        job_title = (data.get("job_title") or data.get("title") or "").strip()
        description = (data.get("description") or "").strip()

        enrichment = enrich_company_profile(company_name=company, email=email)

        analysis = analyze_lead_with_llm(
            text=description or f"New lead from {company or email or 'unknown source'}",
            company=company,
            email=email,
            job_title=job_title,
            enrichment=enrichment,
        )

        preview = merge_enrichment_and_ai(
            enrichment=enrichment,
            analysis=analysis,
            name="",
            company=company,
            job_title=job_title,
            email=email,
            phone="",
            source="Preview",
            description=description,
        )

        return jsonify({"success": True, "lead": preview}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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
        if not lead_id:
            return "Lead id not found", 400

        insert_message(
            {
                "lead_id": lead_id,
                "direction": "inbound",
                "subject": subject,
                "body": body,
                "sender_email": from_addr,
                "thread_key": f"lead-{lead_id}",
            }
        )

        existing_lead = get_lead_by_id(lead_id) or {}
        enrichment = {
            "industry": existing_lead.get("industry"),
            "revenue": existing_lead.get("revenue"),
            "headcount": existing_lead.get("headcount"),
            "linkedin": existing_lead.get("linkedin"),
            "website": existing_lead.get("website"),
            "title": existing_lead.get("title") or existing_lead.get("job_title"),
            "account": existing_lead.get("account") or existing_lead.get("company"),
            "lastFunding": existing_lead.get("last_funding"),
        }

        action = analyze_reply_action(
            text=body,
            company=existing_lead.get("company"),
            email=existing_lead.get("email"),
            job_title=existing_lead.get("job_title"),
            enrichment=enrichment,
        )

        update_lead(
            lead_id,
            {
                "intent": action.get("intent", existing_lead.get("intent", "Interested lead")),
                "score": int(action.get("score", existing_lead.get("score", 60))),
                "lead_score": int(action.get("leadScore", action.get("score", existing_lead.get("score", 60)))),
                "priority": action.get("priority", existing_lead.get("priority", "medium")),
                "reason": action.get("reason", "Inbound reply received"),
                "status": action.get("status", existing_lead.get("status", "Warm")),
                "stage": action.get("stage", existing_lead.get("stage", "Lead")),
                "next_action": action.get("next_action", existing_lead.get("next_action", "Review and qualify lead")),
                "next_action_type": action.get("next_action_type", existing_lead.get("next_action_type", "manual_review")),
                "ai_next_action": action.get("aiNextAction", existing_lead.get("ai_next_action", "Review and qualify lead")),
                "updated_at": utc_now_iso(),
            },
        )

        insert_task(
            {
                "lead_id": lead_id,
                "title": action.get("task_title", "Review inbound reply"),
                "description": action.get(
                    "task_description",
                    "Review inbound reply and continue conversation.",
                ),
                "status": "open",
            }
        )

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
def run_action(lead_id):
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
                    body="Thank you for your interest.\nPlease find our pricing details. Let us know if you would like a quotation call.",
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
                    body=f"Hello, this is a follow-up regarding your interest in our solution for {company}.\nPlease let us know how we can help further.",
                    lead_id=lead_id,
                )
        elif action_type == "close_lead":
            update_lead(
                lead_id,
                {
                    "status": "Cold",
                    "updated_at": utc_now_iso(),
                },
            )
        else:
            return "Unknown action type", 400

        insert_task(
            {
                "lead_id": lead_id,
                "title": f"Executed action: {action_type}",
                "description": f"AI recommended action '{action_type}' was executed.",
                "status": "open",
            }
        )

        update_lead(lead_id, {"updated_at": utc_now_iso()})
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

#json api routes.

@app.route("/api/leads", methods=["POST"])
def api_create_lead():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid or missing JSON body"}), 400

        name = (data.get("name") or "").strip()
        company = (data.get("company") or data.get("account") or "").strip()
        job_title = (data.get("job_title") or data.get("title") or "").strip()
        email = (data.get("email") or "").strip()
        phone = (data.get("phone") or "").strip()
        source = (data.get("source") or "API").strip()
        description = (data.get("description") or "").strip()

        enrichment = enrich_company_profile(company_name=company, email=email)

        analysis = analyze_lead_with_llm(
            text=description or f"New lead from {company or email or 'unknown source'}",
            company=company,
            email=email,
            job_title=job_title,
            enrichment=enrichment,
        )

        lead_data = merge_enrichment_and_ai(
            enrichment=enrichment,
            analysis=analysis,
            name=name,
            company=company,
            job_title=job_title,
            email=email,
            phone=phone,
            source=source,
            description=description,
            ocr_text=ocr_text,
        )

        inserted = insert_lead(lead_data)
        lead = inserted[0] if isinstance(inserted, list) else inserted
        lead_id = lead["id"]

        create_initial_task(
            lead_id,
            analysis,
            company or enrichment.get("account") or "Unknown Company",
        )

        if email:
            send_email(
                to_email=email,
                subject=analysis.get("email_subject", "Thanks for reaching out"),
                body=analysis.get("reply_message", "Thank you for contacting us."),
                lead_id=lead_id,
            )

        return jsonify(
            {
                "message": "Lead created successfully",
                "lead_id": lead_id,
                "lead": lead,
            }
        ), 201
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


@app.route("/api/leads/<int:lead_id>/messages", methods=["GET"])
def api_get_messages_by_lead_route(lead_id):
    try:
        lead = get_lead_by_id(lead_id)
        if not lead:
            return jsonify({"error": "Lead not found"}), 404

        messages = get_messages_by_lead(lead_id)
        return jsonify({"lead_id": lead_id, "count": len(messages), "messages": messages}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/leads/<int:lead_id>/tasks", methods=["GET"])
def api_get_tasks_by_lead_route(lead_id):
    try:
        lead = get_lead_by_id(lead_id)
        if not lead:
            return jsonify({"error": "Lead not found"}), 404

        tasks = get_tasks_by_lead(lead_id)
        return jsonify({"lead_id": lead_id, "count": len(tasks), "tasks": tasks}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port) 