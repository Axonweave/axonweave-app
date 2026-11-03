"""Minimal email templates (text + HTML) for auth emails."""


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
<p>Hi {full_name},</p>
<p>Please verify your Axonweave account by clicking the link below:</p>
<p><a href="{verify_url}" style="display:inline-block;padding:12px 24px;background:#1a1a1a;color:#fff;text-decoration:none;border-radius:6px">Verify email address</a></p>
<p style="color:#888;font-size:13px">This link expires in 24 hours. If you did not create an account, ignore this email.</p>
</body></html>"""
    return html, text


def password_reset_email(full_name: str, reset_url: str) -> tuple[str, str]:
    text = (
        f"Hi {full_name},\n\n"
        "We received a request to reset the password for your Axonweave account.\n\n"
        f"Click the link below to reset your password:\n\n{reset_url}\n\n"
        "This link expires in 30 minutes. If you did not request a reset, ignore this email.\n\n"
        "— The Axonweave team"
    )
    html = f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
<h2>Reset your password</h2>
<p>Hi {full_name},</p>
<p>We received a request to reset the password for your Axonweave account.</p>
<p><a href="{reset_url}" style="display:inline-block;padding:12px 24px;background:#1a1a1a;color:#fff;text-decoration:none;border-radius:6px">Reset password</a></p>
<p style="color:#888;font-size:13px">This link expires in 30 minutes. If you did not request this, ignore this email.</p>
</body></html>"""
    return html, text
