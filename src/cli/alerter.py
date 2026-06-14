"""Feed health tracking and email alerting for pelis-feed.

Monitors RSS feed health and sends email alerts via local SMTP when the
feed has been unreachable for longer than the configured threshold.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy.orm import Session

from src.common.models import FeedHealth

__all__ = ["update_feed_health", "check_and_alert"]

logger = logging.getLogger(__name__)


def _get_or_create_health(session: Session) -> FeedHealth:
    """Get the single FeedHealth row, creating it if it doesn't exist."""
    health = session.query(FeedHealth).first()
    if health is None:
        health = FeedHealth(
            consecutive_failures=0,
        )
        session.add(health)
        session.flush()
    return health


def update_feed_health(
    session: Session, success: bool, error: str | None = None
) -> None:
    """Update the feed health record after a fetch attempt.

    Args:
        session: SQLAlchemy session.
        success: Whether the fetch was successful.
        error: Error message if the fetch failed.
    """
    health = _get_or_create_health(session)
    now = datetime.now(timezone.utc)
    health.last_attempt_at = now

    if success:
        health.last_success_at = now
        health.last_error = None
        health.consecutive_failures = 0
        health.alert_sent_at = None  # Reset alert on recovery
        logger.info("Feed health updated: success")
    else:
        health.last_error = error
        health.consecutive_failures += 1
        logger.warning(
            "Feed health updated: failure #%d — %s",
            health.consecutive_failures,
            error,
        )

    session.commit()


def check_and_alert(session: Session, config: dict) -> bool:
    """Check if feed downtime exceeds threshold and send alert if needed.

    Args:
        session: SQLAlchemy session.
        config: Application config dict (expects config["alerting"]).

    Returns:
        True if an alert was sent, False otherwise.
    """
    alerting_config = config.get("alerting", {})
    threshold_hours = alerting_config.get("downtime_threshold_hours", 24)

    health = _get_or_create_health(session)
    now = datetime.now(timezone.utc)

    # If we've never had a successful fetch, can't determine downtime
    if health.last_success_at is None:
        logger.debug("No successful fetch recorded yet, skipping alert check")
        return False

    downtime = now - health.last_success_at
    threshold = timedelta(hours=threshold_hours)

    if downtime <= threshold:
        logger.debug("Feed downtime (%s) within threshold (%s)", downtime, threshold)
        return False

    # Check if we already sent an alert for this downtime period
    if health.alert_sent_at is not None and health.alert_sent_at > health.last_success_at:
        logger.debug("Alert already sent for this downtime period")
        return False

    # Send alert
    try:
        _send_alert_email(alerting_config, downtime)
        health.alert_sent_at = now
        session.commit()
        logger.info("Feed downtime alert sent (downtime: %s)", downtime)
        return True
    except Exception as e:
        logger.error("Failed to send alert email: %s", e)
        return False


def _send_alert_email(alerting_config: dict, downtime: timedelta) -> None:
    """Send a feed downtime alert via SMTP.

    Args:
        alerting_config: Alerting section of the config.
        downtime: How long the feed has been down.
    """
    smtp_host = alerting_config.get("smtp_host", "localhost")
    smtp_port = alerting_config.get("smtp_port", 25)
    from_address = alerting_config.get("from_address", "pelis-feed@localhost")
    to_address = alerting_config.get("to_address", "user@localhost")

    hours = int(downtime.total_seconds() // 3600)

    msg = EmailMessage()
    msg["Subject"] = "pelis-feed: RSS feed down for >24h"
    msg["From"] = from_address
    msg["To"] = to_address
    msg.set_content(
        f"The pelis-feed RSS source has been unreachable for approximately "
        f"{hours} hours.\n\n"
        f"Please check the feed URL and network connectivity.\n\n"
        f"This is an automated alert from pelis-feed."
    )

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.send_message(msg)
