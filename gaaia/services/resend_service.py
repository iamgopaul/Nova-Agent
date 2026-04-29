from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, html: str) -> bool:
    """Send a transactional email via Resend. Returns True on success."""
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    from_email = os.environ.get("RESEND_FROM_EMAIL", "GAAIA <noreply@gaaia.io>").strip()

    if not api_key:
        logger.warning("[Resend] RESEND_API_KEY not set — email not sent to %s", to)
        return False

    try:
        import resend
        resend.api_key = api_key
        resend.Emails.send({
            "from": from_email,
            "to": [to],
            "subject": subject,
            "html": html,
        })
        return True
    except Exception as exc:
        logger.error("[Resend] Failed to send email to %s: %s", to, exc)
        return False


def send_otp_email(to: str, code: str, display_name: str) -> bool:
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px 24px">
      <h2 style="margin:0 0 8px;color:#0f172a;font-size:22px">Your GAAIA verification code</h2>
      <p style="color:#64748b;font-size:14px;margin:0 0 24px">Hi {display_name}, use the code below to sign in.</p>
      <div style="background:#f1f5f9;border-radius:12px;padding:24px;text-align:center;margin:0 0 24px">
        <span style="font-size:36px;font-weight:700;letter-spacing:8px;color:#0f172a">{code}</span>
      </div>
      <p style="color:#94a3b8;font-size:12px;margin:0">This code expires in <strong>10 minutes</strong>.
      If you didn&apos;t request this, you can safely ignore this email.</p>
    </div>
    """
    return send_email(to, "Your GAAIA sign-in code", html)


def send_org_invitation_email(
    to: str, org_name: str, inviter_name: str, invite_url: str
) -> bool:
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px 24px">
      <h2 style="margin:0 0 8px;color:#0f172a;font-size:22px">You&apos;re invited to {org_name}</h2>
      <p style="color:#64748b;font-size:14px;margin:0 0 24px">
        <strong>{inviter_name}</strong> has invited you to join their GAAIA organisation.
      </p>
      <a href="{invite_url}"
         style="display:inline-block;background:#3b82f6;color:#fff;text-decoration:none;
                padding:12px 28px;border-radius:10px;font-weight:600;font-size:15px">
        Accept invitation
      </a>
      <p style="color:#94a3b8;font-size:12px;margin-top:24px">
        This invitation expires in 7 days. If you weren&apos;t expecting this, ignore it.
      </p>
    </div>
    """
    return send_email(to, f"You're invited to {org_name} on GAAIA", html)


def send_scheduled_task_result(to: str, task_name: str, output: str) -> bool:
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:32px 24px">
      <h2 style="margin:0 0 8px;color:#0f172a;font-size:20px">Scheduled task completed: {task_name}</h2>
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;
                  padding:20px;margin-top:16px;font-size:14px;color:#334155;
                  white-space:pre-wrap;font-family:monospace;line-height:1.6">
{output[:4000]}{'…' if len(output) > 4000 else ''}
      </div>
    </div>
    """
    return send_email(to, f"GAAIA task result: {task_name}", html)
