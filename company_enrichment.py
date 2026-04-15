from llm_agent import enrich_company_with_ai


# -------------------------------------------------------------------
# AI-only company enrichment wrapper
# -------------------------------------------------------------------
# This file keeps the same function name so the rest of the backend
# does not break, but internally it uses AI instead of Apollo.
def enrich_company_from_domain(domain: str, sender_name: str = "", sender_email: str = "", subject: str = "", snippet: str = "") -> dict:
    return enrich_company_with_ai(
        domain=domain,
        sender_name=sender_name,
        sender_email=sender_email,
        subject=subject,
        snippet=snippet,
    ) 