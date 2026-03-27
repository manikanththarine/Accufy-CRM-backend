import os
import json
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


def analyze_with_openai(text):
    if not OPENAI_API_KEY:
        return _fallback_result("OPENAI_API_KEY missing")

    url = "https://api.openai.com/v1/responses"

    prompt = f"""
You are a CRM AI assistant.

Your job is to score a lead based on BUSINESS INTEREST LEVEL, not keywords.

Analyze the message and return JSON:

{{
  "intent": "...",
  "score": number,
  "priority": "...",
  "status": "...",
  "reason": "...",
  "next_action": "...",
  "next_action_type": "..."
}}

Scoring Rules:

HIGH INTEREST (85–95):
- Asking for pricing, quotation, cost
- Asking for demo or meeting
- Asking for proposal or timeline
- Comparing vendors
- Ready to proceed

MEDIUM INTEREST (60–80):
- Asking for product details
- Wants to understand features
- Exploring options

LOW INTEREST (30–55):
- Vague or unclear message
- Just browsing
- No clear intent

NO INTEREST (10–25):
- Not interested
- Rejecting

IMPORTANT:
- Understand meaning, not keywords
- Pricing = HIGH score
- Demo = HIGH score
- Return only JSON

Lead message:
{text}
"""

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
            return _fallback_result(f"OpenAI failed with status {response.status_code}: {response.text[:200]}")

        data = response.json()

        text_output = ""

        # Robust extraction for Responses API
        for item in data.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") in ["output_text", "text"]:
                        text_output += content.get("text", "")

        if not text_output:
            # backup extraction
            text_output = data.get("output_text", "")

        print("OpenAI extracted text:", text_output)

        if not text_output.strip():
            return _fallback_result("OpenAI returned empty text output")

        result = json.loads(text_output)

        return {
            "intent": result.get("intent", "Interested lead"),
            "score": int(result.get("score", 60)),
            "priority": result.get("priority", "medium"),
            "status": result.get("status", "Warm"),
            "reason": result.get("reason", "Lead submitted form"),
            "reply_message": result.get("reply_message", "Thank you for your interest. We will get back to you shortly."),
            "email_subject": result.get("email_subject", "Thanks for reaching out"),
            "followup_days": int(result.get("followup_days", 3)),
            "task_title": result.get("task_title", "Follow up with lead"),
            "task_description": result.get("task_description", "Review lead and continue conversation"),
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