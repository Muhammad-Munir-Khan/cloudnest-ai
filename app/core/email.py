"""Email sending - swappable behind a single send_email() function.

Current implementation: SMTP (Gmail or any SMTP server). To switch to
Resend/SES/etc. later, replace the body of send_email() - nothing else in
the app needs to change.

SMTP is blocking (smtplib), so we run it in a threadpool via asyncio so it
doesn't block the event loop.
"""
import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _send_smtp_sync(
    to: str,
    subject: str,
    body_html: str,
    body_text: str,
) -> None:
    """Blocking SMTP send. Runs in a threadpool via send_email()."""
    if not settings.smtp_user or not settings.smtp_password:
        log.warning(
            "SMTP not configured (SMTP_USER/SMTP_PASSWORD empty) - "
            "email to %s NOT sent. Subject: %s",
            to, subject,
        )
        return

    from_addr = settings.smtp_from or settings.smtp_user
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{from_addr}>"
    msg["To"] = to

    # Attach plain text first, then HTML. Email clients render the last
    # part they can display (HTML), falling back to text.
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(from_addr, [to], msg.as_string())

    log.info("email sent to %s (subject: %s)", to, subject)


async def send_email(
    to: str,
    subject: str,
    body_html: str,
    body_text: str,
) -> None:
    """Send an email. Non-blocking wrapper around the SMTP implementation.

    Swap the internals here to change providers (Resend, SES, etc.) without
    touching any caller.
    """
    try:
        await asyncio.to_thread(
            _send_smtp_sync, to, subject, body_html, body_text
        )
    except Exception as e:
        # Never let an email failure crash the request flow. Log and move on.
        log.error("failed to send email to %s: %s", to, e)


# --- Email templates -------------------------------------------------------

def password_reset_email(reset_link: str) -> tuple[str, str, str]:
    """Return (subject, html_body, text_body) for a password reset email."""
    subject = "Reset your CloudNest password"

    text_body = (
        "You requested a password reset for your CloudNest account.\n\n"
        f"Reset your password here: {reset_link}\n\n"
        "This link expires in 1 hour. If you didn't request this, you can "
        "safely ignore this email."
    )

    html_body = f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0f1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:480px;margin:40px auto;padding:0 20px;">
    <div style="background:#171a21;border:1px solid #262b36;border-radius:16px;padding:36px;">
      <div style="font-size:20px;font-weight:700;color:#22d3ee;margin-bottom:8px;">
        CloudNest<span style="color:#6b7280;font-size:14px;">.ai</span>
      </div>
      <h1 style="font-size:20px;color:#f3f4f6;margin:24px 0 12px;">Reset your password</h1>
      <p style="font-size:14px;line-height:1.6;color:#9ca3af;margin:0 0 24px;">
        You requested a password reset for your CloudNest account. Click the
        button below to choose a new password.
      </p>
      <a href="{reset_link}"
         style="display:inline-block;background:#06b6d4;color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;padding:12px 24px;border-radius:8px;">
        Reset password
      </a>
      <p style="font-size:12px;line-height:1.6;color:#6b7280;margin:24px 0 0;">
        This link expires in 1 hour. If you didn't request this, you can safely
        ignore this email &mdash; your password won't change.
      </p>
      <p style="font-size:11px;color:#4b5563;margin:20px 0 0;word-break:break-all;">
        Or paste this link into your browser:<br>{reset_link}
      </p>
    </div>
    <p style="text-align:center;font-size:11px;color:#4b5563;margin:20px 0;">
      CloudNest.ai &middot; Conversational AI platform
    </p>
  </div>
</body>
</html>"""

    return subject, html_body, text_body


def password_changed_email(when: str) -> tuple[str, str, str]:
    """Return (subject, html_body, text_body) confirming a password change.

    `when` is a preformatted timestamp string (e.g. "May 24, 2026 at 16:32 UTC").
    """
    subject = "Your CloudNest password was changed"

    text_body = (
        "Your CloudNest account password was just changed.\n\n"
        f"When: {when}\n\n"
        "If you made this change, no action is needed.\n\n"
        "If you did NOT change your password, your account may be "
        "compromised. Reset it immediately and contact support."
    )

    html_body = f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0f1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:480px;margin:40px auto;padding:0 20px;">
    <div style="background:#171a21;border:1px solid #262b36;border-radius:16px;padding:36px;">
      <div style="font-size:20px;font-weight:700;color:#22d3ee;margin-bottom:8px;">
        CloudNest<span style="color:#6b7280;font-size:14px;">.ai</span>
      </div>
      <h1 style="font-size:20px;color:#f3f4f6;margin:24px 0 12px;">Your password was changed</h1>
      <p style="font-size:14px;line-height:1.6;color:#9ca3af;margin:0 0 16px;">
        The password for your CloudNest account was just changed.
      </p>
      <div style="background:#1f2430;border:1px solid #262b36;border-radius:8px;padding:14px 16px;margin:16px 0;">
        <p style="font-size:13px;line-height:1.6;color:#d1d5db;margin:0;">
          <span style="color:#6b7280;">When:</span> {when}
        </p>
      </div>
      <p style="font-size:14px;line-height:1.6;color:#9ca3af;margin:0 0 16px;">
        If you made this change, you're all set &mdash; no further action needed.
      </p>
      <div style="background:#1f2430;border:1px solid #3b2530;border-radius:8px;padding:14px 16px;margin:16px 0;">
        <p style="font-size:13px;line-height:1.6;color:#fca5a5;margin:0;">
          If you did NOT make this change, your account may be compromised.
          Reset your password immediately and contact support.
        </p>
      </div>
    </div>
    <p style="text-align:center;font-size:11px;color:#4b5563;margin:20px 0;">
      CloudNest.ai &middot; Conversational AI platform
    </p>
  </div>
</body>
</html>"""

    return subject, html_body, text_body


def _escape_html(s: str) -> str:
    """Minimal HTML escape for arbitrary text dropped into email bodies."""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&#39;")
    )


def account_suspended_email(reason: str | None = None) -> tuple[str, str, str]:
    """Return (subject, html_body, text_body) notifying a user their account
    has been suspended by an administrator.

    `reason` is optional, free-form text the admin entered. We render it inline
    but escape it - admin-typed strings should never be allowed to break out
    of HTML context.
    """
    subject = "Your CloudNest account has been suspended"

    reason_clean = (reason or "").strip()

    if reason_clean:
        text_body = (
            "Your CloudNest account has been suspended by an administrator.\n\n"
            f"Reason: {reason_clean}\n\n"
            "While suspended, you cannot log in or use CloudNest services.\n\n"
            "If you believe this was done in error, please reply to this "
            "email or contact your administrator."
        )
    else:
        text_body = (
            "Your CloudNest account has been suspended by an administrator.\n\n"
            "While suspended, you cannot log in or use CloudNest services.\n\n"
            "If you believe this was done in error, please reply to this "
            "email or contact your administrator."
        )

    reason_html_block = ""
    if reason_clean:
        reason_html_block = f"""
      <div style="background:#1f2430;border:1px solid #262b36;border-radius:8px;padding:14px 16px;margin:16px 0;">
        <p style="font-size:12px;line-height:1.4;color:#6b7280;margin:0 0 4px;text-transform:uppercase;letter-spacing:0.05em;">Reason</p>
        <p style="font-size:14px;line-height:1.6;color:#e5e7eb;margin:0;white-space:pre-wrap;">{_escape_html(reason_clean)}</p>
      </div>"""

    html_body = f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0f1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:480px;margin:40px auto;padding:0 20px;">
    <div style="background:#171a21;border:1px solid #262b36;border-radius:16px;padding:36px;">
      <div style="font-size:20px;font-weight:700;color:#22d3ee;margin-bottom:8px;">
        CloudNest<span style="color:#6b7280;font-size:14px;">.ai</span>
      </div>
      <h1 style="font-size:20px;color:#f3f4f6;margin:24px 0 12px;">Your account has been suspended</h1>
      <p style="font-size:14px;line-height:1.6;color:#9ca3af;margin:0 0 16px;">
        An administrator has suspended your CloudNest account. While suspended,
        you cannot log in or use CloudNest services.
      </p>{reason_html_block}
      <div style="background:#1f2430;border:1px solid #3b2530;border-radius:8px;padding:14px 16px;margin:16px 0;">
        <p style="font-size:13px;line-height:1.6;color:#fca5a5;margin:0;">
          If you believe this was done in error, please reply to this email
          or contact your administrator.
        </p>
      </div>
    </div>
    <p style="text-align:center;font-size:11px;color:#4b5563;margin:20px 0;">
      CloudNest.ai &middot; Conversational AI platform
    </p>
  </div>
</body>
</html>"""

    return subject, html_body, text_body


def account_unsuspended_email() -> tuple[str, str, str]:
    """Return (subject, html_body, text_body) notifying a user their account
    has been restored.
    """
    subject = "Your CloudNest account has been restored"

    text_body = (
        "Good news - your CloudNest account has been restored. You can now "
        "log in and use CloudNest services as normal.\n\n"
        "If you have any questions, contact your administrator."
    )

    html_body = """\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0f1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:480px;margin:40px auto;padding:0 20px;">
    <div style="background:#171a21;border:1px solid #262b36;border-radius:16px;padding:36px;">
      <div style="font-size:20px;font-weight:700;color:#22d3ee;margin-bottom:8px;">
        CloudNest<span style="color:#6b7280;font-size:14px;">.ai</span>
      </div>
      <h1 style="font-size:20px;color:#f3f4f6;margin:24px 0 12px;">Your account has been restored</h1>
      <p style="font-size:14px;line-height:1.6;color:#9ca3af;margin:0 0 16px;">
        Good news &mdash; your CloudNest account has been restored. You can now
        log in and use CloudNest services as normal.
      </p>
      <div style="background:#1f2430;border:1px solid #1f3a2a;border-radius:8px;padding:14px 16px;margin:16px 0;">
        <p style="font-size:13px;line-height:1.6;color:#86efac;margin:0;">
          If you have any questions, contact your administrator.
        </p>
      </div>
    </div>
    <p style="text-align:center;font-size:11px;color:#4b5563;margin:20px 0;">
      CloudNest.ai &middot; Conversational AI platform
    </p>
  </div>
</body>
</html>"""

    return subject, html_body, text_body


def account_deleted_email() -> tuple[str, str, str]:
    """Return (subject, html_body, text_body) notifying a user that their
    account and all associated data have been permanently deleted.

    Sent AFTER the deletion completes - so the user knows it happened and what
    is gone. No "this was an error" recourse line because the deletion is
    irreversible; we explicitly say so to set the right expectation.
    """
    subject = "Your CloudNest account has been deleted"

    text_body = (
        "Your CloudNest account has been deleted by an administrator.\n\n"
        "What was removed:\n"
        "  - Your account and login credentials\n"
        "  - All your chat sessions and messages\n"
        "  - All documents you uploaded\n"
        "  - All vector data derived from those documents\n\n"
        "This action is permanent and cannot be undone. If you believe this "
        "was done in error, please contact your administrator. To use "
        "CloudNest again you would need to create a new account."
    )

    html_body = """\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0f1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:480px;margin:40px auto;padding:0 20px;">
    <div style="background:#171a21;border:1px solid #262b36;border-radius:16px;padding:36px;">
      <div style="font-size:20px;font-weight:700;color:#22d3ee;margin-bottom:8px;">
        CloudNest<span style="color:#6b7280;font-size:14px;">.ai</span>
      </div>
      <h1 style="font-size:20px;color:#f3f4f6;margin:24px 0 12px;">Your account has been deleted</h1>
      <p style="font-size:14px;line-height:1.6;color:#9ca3af;margin:0 0 16px;">
        An administrator has deleted your CloudNest account. All your data has
        been permanently removed.
      </p>
      <div style="background:#1f2430;border:1px solid #262b36;border-radius:8px;padding:14px 16px;margin:16px 0;">
        <p style="font-size:12px;line-height:1.4;color:#6b7280;margin:0 0 8px;text-transform:uppercase;letter-spacing:0.05em;">What was removed</p>
        <ul style="font-size:13px;line-height:1.7;color:#e5e7eb;margin:0;padding-left:18px;">
          <li>Your account and login credentials</li>
          <li>All your chat sessions and messages</li>
          <li>All documents you uploaded</li>
          <li>All vector data derived from those documents</li>
        </ul>
      </div>
      <div style="background:#1f2430;border:1px solid #3b2530;border-radius:8px;padding:14px 16px;margin:16px 0;">
        <p style="font-size:13px;line-height:1.6;color:#fca5a5;margin:0;">
          This action is permanent and cannot be undone. If you believe this
          was done in error, please contact your administrator. To use
          CloudNest again you would need to create a new account.
        </p>
      </div>
    </div>
    <p style="text-align:center;font-size:11px;color:#4b5563;margin:20px 0;">
      CloudNest.ai &middot; Conversational AI platform
    </p>
  </div>
</body>
</html>"""

    return subject, html_body, text_body
