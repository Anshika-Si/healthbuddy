"""Email delivery over plain SMTP — works with Gmail, Brevo, Resend, SES, etc.

Configure with environment variables (see EMAIL_SETUP.md):
    HB_SMTP_HOST      e.g. smtp.gmail.com
    HB_SMTP_PORT      587 (STARTTLS, default) or 465 (SSL)
    HB_SMTP_USER      the login for the SMTP service
    HB_SMTP_PASS      app password / API key
    HB_MAIL_FROM      address subscribers see (defaults to HB_SMTP_USER)
    HB_MAIL_FROM_NAME display name (default "HealthBuddy")

If nothing is configured the app still works: codes are written to the server
log, and in dev mode the API returns them so the flow stays testable. Nothing
is ever silently faked to the user.

Sending happens on a background thread because SMTP handshakes can take
several seconds and no user should watch a spinner for that.
"""
import os
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr

BRAND = "#FF5C8A"


def config():
    host = os.environ.get("HB_SMTP_HOST", "").strip()
    user = os.environ.get("HB_SMTP_USER", "").strip()
    return {
        "host": host,
        "port": int(os.environ.get("HB_SMTP_PORT", "587")),
        "user": user,
        "password": os.environ.get("HB_SMTP_PASS", ""),
        "from_addr": os.environ.get("HB_MAIL_FROM", "").strip() or user,
        "from_name": os.environ.get("HB_MAIL_FROM_NAME", "HealthBuddy"),
    }


def is_configured():
    c = config()
    return bool(c["host"] and c["user"] and c["password"] and c["from_addr"])


def _deliver(cfg, message):
    context = ssl.create_default_context()
    if cfg["port"] == 465:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20, context=context) as s:
            s.login(cfg["user"], cfg["password"])
            s.send_message(message)
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as s:
            s.ehlo()
            s.starttls(context=context)
            s.login(cfg["user"], cfg["password"])
            s.send_message(message)


def send(to_addr, subject, text_body, html_body=None, logger=None):
    """Queue an email. Returns True if handed to the mail thread, False if no
    provider is configured (caller then relies on the logged fallback)."""
    cfg = config()
    if not is_configured():
        if logger:
            logger.warning("[mail] not configured — would have sent %r to %s", subject, to_addr)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg["from_name"], cfg["from_addr"]))
    msg["To"] = to_addr
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    def worker():
        try:
            _deliver(cfg, msg)
            if logger:
                logger.info("[mail] sent %r to %s", subject, to_addr)
        except Exception as exc:            # network/auth problems must not crash a request
            if logger:
                logger.error("[mail] FAILED to %s: %s", to_addr, exc)

    threading.Thread(target=worker, daemon=True).start()
    return True


def _shell(title, intro, code, outro):
    """One friendly template for both verify and reset — big readable code."""
    return f"""<!DOCTYPE html>
<html><body style="margin:0;background:#F6F1EA;font-family:'Segoe UI',Helvetica,Arial,sans-serif">
  <div style="max-width:480px;margin:32px auto;background:#fff;border-radius:18px;overflow:hidden;
              box-shadow:0 6px 24px rgba(0,0,0,.08)">
    <div style="background:linear-gradient(135deg,#FF8A5C,{BRAND});padding:22px 26px;color:#fff">
      <div style="font-size:22px;font-weight:800">🌱 HealthBuddy</div>
    </div>
    <div style="padding:26px">
      <h1 style="margin:0 0 10px;font-size:20px;color:#241028">{title}</h1>
      <p style="margin:0 0 20px;color:#5b5566;line-height:1.5">{intro}</p>
      <div style="text-align:center;margin:24px 0">
        <div style="display:inline-block;letter-spacing:10px;font-size:34px;font-weight:800;
                    color:#241028;background:#F6F1EA;border-radius:14px;padding:16px 22px">{code}</div>
      </div>
      <p style="margin:0;color:#8a8398;font-size:13px;line-height:1.5">{outro}</p>
    </div>
  </div>
</body></html>"""


def send_verification_code(to_addr, code, logger=None):
    text = (f"Welcome to HealthBuddy!\n\nYour verification code is: {code}\n\n"
            "It expires in 10 minutes. If you didn't sign up, you can ignore this email.")
    html = _shell("Confirm your email 🌱",
                  "Pop this code into the app to finish setting up your account. "
                  "Then your buddy can start nudging you.",
                  code,
                  "This code expires in 10 minutes. Didn't sign up? Just ignore this email.")
    return send(to_addr, "Your HealthBuddy verification code", text, html, logger)


def send_reset_code(to_addr, code, logger=None):
    text = (f"Password reset for HealthBuddy.\n\nYour reset code is: {code}\n\n"
            "It expires in 10 minutes. If you didn't ask for this, ignore this email — "
            "your password stays unchanged.")
    html = _shell("Reset your password 🔑",
                  "Enter this code in the app, then choose a new password.",
                  code,
                  "This code expires in 10 minutes. Didn't request it? Ignore this email — "
                  "your password hasn't changed.")
    return send(to_addr, "Your HealthBuddy password reset code", text, html, logger)
