"""
Security event logging (D-25).

All security events are emitted on a dedicated 'security' structlog logger.
Fields: correlation_id (from context), event_type, user_id (UUID only, no PII), ip.
Never log: email, full name, password, session id, tokens.
"""

import structlog

_security_log = structlog.get_logger("security")


def log_registration(user_id: str, ip: str) -> None:
    _security_log.info("account_registered", user_id=user_id, ip=ip)


def log_login_success(user_id: str, ip: str) -> None:
    _security_log.info("login_success", user_id=user_id, ip=ip)


def log_login_failure(ip: str, reason: str) -> None:
    _security_log.warning("login_failure", ip=ip, reason=reason)


def log_logout(user_id: str, ip: str) -> None:
    _security_log.info("logout", user_id=user_id, ip=ip)


def log_password_changed(user_id: str, ip: str) -> None:
    _security_log.info("password_changed", user_id=user_id, ip=ip)


def log_email_change_requested(user_id: str, ip: str) -> None:
    _security_log.info("email_change_requested", user_id=user_id, ip=ip)


def log_account_deletion_requested(user_id: str, ip: str) -> None:
    _security_log.warning("account_deletion_requested", user_id=user_id, ip=ip)


def log_password_reset_requested(ip: str) -> None:
    _security_log.info("password_reset_requested", ip=ip)


def log_password_reset_completed(user_id: str, ip: str) -> None:
    _security_log.info("password_reset_completed", user_id=user_id, ip=ip)


def log_verification_email_sent(user_id: str) -> None:
    _security_log.info("verification_email_sent", user_id=user_id)


def log_email_verified(user_id: str, ip: str) -> None:
    _security_log.info("email_verified", user_id=user_id, ip=ip)


def log_rate_limit_hit(ip: str, endpoint: str) -> None:
    _security_log.warning("rate_limit_hit", ip=ip, endpoint=endpoint)


def log_csrf_failure(ip: str, path: str) -> None:
    _security_log.warning("csrf_check_failed", ip=ip, path=path)


def log_session_revoked(user_id: str, reason: str) -> None:
    _security_log.info("session_revoked", user_id=user_id, reason=reason)
