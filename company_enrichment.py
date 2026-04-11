import os
import requests

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")

def _clean(value, default=None):
    if value in ("", None, [], {}):
        return default
    return value


def _format_revenue(value):
    if value in (None, ""):
        return None
    return str(value)


def _format_headcount(value):
    if value in (None, ""):
        return None
    return str(value)


def enrich_company_from_domain(domain: str) -> dict:
    if not domain:
        return {
            "company_name": None,
            "website": None,
            "linkedin": None,
            "industry": None,
            "revenue": None,
            "headcount": None,
            "last_funding": None,
            "icon": None,
            "apollo_status": "skipped",
        }

    if not APOLLO_API_KEY:
        return {
            "company_name": domain.split(".")[0].title(),
            "website": f"https://{domain}",
            "linkedin": None,
            "industry": None,
            "revenue": None,
            "headcount": None,
            "last_funding": None,
            "icon": domain[:1].upper(),
            "apollo_status": "no_api_key",
        }

    try:
        url = "https://api.apollo.io/api/v1/organizations/enrich"
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": APOLLO_API_KEY,
            "Cache-Control": "no-cache",
        }
        payload = {"domain": domain}

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json() or {}
        org = data.get("organization") or data.get("account") or {}

        company_name = _clean(org.get("name"), domain.split(".")[0].title())
        website = _clean(org.get("website_url"), f"https://{domain}")
        linkedin = _clean(org.get("linkedin_url"))
        industry = _clean(org.get("industry"))
        revenue = _format_revenue(_clean(org.get("estimated_annual_revenue")))
        headcount = _format_headcount(_clean(org.get("estimated_num_employees")))
        last_funding = _clean(org.get("latest_funding_stage")) or _clean(org.get("latest_funding_round_date"))
        
        
        print("APOLLO_API_KEY found:", bool(APOLLO_API_KEY))
        print("apollo enrching domain:", domain)
        print("apollo response:", data)
        
        return {
            "company_name": company_name,
            "website": website,
            "linkedin": linkedin,
            "industry": industry,
            "revenue": revenue,
            "headcount": headcount,
            "last_funding": str(last_funding) if last_funding is not None else None,
            "icon": company_name[:1].upper() if company_name else domain[:1].upper(),
            "apollo_status": "enriched",
        }
        

    except Exception as e:
        print("Apollo enriching error:", str(e))
        return {
            "company_name": domain.split(".")[0].title(),
            "website": f"https://{domain}",
            "linkedin": None,
            "industry": None,
            "revenue": None,
            "headcount": None,
            "last_funding": None,
            "icon": domain[:1].upper(),
            "apollo_status": "failed",
        } 