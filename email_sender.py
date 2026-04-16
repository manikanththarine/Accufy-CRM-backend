import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "").strip()
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "sales@aicrmflow.tech").strip()


def send_email(to: str, subject: str, body: str):
    if not SENDGRID_API_KEY:
        raise ValueError("SENDGRID_API_KEY missing")

    message = Mail(
        from_email=DEFAULT_FROM_EMAIL,
        to_emails=to,
        subject=subject,
        plain_text_content=body,
    )

    client = SendGridAPIClient(SENDGRID_API_KEY)
    response = client.send(message)
    return {
        "status_code": response.status_code,
        "body": response.body.decode() if hasattr(response.body, "decode") else str(response.body),
    } 