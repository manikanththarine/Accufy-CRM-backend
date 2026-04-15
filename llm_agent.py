import json
import os
import re
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
print ("check", OPENAI_API_KEY)


# -------------------------------------------------------------------
# Generic fallback for CRM lead scoring
# -------------------------------------------------------------------
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


# -------------------------------------------------------------------
# Safe JSON parsing from model output
# -------------------------------------------------------------------
def _parse_json_safely(text):
    text = (text or "").strip()

    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                return {}
        return {}


# -------------------------------------------------------------------
# Low-level OpenAI Responses API caller
# -------------------------------------------------------------------
def _call_openai_json(prompt: str, fallback: dict):
    if not OPENAI_API_KEY:
        return fallback

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
            return fallback

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
        return result or fallback

    except Exception as exc:
        print("OpenAI exception:", str(exc))
        return fallback


# -------------------------------------------------------------------
# Lead scoring / CRM action analysis
# -------------------------------------------------------------------
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

    fallback = _fallback_result("OpenAI fallback used", enrichment=enrichment)
    result = _call_openai_json(prompt, fallback)

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


# -------------------------------------------------------------------
# AI company enrichment
# -------------------------------------------------------------------
def enrich_company_with_ai(domain: str, sender_name: str = "", sender_email: str = "", subject: str = "", snippet: str = ""):
    company_hint = domain.split(".")[0].replace("-", " ").replace("_", " ").title() if domain else "Unknown"

    fallback = {
        "company_name": company_hint,
        "website": f"https://{domain}" if domain else None,
        "linkedin": None,
        "industry": None,
        "revenue": None,
        "headcount": None,
        "last_funding": None,
        "title": None,
        "stage": "New",
        "amount": None,
        "icon": company_hint[:1].upper() if company_hint else "?",
        "accountIcon": company_hint[:1].upper() if company_hint else "?",
        "apollo_status": "not_used_ai_only",
    }

    if not domain:
        return fallback

    prompt = f"""
You are enriching CRM account data from email and company domain context.

Return ONLY valid JSON in this exact structure:
{{
  "company_name": "string",
  "website": "string or null",
  "linkedin": "string or null",
  "industry": "string or null",
  "revenue": "string or null",
  "headcount": "string or null",
  "last_funding": "string or null",
  "title": "string or null",
  "stage": "New | Qualified | Proposal | Negotiation | Won | Lost",
  "amount": null,
  "icon": "single character",
  "accountIcon": "single character"
}}

Rules:
- Do not invent exact facts if uncertain.
- Use null if the value is not reasonably inferable.
- revenue and headcount should be estimates or ranges, not exact claims.
- website should default to https://{domain} if no better option is inferable.
- icon and accountIcon should be the first letter of the company name.

Context:
- Domain: {domain}
- Sender Name: {sender_name}
- Sender Email: {sender_email}
- Subject: {subject}
- Message Snippet: {snippet}
- Company Hint: {company_hint}
""".strip()

    result = _call_openai_json(prompt, fallback)

    company_name = result.get("company_name") or company_hint
    icon_value = company_name[:1].upper() if company_name else "?"

    return {
        "company_name": company_name,
        "website": result.get("website") or f"https://{domain}",
        "linkedin": result.get("linkedin"),
        "industry": result.get("industry"),
        "revenue": result.get("revenue"),
        "headcount": result.get("headcount"),
        "last_funding": result.get("last_funding"),
        "title": result.get("title"),
        "stage": result.get("stage") or "New",
        "amount": result.get("amount"),
        "icon": result.get("icon") or icon_value,
        "accountIcon": result.get("accountIcon") or icon_value,
        "apollo_status": "replaced_by_ai",
    }


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