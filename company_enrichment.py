import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "").strip()
print("APOLLO KEY:", APOLLO_API_KEY)

def normalize_domain(value):
    if not value:
        return None
    value = str(value).strip().lower()
    value = value.replace("https://", "").replace("http://", "")
    value = value.replace("www.", "")
    value = value.split("/")[0]
    value = value.split("?")[0]
    return value or None


def extract_domain_from_email(email):
    if not email or "@" not in email:
        return None
    return normalize_domain(email.split("@")[-1])

def fallback_domain_from_company(company_name):
    if not company_name:
        return None
    slug = re.sub(r"[^a-zA-Z0-9]+", "", company_name).lower()
    if not slug:
        return None
    return f"{slug}.com"

def first_letter(value, default="U"):
    if not value:
        return default
    return str(value).strip()[:1].upper() or default

def get_logo(domain):
    domain = normalize_domain(domain)
    if not domain:
        return None
    return f"https://img.logo.dev/{domain}?size=200"


def _pick_first(*values):
    for value in values:
        if value not in (None, "", [], {}, ()):
            return value
    return None


def apollo_enrich_company(domain):
    domain = normalize_domain(domain)
    if not domain or not APOLLO_API_KEY:
        return {}

    url = "https://api.apollo.io/api/v1/organizations/enrich"
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {APOLLO_API_KEY}",
    }
    params = {
        "domain": domain
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        print("Apollo status:", response.status_code)
        print("Apollo response:", response.text[:1000])

        if response.status_code != 200:
            return {}

        data = response.json() or {}
        org = data.get("organization") or data.get("account") or data

        if not isinstance(org, dict):
            return {}

        name = _pick_first(
            org.get("name"),
            org.get("organization_name"),
            domain.split(".")[0].title()
        )

        website = normalize_domain(
            _pick_first(
                org.get("website_url"),
                org.get("website"),
                org.get("primary_domain"),
                org.get("domain"),
                domain
            )
        )

        linkedin = _pick_first(
            org.get("linkedin_url"),
            org.get("linkedin"),
            (org.get("social_links") or {}).get("linkedin")
        )

        industry = _pick_first(
            org.get("primary_industry"),
            org.get("industry"),
            "Unknown"
        )

        revenue = _pick_first(
            org.get("annual_revenue_printed"),
            org.get("annual_revenue"),
            org.get("estimated_annual_revenue"),
            org.get("revenue"),
            "Unknown"
        )

        headcount = _pick_first(
            org.get("estimated_num_employees"),
            org.get("employee_count"),
            org.get("employees_count"),
            org.get("num_employees"),
            "Unknown"
        )

        last_funding = _pick_first(
            org.get("latest_funding_round"),
            org.get("latest_funding_stage"),
            org.get("funding_stage"),
            org.get("last_funding_round"),
            "Unknown"
        )

        return {
            "name": name,
            "account": name,
            "title": "New Business",
            "accountIcon": first_letter(name),
            "icon": first_letter(name),
            "owner": "Unassigned",
            "industry": str(industry),
            "status": "New",
            "stage": "Lead",
            "amount": None,
            "revenue": str(revenue),
            "headcount": str(headcount),
            "lastInteraction": "Just now",
            "lastFunding": str(last_funding),
            "linkedin": linkedin,
            "website": website,
            "logo": get_logo(website or domain),
        }

    except Exception as e:
        print("Apollo exception:", str(e))
        return {}


def enrich_company_profile(company_name, email):
    domain = extract_domain_from_email(email) or fallback_domain_from_company(company_name)
    apollo = apollo_enrich_company(domain)

    final_name = _pick_first(
        apollo.get("name"),
        company_name,
        domain.split(".")[0].title() if domain else "Unknown Company"
    )
    final_domain = _pick_first(apollo.get("website"), domain)

    return {
        "name": final_name,
        "account": _pick_first(apollo.get("account"), final_name),
        "title": _pick_first(apollo.get("title"), "New Business"),
        "accountIcon": _pick_first(apollo.get("accountIcon"), first_letter(final_name)),
        "icon": _pick_first(apollo.get("icon"), first_letter(final_name)),
        "owner": _pick_first(apollo.get("owner"), "Unassigned"),
        "industry": _pick_first(apollo.get("industry"), "Unknown"),
        "status": _pick_first(apollo.get("status"), "New"),
        "stage": _pick_first(apollo.get("stage"), "Lead"),
        "amount": apollo.get("amount"),
        "revenue": _pick_first(apollo.get("revenue"), "Unknown"),
        "headcount": _pick_first(apollo.get("headcount"), "Unknown"),
        "lastInteraction": _pick_first(apollo.get("lastInteraction"), "Just now"),
        "lastFunding": _pick_first(apollo.get("lastFunding"), "Unknown"),
        "linkedin": apollo.get("linkedin"),
        "website": final_domain,
        "logo": _pick_first(apollo.get("logo"), get_logo(final_domain)),
    } 