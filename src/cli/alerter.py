"""Feed health tracking and email alerting for pelis-feed.

Monitors all configured feeds and sends an email alert via local SMTP when
any feed has been unreachable for longer than the configured threshold.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlalchemy.orm import Session

from src.common.models import FeedHealth

__all__ = ["update_feed_health", "check_and_alert"]

logger = logging.getLogger(__name__)


def _get_or_create_health(session: Session, feed_name: str) -> FeedHealth:
    """Get the FeedHealth row for a feed, creating it if it doesn't exist."""
    health = session.query(FeedHealth).filter(FeedHealth.feed_name == feed_name).first()
    if health is None:
        health = FeedHealth(feed_name=feed_name, consecutive_failures=0)
        session.add(health)
        session.flush()
    return health


def update_feed_health(
    session: Session, feed_name: str, success: bool, error: str | None = None
) -> None:
    """Update the feed health record for a feed after a fetch attempt.

    Args:
        session: SQLAlchemy session.
        feed_name: Logical name of the feed.
        success: Whether the fetch was successful.
        error: Error message if the fetch failed.
    """
    health = _get_or_create_health(session, feed_name)
    now = datetime.utcnow()
    health.last_attempt_at = now

    if success:
        health.last_success_at = now
        health.last_error = None
        health.consecutive_failures = 0
        health.alert_sent_at = None  # Reset alert on recovery
        logger.info("Feed health updated: '%s' success", feed_name)
    else:
        health.last_error = error
        health.consecutive_failures += 1
        logger.warning(
            "Feed health updated: '%s' failure #%d — %s",
            feed_name, health.consecutive_failures, error,
        )

    session.commit()


def check_and_alert(session: Session, config: dict) -> int:
    """Check all feeds for downtime and send alert email if any exceed the threshold.

    Sends one aggregated email listing all degraded feeds. Each feed tracks its
    own alert_sent_at so alerts are not repeated until the feed recovers.

    Args:
        session: SQLAlchemy session.
        config: Application config dict (expects config["alerting"]).

    Returns:
        Number of feeds for which an alert was (newly) sent.
    """
    alerting_config = config.get("alerting", {})
    threshold_hours = alerting_config.get("downtime_threshold_hours", 24)
    threshold = timedelta(hours=threshold_hours)
    now = datetime.utcnow()

    all_health = session.query(FeedHealth).all()
    newly_degraded: list[tuple[FeedHealth, timedelta]] = []

    for health in all_health:
        if health.last_success_at is None:
            continue

        downtime = now - health.last_success_at
        if downtime <= threshold:
            continue

        # Alert already sent for this downtime period
        if health.alert_sent_at is not None and health.alert_sent_at > health.last_success_at:
            continue

        newly_degraded.append((health, downtime))

    if not newly_degraded:
        return 0

    try:
        _send_alert_email(alerting_config, newly_degraded)
        for health, _ in newly_degraded:
            health.alert_sent_at = now
        session.commit()
        logger.info("Feed downtime alert sent for %d feed(s)", len(newly_degraded))
        return len(newly_degraded)
    except Exception as e:
        logger.error("Failed to send alert email: %s", e)
        return 0


def _send_alert_email(
    alerting_config: dict, degraded: list[tuple[FeedHealth, timedelta]]
) -> None:
    """Send a feed downtime alert listing all degraded feeds."""
    smtp_host = alerting_config.get("smtp_host", "localhost")
    smtp_port = alerting_config.get("smtp_port", 25)
    from_address = alerting_config.get("from_address", "pelis-feed@localhost")
    to_address = alerting_config.get("to_address", "user@localhost")

    feed_lines = []
    for health, downtime in degraded:
        hours = int(downtime.total_seconds() // 3600)
        feed_lines.append(f"  - {health.feed_name}: down for ~{hours}h")

    body = (
        "The following pelis-feed sources have been unreachable:\n\n"
        + "\n".join(feed_lines)
        + "\n\nPlease check the feed URLs and network connectivity.\n\n"
        "This is an automated alert from pelis-feed."
    )

    subject = (
        "pelis-feed: 1 feed down"
        if len(degraded) == 1
        else f"pelis-feed: {len(degraded)} feeds down"
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_address
    msg["To"] = to_address
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.send_message(msg)
