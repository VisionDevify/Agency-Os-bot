from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from redis import Redis
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.incident import Incident
from app.models.reporting import NotificationDeliveryAttempt
from app.models.task import Task
from app.models.user import AVAILABILITY_STATUSES, SUPPORTED_LANGUAGES, TIME_FORMATS, User, UserAvailability
from app.services.auth import audit_action, user_has_permission
from app.services.notifications import (
    active_targets_for_event,
    create_delivery_attempt,
    record_notification_routed,
)
from app.services.tasks import count_tasks, overdue_tasks
from app.services.incidents import count_incidents
from app.services.recommendations import list_recommendations

COUNTRY_TIMEZONE_QUICK_PICKS: dict[str, tuple[str, ...]] = {
    "United States": ("America/New_York", "America/Chicago", "America/Los_Angeles"),
    "Philippines": ("Asia/Manila",),
    "Serbia": ("Europe/Belgrade",),
    "Colombia": ("America/Bogota",),
    "Brazil": ("America/Sao_Paulo",),
    "United Kingdom": ("Europe/London",),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _require_user_admin(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_users"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="user_preferences",
        status="denied",
        details={"permission": "manage_users"},
    )
    raise PermissionError("Missing permission: manage_users")


def _valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid timezone: {value}") from exc
    return value


def timezone_suggestions_for_country(country: str | None) -> tuple[str, ...]:
    if not country:
        return ("UTC",)
    return COUNTRY_TIMEZONE_QUICK_PICKS.get(country, ("UTC",))


def get_or_create_availability(session: Session, user: User) -> UserAvailability:
    availability = user.availability or session.scalar(
        select(UserAvailability).where(UserAvailability.user_id == user.id)
    )
    if availability is None:
        availability = UserAvailability(
            user_id=user.id,
            status="off_shift",
            timezone=user.timezone or "UTC",
        )
        session.add(availability)
        session.flush()
    user.availability = availability
    return availability


def update_user_localization(
    session: Session,
    user: User,
    *,
    actor: User | None,
    language: str | None = None,
    country: str | None = None,
    timezone: str | None = None,
    time_format: str | None = None,
    require_admin: bool = True,
) -> User:
    if require_admin and actor is not None and actor.id != user.id:
        _require_user_admin(session, actor)
    if language is not None:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Invalid language: {language}")
        user.language = language
        audit_action(
            session,
            actor=actor,
            action="user.language_updated",
            resource_type="user",
            resource_id=str(user.id),
            details={"language": language},
        )
    if country is not None:
        user.country = country
        audit_action(
            session,
            actor=actor,
            action="user.country_updated",
            resource_type="user",
            resource_id=str(user.id),
            details={"country": country},
        )
    if timezone is not None:
        user.timezone = _valid_timezone(timezone)
        availability = get_or_create_availability(session, user)
        availability.timezone = user.timezone
        audit_action(
            session,
            actor=actor,
            action="user.timezone_updated",
            resource_type="user",
            resource_id=str(user.id),
            details={"timezone": user.timezone},
        )
    if time_format is not None:
        if time_format not in TIME_FORMATS:
            raise ValueError(f"Invalid time format: {time_format}")
        user.time_format = time_format
        audit_action(
            session,
            actor=actor,
            action="user.time_format_updated",
            resource_type="user",
            resource_id=str(user.id),
            details={"time_format": time_format},
        )
    session.flush()
    return user


def set_availability(
    session: Session,
    user: User,
    *,
    actor: User | None,
    status: str,
    timezone: str | None = None,
    shift_start_local: time | None = None,
    shift_end_local: time | None = None,
    quiet_hours_start_local: time | None = None,
    quiet_hours_end_local: time | None = None,
) -> UserAvailability:
    if actor is not None and actor.id != user.id:
        _require_user_admin(session, actor)
    if status not in AVAILABILITY_STATUSES:
        raise ValueError(f"Invalid availability status: {status}")
    availability = get_or_create_availability(session, user)
    availability.status = status
    if timezone is not None:
        availability.timezone = _valid_timezone(timezone)
        user.timezone = availability.timezone
    if shift_start_local is not None:
        availability.shift_start_local = shift_start_local
    if shift_end_local is not None:
        availability.shift_end_local = shift_end_local
    if quiet_hours_start_local is not None:
        availability.quiet_hours_start_local = quiet_hours_start_local
    if quiet_hours_end_local is not None:
        availability.quiet_hours_end_local = quiet_hours_end_local
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="availability.updated",
        resource_type="user",
        resource_id=str(user.id),
        details={"status": availability.status, "timezone": availability.timezone},
    )
    return availability


def _time_in_range(current: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def user_in_quiet_hours(user: User, *, now: datetime | None = None) -> bool:
    availability = user.availability
    if availability is None or availability.quiet_hours_start_local is None or availability.quiet_hours_end_local is None:
        return False
    current = (now or _now()).astimezone(ZoneInfo(availability.timezone or user.timezone or "UTC")).time()
    return _time_in_range(current, availability.quiet_hours_start_local, availability.quiet_hours_end_local)


def is_user_available(user: User, *, now: datetime | None = None) -> bool:
    availability = user.availability
    if availability is None:
        return False
    if availability.status != "on_shift":
        return False
    if user_in_quiet_hours(user, now=now):
        return False
    return True


def format_user_datetime(user: User, value: datetime | None) -> str:
    if value is None:
        return "Not set"
    local = value.astimezone(ZoneInfo(user.timezone or "UTC"))
    if user.time_format == "24h":
        return local.strftime("%Y-%m-%d %H:%M %Z")
    return local.strftime("%Y-%m-%d %I:%M %p %Z")


def onboarding_next_step(user: User) -> str:
    if not user.language:
        return "language"
    if not user.country:
        return "country"
    if not user.timezone or user.timezone == "UTC":
        return "timezone"
    if user.time_format not in TIME_FORMATS:
        return "time_format"
    return "pending_approval"


@dataclass(frozen=True)
class RoutingDecision:
    purposes: tuple[str, ...]
    direct_user_allowed: bool
    reason: str


def smart_notification_decision(
    session: Session,
    *,
    event_type: str,
    assigned_user: User | None = None,
    severity: str | None = None,
    escalation_level: int = 0,
    now: datetime | None = None,
) -> RoutingDecision:
    purposes = list(active_purposes_for_event(event_type, severity=severity))
    direct_user_allowed = False
    reason = "purpose_route"
    if assigned_user is not None:
        direct_user_allowed = is_user_available(assigned_user, now=now)
        if direct_user_allowed:
            reason = "assigned_user_on_shift"
        else:
            if "operations" not in purposes:
                purposes.append("operations")
            reason = "assigned_user_unavailable_routed_to_operations"
    if severity == "critical" or escalation_level >= 2:
        for purpose in ("incidents", "owner"):
            if purpose not in purposes:
                purposes.append(purpose)
        reason = "critical_or_escalated"
    return RoutingDecision(tuple(purposes), direct_user_allowed, reason)


def active_purposes_for_event(event_type: str, *, severity: str | None = None) -> tuple[str, ...]:
    if event_type == "incident.created" and severity == "critical":
        return ("owner", "incidents")
    routes = {
        "task.assigned": ("operations",),
        "task.overdue_detected": ("operations",),
        "task.escalated": ("operations", "owner"),
        "proxy.repair.failed": ("incidents", "automation_logs"),
        "proxy.repair.succeeded": ("automation_logs",),
        "briefing.generated": ("owner", "operations"),
        "digest.sent": ("owner", "operations"),
        "accountability.generated": ("operations",),
        "automation.simulated": ("automation_logs",),
    }
    return routes.get(event_type, ())


def route_notification(
    session: Session,
    *,
    actor: User | None,
    event_type: str,
    assigned_user: User | None = None,
    severity: str | None = None,
    escalation_level: int = 0,
) -> tuple[RoutingDecision, list[NotificationDeliveryAttempt]]:
    decision = smart_notification_decision(
        session,
        event_type=event_type,
        assigned_user=assigned_user,
        severity=severity,
        escalation_level=escalation_level,
    )
    attempts: list[NotificationDeliveryAttempt] = []
    event_targets = active_targets_for_event(session, event_type, severity=severity)
    for purpose in decision.purposes:
        targets = [target for target in event_targets if target.purpose == purpose]
        if not targets:
            record_notification_routed(session, actor=actor, event_type=event_type, target_count=0, purpose=purpose)
            continue
        for target in targets:
            attempts.append(
                create_delivery_attempt(
                    session,
                    target,
                    event_type=event_type,
                    actor=actor,
                    metadata={"route_reason": decision.reason, "purpose": purpose},
                )
            )
        record_notification_routed(
            session,
            actor=actor,
            event_type=event_type,
            target_count=len(targets),
            purpose=purpose,
        )
    return decision, attempts


def create_digest_delivery_attempts(
    session: Session,
    *,
    actor: User | None,
    purpose: str,
    event_type: str = "digest.sent",
) -> list[NotificationDeliveryAttempt]:
    targets = [
        target
        for target in active_targets_for_event(session, "briefing.generated")
        if target.purpose == purpose
    ]
    attempts = [
        create_delivery_attempt(
            session,
            target,
            event_type=event_type,
            actor=actor,
            metadata={"purpose": purpose, "source": "daily_digest"},
        )
        for target in targets
    ]
    audit_action(
        session,
        actor=actor,
        action="digest.send_requested",
        resource_type="daily_digest",
        resource_id=purpose,
        details={"purpose": purpose, "target_count": len(attempts)},
    )
    return attempts


def delivery_history(session: Session, *, limit: int = 10) -> list[NotificationDeliveryAttempt]:
    return list(
        session.scalars(
            select(NotificationDeliveryAttempt)
            .order_by(desc(NotificationDeliveryAttempt.attempted_at), desc(NotificationDeliveryAttempt.id))
            .limit(limit)
        ).all()
    )


def manager_command_metrics(session: Session) -> dict:
    users = list(session.scalars(select(User).options(selectinload(User.availability), selectinload(User.roles))).all())
    on_shift = [user for user in users if user.availability and user.availability.status == "on_shift"]
    off_shift = [user for user in users if not user.availability or user.availability.status != "on_shift"]
    open_task_rows = session.execute(
        select(Task.assigned_to_user_id, func.count(Task.id))
        .where(Task.status.in_(("open", "in_progress", "blocked")))
        .group_by(Task.assigned_to_user_id)
    ).all()
    incident_rows = session.execute(
        select(Incident.assigned_to_user_id, func.count(Incident.id))
        .where(Incident.status.in_(("open", "investigating")))
        .group_by(Incident.assigned_to_user_id)
    ).all()
    failed_deliveries = (
        session.scalar(
            select(func.count(NotificationDeliveryAttempt.id)).where(NotificationDeliveryAttempt.status == "failed")
        )
        or 0
    )
    return {
        "on_shift": on_shift,
        "off_shift": off_shift,
        "open_tasks_by_assignee": {user_id: count for user_id, count in open_task_rows},
        "open_incidents_by_assignee": {user_id: count for user_id, count in incident_rows},
        "overdue_tasks": len(overdue_tasks(session)),
        "unresolved_critical_incidents": count_incidents(
            session,
            statuses=("open", "investigating"),
            severity="critical",
        ),
        "owner_admin_recommendations": len(
            [rec for rec in list_recommendations(session, status="open", limit=50) if rec.severity in {"warning", "critical"}]
        ),
        "notification_delivery_failures": failed_deliveries,
        "open_tasks": count_tasks(session, statuses=("open", "in_progress", "blocked")),
        "open_incidents": count_incidents(session, statuses=("open", "investigating")),
    }


class BotPollingGuard:
    def __init__(
        self,
        redis_url: str | None,
        *,
        key: str = "agency_os:bot_polling_lock",
        ttl_seconds: int = 300,
        client: Redis | None = None,
    ) -> None:
        self.redis_url = redis_url
        self.key = key
        self.ttl_seconds = ttl_seconds
        self.token = str(uuid4())
        self.client = client
        self.enabled = bool(redis_url)

    def _client(self) -> Redis:
        if self.client is None:
            self.client = Redis.from_url(self.redis_url)
        return self.client

    def acquire(self) -> bool:
        if not self.enabled:
            return True
        return bool(self._client().set(self.key, self.token, nx=True, ex=self.ttl_seconds))

    def refresh(self) -> bool:
        if not self.enabled:
            return True
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('expire', KEYS[1], ARGV[2])
        end
        return 0
        """
        return bool(self._client().eval(script, 1, self.key, self.token, self.ttl_seconds))

    def release(self) -> None:
        if not self.enabled:
            return
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """
        self._client().eval(script, 1, self.key, self.token)
