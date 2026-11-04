"""Minimal email templates (text + HTML) for auth emails."""

from html import escape


def verification_email(full_name: str, verify_url: str) -> tuple[str, str]:
    """Returns (html_body, text_body)."""
    text = (
        f"Hi {full_name},\n\n"
        "Please verify your Axonweave account by clicking the link below:\n\n"
        f"{verify_url}\n\n"
        "This link expires in 24 hours.\n\n"
        "If you did not create an account, you can ignore this email.\n\n"
        "— The Axonweave team"
    )
    html = f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
<h2>Verify your email</h2>
<p>Hi {escape(full_name)},</p>
<p>Please verify your Axonweave account by clicking the link below:</p>
<p><a href="{escape(verify_url)}" style="display:inline-block;padding:12px 24px;background:#1a1a1a;color:#fff;text-decoration:none;border-radius:6px">Verify email address</a></p>
<p style="color:#888;font-size:13px">This link expires in 24 hours. If you did not create an account, ignore this email.</p>
</body></html>"""
    return html, text


def password_reset_email(full_name: str, reset_url: str) -> tuple[str, str]:
    text = (
        f"Hi {escape(full_name)},\n\n"
        "We received a request to reset the password for your Axonweave account.\n\n"
        f"Click the link below to reset your password:\n\n{escape(reset_url)}\n\n"
        "This link expires in 30 minutes. If you did not request a reset, ignore this email.\n\n"
        "— The Axonweave team"
    )
    html = f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
<h2>Reset your password</h2>
<p>Hi {escape(full_name)},</p>
<p>We received a request to reset the password for your Axonweave account.</p>
<p><a href="{escape(reset_url)}" style="display:inline-block;padding:12px 24px;background:#1a1a1a;color:#fff;text-decoration:none;border-radius:6px">Reset password</a></p>
<p style="color:#888;font-size:13px">This link expires in 30 minutes. If you did not request this, ignore this email.</p>
</body></html>"""
    return html, text


def email_change_email(full_name: str, verify_url: str) -> tuple[str, str]:
    text = (
        f"Hi {full_name},\n\n"
        "We received a request to change the email address on your Axonweave account to this one.\n\n"
        f"Confirm the change by clicking the link below:\n\n{verify_url}\n\n"
        "This link expires in 24 hours. If you did not request this, ignore this email "
        "and your address will not change.\n\n"
        "— The Axonweave team"
    )
    html = f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
<h2>Confirm your new email</h2>
<p>Hi {escape(full_name)},</p>
<p>We received a request to change the email address on your Axonweave account to this one.</p>
<p><a href="{escape(verify_url)}" style="display:inline-block;padding:12px 24px;background:#1a1a1a;color:#fff;text-decoration:none;border-radius:6px">Confirm new email</a></p>
<p style="color:#888;font-size:13px">This link expires in 24 hours. If you did not request this, ignore this email and your address will not change.</p>
</body></html>"""
    return html, text
