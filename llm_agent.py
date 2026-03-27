import os
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def analyze_with_openai(text):

    url = "https://api.openai.com/v1/responses"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""
    Analyze this lead and return JSON only:

    Lead: {text}

    Return format:
    {{
        "intent": "...",
        "score": number,
        "priority": "...",
        "status": "...",
        "reason": "...",
        "next_action": "...",
        "next_action_type": "..."
    }}
    """

    response = requests.post(
        url,
        headers=headers,
        json={
            "model": "gpt-4.1-mini",
            "input": prompt
        },
        timeout=60
    )

    print("OpenAI status:", response.status_code)
    print("OpenAI response:", response.text)

    if response.status_code != 200:
        return {
            "intent": "Error",
            "score": 50,
            "priority": "medium",
            "status": "Warm",
            "reason": "OpenAI failed",
            "next_action": "Manual review",
            "next_action_type": "manual"
        }

    try:
        output = response.json()
        text_output = output["output"][0]["content"][0]["text"]

        import json
        return json.loads(text_output)

    except Exception as e:
        print("Parsing error:", e)

        return {
            "intent": "Fallback",
            "score": 60,
            "priority": "medium",
            "status": "Warm",
            "reason": "Parsing failed",
            "next_action": "Follow up manually",
            "next_action_type": "manual"
        }