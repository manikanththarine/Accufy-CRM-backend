import json
import os
import re
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()


def _fallback_result(reason="OpenAI failed", enrichment=None):
    enrichment = enrichment or {}
    base_score = int(enrichment.get("leadScore", 60))

    return {
        "intent": "Interested lead",
        "score": base_score,
        "priority": "medium",
        "status": "Warm",
        "reason": reason,
        "reply_message": "Thank you for your interest. We will get back to you shortly.",
        "email_subject": "Thanks for reaching out",
        "followup_days": 3,
        "task_title": "Review lead",
        "task_description": "Review lead and continue qualification.",
        "next_action": "Review and qualify lead",
        "next_action_type": "manual_review",
        "auto_reply": True,
        "stage": "Lead",
        "amount": None,
        "leadScore": base_score,
        "aiNextAction": "Review and qualify lead",
        "owner": "Unassigned",
    }


def _parse_json_safely(text):
    text = (text or "").strip()

    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}


def analyze_with_openai(text, company, email, job_title, enrichment=None):
    enrichment = enrichment or {}
    if not OPENAI_API_KEY:
        return _fallback_result("OPENAI_API_KEY missing", enrichment=enrichment)

    prompt = f"""
You are a CRM AI assistant.

Your job:
1. Score the lead based on business interest.
2. Suggest CRM next actions.
3. Use enrichment data as context.
4. Do NOT invent factual company data. Keep provided enrichment values unchanged.

Return ONLY valid JSON in this exact structure:
{{
  "intent": "High purchase intent | Requested quotation | Interested lead | Just exploring | Not interested lead",
  "score": 0,
  "priority": "high | medium | low",
  "status": "Hot | Warm | Cold | New",
  "reason": "short explanation",
  "reply_message": "professional client-friendly email body",
  "email_subject": "professional email subject",
  "followup_days": 0,
  "task_title": "short task title",
  "task_description": "short task description",
  "next_action": "human readable next step",
  "next_action_type": "send_pricing | schedule_demo | send_followup | close_lead | manual_review",
  "auto_reply": true,
  "stage": "Lead | Discovery | Proposal | Won | Lost",
  "amount": null,
  "leadScore": 0,
  "aiNextAction": "short CRM action sentence",
  "owner": "Unassigned"
}}

Rules:
- Score must be between 10 and 100.
- leadScore must equal score.
- Use realistic values.
- Never overwrite factual enrichment fields in the backend.
- If the user message is weak or generic, keep score moderate.

Lead context:
- Company: {company or enrichment.get("account") or "Unknown Company"}
- Email: {email or ""}
- Job title: {job_title or enrichment.get("title") or ""}
- Industry: {enrichment.get("industry", "Unknown")}
- Revenue: {enrichment.get("revenue", "Unknown")}
- Headcount: {enrichment.get("headcount", "Unknown")}
- LinkedIn: {enrichment.get("linkedin") or ""}
- Website: {enrichment.get("website") or ""}
- Message: {text or ""}
""".strip()

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4.1-mini",
                "input": prompt,
            },
            timeout=60,
        )

        if response.status_code != 200:
            print("OpenAI failed:", response.status_code, response.text[:500])
            return _fallback_result(
                f"OpenAI failed with status {response.status_code}",
                enrichment=enrichment,
            )

        payload = response.json() or {}
        text_output = ""

        for item in payload.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") in ("output_text", "text"):
                        text_output += content.get("text", "")

        if not text_output:
            text_output = payload.get("output_text", "")

        result = _parse_json_safely(text_output)
        score = int(result.get("score", enrichment.get("leadScore", 60)))
        score = max(10, min(100, score))

        return {
            "intent": result.get("intent", "Interested lead"),
            "score": score,
            "priority": result.get("priority", "medium"),
            "status": result.get("status", "Warm"),
            "reason": result.get("reason", "Lead submitted form"),
            "reply_message": result.get(
                "reply_message",
                "Thank you for your interest. We will get back to you shortly."
            ),
            "email_subject": result.get("email_subject", "Thanks for reaching out"),
            "followup_days": int(result.get("followup_days", 3)),
            "task_title": result.get("task_title", "Review lead"),
            "task_description": result.get(
                "task_description",
                "Review lead and continue qualification."
            ),
            "next_action": result.get("next_action", "Review and qualify lead"),
            "next_action_type": result.get("next_action_type", "manual_review"),
            "auto_reply": bool(result.get("auto_reply", True)),
            "stage": result.get("stage", "Lead"),
            "amount": result.get("amount"),
            "leadScore": score,
            "aiNextAction": result.get(
                "aiNextAction",
                result.get("next_action", "Review and qualify lead")
            ),
            "owner": result.get("owner", "Unassigned"),
        }

    except Exception as exc:
        print("OpenAI exception:", str(exc))
        return _fallback_result(f"OpenAI exception: {str(exc)}", enrichment=enrichment)


def analyze_lead_with_llm(text, company, email, job_title, enrichment=None):
    return analyze_with_openai(
        text=text,
        company=company,
        email=email,
        job_title=job_title,
        enrichment=enrichment,
    )


def analyze_reply_action(text, company, email, job_title, enrichment=None):
    return analyze_with_openai(
        text=text,
        company=company,
        email=email,
        job_title=job_title,
        enrichment=enrichment,
    ) 