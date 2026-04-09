
import os
import json
import requests
import re

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def _fallback_result(reason="OpenAI failed"):
    return {
        "intent": "Interested lead",
        "score": 60,
        "priority": "medium",
        "status": "Warm",
        "reason": reason,
        "reply_message": "Thank you for your interest. We will get back to you shortly.",
        "email_subject": "Thanks for reaching out",
        "followup_days": 3,
        "task_title": "Manual review lead",
        "task_description": "Review lead manually because AI response failed.",
        "next_action": "Manual review",
        "next_action_type": "manual_review",
        "auto_reply": True,

        "account": "Unknown Company",
        "accountIcon": "U",
        "icon": "U",
        "owner": "Unassigned",
        "industry": "Unknown",
        "stage": "Lead",
        "amount": None,
        "revenue": "Unknown",
        "headcount": "Unknown",
        "leadScore": 61,
        "aiNextAction": "Manual review",
        "lastInteraction": "Just now",
        "lastFunding": "Unknown",
        "linkedin": None,
        "website": None,
    }


def _parse_json_safely(text_output: str):
    text_output = text_output.strip()

    if text_output.startswith("```"):
        text_output = text_output.replace("```json", "").replace("```", "").strip()

    match = re.search(r"\{.*\}", text_output, re.DOTALL)
    if match:
        text_output = match.group()

    return json.loads(text_output)


def analyze_with_openai(text, company=None, email=None, job_title=None):
    if not OPENAI_API_KEY:
        return _fallback_result("OPENAI_API_KEY missing")

    inferred_company = company or "Unknown Company"
    inferred_domain = None
    if email and "@" in email:
        inferred_domain = email.split("@")[-1].strip().lower()

    url = "https://api.openai.com/v1/responses"

    prompt = f"""
You are a CRM AI assistant.

Your job is to enrich a new lead record and score it based on BUSINESS INTEREST LEVEL, not keywords.

Analyze the message and return ONLY valid JSON in this exact format:

{{
  "intent": "High purchase intent | Requested quotation | Interested lead | Just exploring | Not interested lead",
  "score": 0,
  "priority": "high | medium | low",
  "status": "Hot | Warm | Cold",
  "reason": "short explanation",
  "reply_message": "professional client-friendly email body",
  "email_subject": "professional email subject",
  "followup_days": 0,
  "task_title": "short task title",
  "task_description": "short task description",
  "next_action": "human readable next step",
  "next_action_type": "send_pricing | schedule_demo | send_followup | close_lead | manual_review",
  "auto_reply": true,

  "account": "",
  "accountIcon": "",
  "icon": "",
  "owner": "",
  "industry": "",
  "stage": "",
  "amount": "",
  "revenue": "",
  "headcount": "",
  "leadScore": 0,
  "aiNextAction": "",
  "lastInteraction": "",
  "lastFunding": "",
  "linkedin": "",
  "website": ""
}}

Scoring rules:
- Score must be between 10 and 100
- Do not use fixed values only like 60 or 90
- Generate realistic score based on seriousness, urgency, buying readiness, and business intent strength

Interest guidelines:
- VERY HIGH INTEREST (85–100):
  - Asking for quotation, pricing, proposal, commercial details, implementation timeline
  - Serious vendor comparison
  - Ready to proceed
- HIGH-MEDIUM INTEREST (70–84):
  - Strong interest, asks for demo, detailed discussion, next steps
- MEDIUM INTEREST (55–69):
  - Asks for product details or features with moderate curiosity
- LOW INTEREST (30–54):
  - Weak, vague, exploratory
- VERY LOW INTEREST (10–29):
  - Rejects / not relevant / not interested

Field guidance:
- account = company name if inferable, else use provided company
- accountIcon = first letter of account/company uppercase
- icon = first letter of account/company uppercase
- owner = if unknown, return "Unassigned"
- industry = infer from company/domain/message if possible, else "Unknown"
- stage = choose from Lead, Qualification, Demo, Proposal, Won, Lost
- amount = infer only if clearly present, else null
- revenue = infer only if clearly known, else "Unknown"
- headcount = infer only if clearly known, else "Unknown"
- leadScore = same as score
- aiNextAction = short CRM action sentence
- lastInteraction = "Just now"
- lastFunding = infer only if clearly known, else "Unknown"
- linkedin = company linkedin handle if inferable, else null
- website = company website/domain if inferable, else null

Context:
- Provided company: {inferred_company}
- Provided email domain: {inferred_domain}
- Provided title: {job_title}

Important:
- Understand meaning, not just keywords
- Return STRICT JSON only, no markdown and no extra text

Lead message:
{text}
""".strip()

    try:
        response = requests.post(
            url,
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

        print("OpenAI status:", response.status_code)
        print("OpenAI raw response:", response.text)

        if response.status_code != 200:
            return _fallback_result(
                f"OpenAI failed with status {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        text_output = ""

        for item in data.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") in ["output_text", "text"]:
                        text_output += content.get("text", "")

        if not text_output:
            text_output = data.get("output_text", "")

        print("OpenAI extracted text:", text_output)

        if not text_output.strip():
            return _fallback_result("OpenAI returned empty text output")

        result = _parse_json_safely(text_output)

        account_name = result.get("account") or inferred_company or "Unknown Company"
        first_letter = account_name[:1].upper() if account_name else "U"

        score = int(result.get("score", 61))

        return {
            "intent": result.get("intent", "Interested lead"),
            "score": score,
            "priority": result.get("priority", "medium"),
            "status": result.get("status", "Warm"),
            "reason": result.get("reason", "Lead submitted form"),
            "reply_message": result.get(
                "reply_message",
                "Thank you for your interest. We will get back to you shortly.",
            ),
            "email_subject": result.get("email_subject", "Thanks for reaching out"),
            "followup_days": int(result.get("followup_days", 3)),
            "task_title": result.get("task_title", "Follow up with lead"),
            "task_description": result.get(
                "task_description", "Review lead and continue conversation"
            ),
            "next_action": result.get("next_action", "Send follow-up"),
            "next_action_type": result.get("next_action_type", "send_followup"),
            "auto_reply": bool(result.get("auto_reply", True)),

            "account": account_name,
            "accountIcon": result.get("accountIcon", first_letter),
            "icon": result.get("icon", first_letter),
            "owner": result.get("owner", "Unassigned"),
            "industry": result.get("industry", "Unknown"),
            "stage": result.get("stage", "Lead"),
            "amount": result.get("amount", None),
            "revenue": result.get("revenue", "Unknown"),
            "headcount": result.get("headcount", "Unknown"),
            "leadScore": int(result.get("leadScore", score)),
            "aiNextAction": result.get("aiNextAction", result.get("next_action", "Send follow-up")),
            "lastInteraction": result.get("lastInteraction", "Just now"),
            "lastFunding": result.get("lastFunding", "Unknown"),
            "linkedin": result.get("linkedin", None),
            "website": result.get("website", inferred_domain),
        }

    except Exception as e:
        print("OpenAI parsing exception:", str(e))
        return _fallback_result(f"Parsing exception: {str(e)}")


def analyze_lead_with_llm(text, company=None, email=None, job_title=None):
    return analyze_with_openai(text, company=company, email=email, job_title=job_title)


def analyze_reply_action(text):
    return analyze_with_openai(text)
