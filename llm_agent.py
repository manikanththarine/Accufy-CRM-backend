import os
import json
import re
import requests

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
    }


def _parse_json_safely(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}
def analyze_with_openai(text):
    if not OPENAI_API_KEY:
        return _fallback_result("OPENAI_API_KEY missing")

    url = "https://api.openai.com/v1/responses"

    prompt = f"""
You are a CRM AI assistant.

Your job is to score a lead based on BUSINESS INTEREST LEVEL, not keywords.

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
  "auto_reply": true
}}

Scoring rules:
- Score must be between 10 and 100
- DO NOT use fixed numbers like 60, 90, 50
- Generate a realistic score based on actual intensity of interest
- Score should vary naturally, such as 63, 75, 88, 91, 97, etc.
- Avoid rounded numbers unless strongly justified by the message
- Consider urgency, clarity, seriousness, buying readiness, and business intent strength

Interest guidelines:

VERY HIGH INTEREST (85–100):
- Explicit purchase intent
- Asking for quotation, pricing, commercial proposal, contract, implementation timeline
- Ready to proceed / urgent requirement / comparing vendors seriously

HIGH-MEDIUM INTEREST (70–84):
- Strong interest but not finalized
- Asking for demo, proposal, comparison, next steps, detailed discussion

MEDIUM INTEREST (55–69):
- General interest
- Asking about product details, features, use cases, capabilities

LOW INTEREST (30–54):
- Weak, vague, or exploratory message
- No clear next step or buying signal

VERY LOW INTEREST (10–29):
- No interest
- Rejection
- Not relevant

Important:
- Understand business meaning, not just keywords
- Pricing / quotation / commercial request should usually be high interest
- Demo request should usually be high-medium or very high depending on seriousness
- Set priority:
  - high if score >= 80
  - medium if score >= 50 and < 80
  - low if score < 50
- Set status:
  - Hot if score >= 80
  - Warm if score >= 50 and < 80
  - Cold if score < 50
- Return JSON only, with no markdown and no extra text

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

        return {
            "intent": result.get("intent", "Interested lead"),
            "score": int(result.get("score", 61)),
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
        }

    except Exception as e:
        print("OpenAI parsing exception:", str(e))
        return _fallback_result(f"Parsing exception: {str(e)}")


def analyze_lead_with_llm(text):
    return analyze_with_openai(text)


def analyze_reply_action(text):
    return analyze_with_openai(text)
