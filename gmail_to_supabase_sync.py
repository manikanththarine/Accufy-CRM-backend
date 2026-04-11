from gmail_reader import extract_companies_from_gmail
from company_enrichment import enrich_company_profile
from llm_agent import analyze_lead_with_llm
from supabase_db import insert_lead, update_lead, find_lead_by_email, find_lead_by_website


def build_lead_payload(gmail_item, enrichment, analysis):
    company = enrichment.get("account") or enrichment.get("name") or gmail_item.get("domain")
    score = int(analysis.get("score", 60))
    lead_score = int(analysis.get("leadScore", score))

    return {
        "name": gmail_item.get("sender_name") or company,
        "company": company,
        "account": company,
        "title": enrichment.get("title") or "New Business",
        "job_title": None,
        "email": gmail_item.get("sender_email"),
        "phone": None,
        "source": "Gmail",
        "description": f"Subject: {gmail_item.get('subject', '')}\n\nBody:\n{(gmail_item.get('body') or '')[:3000]}",
        "intent": analysis.get("intent", "Interested lead"),
        "score": score,
        "priority": analysis.get("priority", "medium"),
        "reason": analysis.get("reason", "Lead discovered from Gmail"),
        "status": analysis.get("status", enrichment.get("status", "New")),
        "stage": analysis.get("stage", enrichment.get("stage", "Lead")),
        "amount": analysis.get("amount", enrichment.get("amount")),
        "revenue": enrichment.get("revenue", "Unknown"),
        "headcount": enrichment.get("headcount", "Unknown"),
        "industry": enrichment.get("industry", "Unknown"),
        "lead_score": lead_score,
        "ai_next_action": analysis.get("aiNextAction", "Review and qualify lead"),
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
        "email_subject": "",
        "email_body": "",
    }


def sync_gmail_companies_to_supabase(max_results=20):
    gmail_companies = extract_companies_from_gmail(max_results=max_results)

    inserted = 0
    updated = 0

    for item in gmail_companies:
        sender_email = item.get("sender_email")
        domain = item.get("domain")

        enrichment = enrich_company_profile(company_name=domain, email=sender_email)

        ai_text = f"""
Lead source: Gmail
Sender: {item.get('sender_name') or 'Unknown'}
Sender email: {sender_email or 'Unknown'}
Domain: {domain or 'Unknown'}
Subject: {item.get('subject') or ''}
Body:
{item.get('body') or ''}

Company details:
Company: {enrichment.get('account') or enrichment.get('name') or 'Unknown'}
Industry: {enrichment.get('industry') or 'Unknown'}
Revenue: {enrichment.get('revenue') or 'Unknown'}
Headcount: {enrichment.get('headcount') or 'Unknown'}
LinkedIn: {enrichment.get('linkedin') or 'Unknown'}
Website: {enrichment.get('website') or 'Unknown'}
""".strip()

        analysis = analyze_lead_with_llm(
            text=ai_text,
            company=enrichment.get("account") or domain,
            email=sender_email,
            job_title=None,
            enrichment=enrichment,
        )

        payload = build_lead_payload(item, enrichment, analysis)

        existing = None
        if sender_email:
            existing = find_lead_by_email(sender_email)
        if not existing and enrichment.get("website"):
            existing = find_lead_by_website(enrichment.get("website"))

        if existing:
            update_lead(existing["id"], payload)
            updated += 1
            print("Updated:", company)
        else:
            insert_lead(payload)
            inserted += 1
            print("Inserted:", company)

    return {
        "inserted": inserted,
        "updated": updated,
        "total_processed": len(gmail_companies),
    }


if __name__ == "__main__":
    result = sync_gmail_companies_to_supabase(max_results=10)
    print(result) 