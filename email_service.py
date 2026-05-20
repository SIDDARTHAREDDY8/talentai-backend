"""
Email service — Resend integration.
Falls back to console logging in development when RESEND_API_KEY is not set.
"""

import os
import logging

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "TalentAI <noreply@yourdomain.com>")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def _send(to: str, subject: str, html: str) -> None:
    if not RESEND_API_KEY:
        logger.info(f"[EMAIL DEV] To: {to} | Subject: {subject}\n{html}")
        return
    import resend
    resend.api_key = RESEND_API_KEY
    resend.Emails.send({"from": FROM_EMAIL, "to": [to], "subject": subject, "html": html})


def send_password_reset_email(to_email: str, name: str, token: str) -> None:
    url = f"{FRONTEND_URL}/reset-password?token={token}"
    _send(
        to_email,
        "Reset your TalentAI password",
        f"""
        <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#09090b;color:#fafafa;padding:40px;border-radius:12px;">
          <h1 style="color:#6366f1;margin-bottom:8px;">TalentAI</h1>
          <h2 style="font-weight:600;margin-bottom:16px;">Reset your password</h2>
          <p style="color:#a1a1aa;margin-bottom:24px;">Hi {name}, click the button below to reset your password. This link expires in 1 hour.</p>
          <a href="{url}" style="background:#6366f1;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block;margin-bottom:24px;">
            Reset Password
          </a>
          <p style="color:#71717a;font-size:13px;">If you didn't request this, you can safely ignore this email.</p>
        </div>
        """,
    )


def send_welcome_email(to_email: str, name: str) -> None:
    _send(
        to_email,
        "Welcome to TalentAI 🎉",
        f"""
        <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#09090b;color:#fafafa;padding:40px;border-radius:12px;">
          <h1 style="color:#6366f1;margin-bottom:8px;">TalentAI</h1>
          <h2 style="font-weight:600;margin-bottom:16px;">Welcome, {name}!</h2>
          <p style="color:#a1a1aa;margin-bottom:16px;">Your account is ready. Start practising interviews, analyze your resume, and get AI-powered coaching.</p>
          <a href="{FRONTEND_URL}/dashboard" style="background:#6366f1;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block;">
            Go to Dashboard
          </a>
        </div>
        """,
    )
