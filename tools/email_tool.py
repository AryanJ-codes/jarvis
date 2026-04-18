"""Email sending via Gmail SMTP with optional file attachments."""

import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import config

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _build_message(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    html: bool = False,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative" if html else "mixed")
    msg["From"] = config.GMAIL_ADDRESS
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc

    subtype = "html" if html else "plain"
    msg.attach(MIMEText(body, subtype))
    return msg


def _send(msg: MIMEMultipart, to: str, cc: str = "") -> dict:
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        return {
            "success": False,
            "error": "Gmail credentials not configured. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env",
        }

    recipients = [to] + ([cc] if cc else [])
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
            server.sendmail(config.GMAIL_ADDRESS, recipients, msg.as_string())
        return {"success": True, "message": f"Email sent to {to}"}
    except smtplib.SMTPAuthenticationError:
        return {
            "success": False,
            "error": "Authentication failed. Check GMAIL_ADDRESS and GMAIL_APP_PASSWORD.",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    html: bool = False,
) -> dict:
    msg = _build_message(to, subject, body, cc=cc, html=html)
    return _send(msg, to, cc=cc)


def send_email_with_attachment(
    to: str,
    subject: str,
    body: str,
    attachment_path: str,
    cc: str = "",
) -> dict:
    if not os.path.exists(attachment_path):
        return {"success": False, "error": f"File not found: {attachment_path}"}

    msg = _build_message(to, subject, body, cc=cc)

    filename = os.path.basename(attachment_path)
    with open(attachment_path, "rb") as fh:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(fh.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)

    return _send(msg, to, cc=cc)
