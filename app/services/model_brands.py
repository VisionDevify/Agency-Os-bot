from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.audit import AuditLog
from app.models.model_brand import (
    MODEL_BRAND_RELATIONSHIP_TYPES,
    MODEL_BRAND_STATUSES,
    ModelBrand,
    ModelBrandMember,
)
from app.models.user import User
from app.services.auth import USER_STATUS_ACTIVE, audit_action, user_has_permission
from app.services.events import emit_event
from app.services.model_health import ModelHealth, calculate_model_health

RELATIONSHIP_LABELS: dict[str, str] = {
    "manager": "Manager",
    "chatter_manager": "Chatter Manager",
    "senior_chatter": "Senior Chatter",
    "chatter": "Chatter",
    "va": "VA",
    "viewer": "Viewer",
}


def _require_manage_accounts(session: Session, actor: User | None) -> None:
    if not user_has_permission(actor, "manage_accounts"):
        audit_action(
            session,
            actor=actor,
            action="access.denied",
            resource_type="model_brand",
            status="denied",
            details={"permission": "manage_accounts"},
        )
        raise PermissionError("Missing permission: manage_accounts")


def _require_assignment_permission(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_users") or user_has_permission(actor, "manage_accounts"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="model_brand_member",
        status="denied",
        details={"permission": "manage_users_or_manage_accounts"},
    )
    raise PermissionError("Missing permission: manage_users or manage_accounts")


def _model_payload(model_brand: ModelBrand, extra: dict | None = None) -> dict:
    payload = {
        "display_name": model_brand.display_name,
        "stage_name": model_brand.stage_name,
        "status": model_brand.status,
        "country": model_brand.country,
        "timezone": model_brand.timezone,
        "primary_platform": model_brand.primary_platform,
        "is_demo": model_brand.is_demo,
    }
    payload.update(extra or {})
    return payload


def _emit_model_health(session: Session, model_brand: ModelBrand, *, actor: User | None) -> ModelHealth:
    health = calculate_model_health(model_brand)
    emit_event(
        session,
        actor=actor,
        event_name="model.health.changed",
        resource_type="model_brand",
        resource_id=str(model_brand.id),
        payload={
            "score": health.score,
            "status": health.status,
            "label": health.label,
        },
    )
    return health


def list_model_brands(session: Session, *, include_archived: bool = False) -> list[ModelBrand]:
    statement = (
        select(ModelBrand)
        .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
        .order_by(ModelBrand.id)
    )
    if not include_archived:
        statement = statement.where(ModelBrand.status != "archived")
    return list(session.scalars(statement).all())


def get_model_brand(session: Session, model_brand_id: int) -> ModelBrand | None:
    return session.scalar(
        select(ModelBrand)
        .where(ModelBrand.id == model_brand_id)
        .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
    )


def create_model_brand(
    session: Session,
    *,
    display_name: str,
    actor: User,
    stage_name: str | None = None,
    notes: str | None = None,
    country: str | None = None,
    timezone: str | None = None,
    language_preference: str | None = None,
    primary_platform: str | None = None,
    internal_notes: str | None = None,
    status: str = "active",
    is_demo: bool = False,
) -> ModelBrand:
    _require_manage_accounts(session, actor)
    if status not in MODEL_BRAND_STATUSES:
        raise ValueError(f"Invalid model status: {status}")
    model_brand = ModelBrand(
        display_name=display_name,
        stage_name=stage_name,
        status=status,
        notes=notes,
        country=country,
        timezone=timezone,
        language_preference=language_preference,
        primary_platform=primary_platform,
        internal_notes=internal_notes,
        is_demo=is_demo,
    )
    session.add(model_brand)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="model.created",
        resource_type="model_brand",
        resource_id=str(model_brand.id),
        payload=_model_payload(model_brand),
    )
    _emit_model_health(session, model_brand, actor=actor)
    return model_brand


def create_default_model_brand(session: Session, *, actor: User) -> ModelBrand:
    next_number = session.scalar(select(func.count(ModelBrand.id))) or 0
    return create_model_brand(
        session,
        actor=actor,
        display_name=f"New Model {next_number + 1}",
        stage_name=f"model-{next_number + 1}",
        notes="Created from Telegram. TODO: edit profile details.",
    )


def update_model_brand(
    session: Session,
    model_brand: ModelBrand,
    *,
    actor: User,
    display_name: str | None = None,
    stage_name: str | None = None,
    status: str | None = None,
    notes: str | None = None,
    country: str | None = None,
    timezone: str | None = None,
    language_preference: str | None = None,
    primary_platform: str | None = None,
    internal_notes: str | None = None,
) -> ModelBrand:
    _require_manage_accounts(session, actor)
    if status is not None and status not in MODEL_BRAND_STATUSES:
        raise ValueError(f"Invalid model status: {status}")
    if display_name is not None:
        model_brand.display_name = display_name
    if stage_name is not None:
        model_brand.stage_name = stage_name
    if status is not None:
        model_brand.status = status
    if notes is not None:
        model_brand.notes = notes
    if country is not None:
        model_brand.country = country
    if timezone is not None:
        model_brand.timezone = timezone
    if language_preference is not None:
        model_brand.language_preference = language_preference
    if primary_platform is not None:
        model_brand.primary_platform = primary_platform
    if internal_notes is not None:
        model_brand.internal_notes = internal_notes
    session.flush()
    action = "model.disabled" if status == "disabled" else "model.updated"
    emit_event(
        session,
        actor=actor,
        event_name=action,
        resource_type="model_brand",
        resource_id=str(model_brand.id),
        payload=_model_payload(model_brand),
    )
    _emit_model_health(session, model_brand, actor=actor)
    return model_brand


def archive_model_brand(session: Session, model_brand: ModelBrand, *, actor: User) -> ModelBrand:
    _require_manage_accounts(session, actor)
    model_brand.status = "archived"
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="model.archived",
        resource_type="model_brand",
        resource_id=str(model_brand.id),
        payload=_model_payload(model_brand),
    )
    _emit_model_health(session, model_brand, actor=actor)
    return model_brand


def assign_model_member(
    session: Session,
    model_brand: ModelBrand,
    user: User,
    relationship_type: str,
    *,
    actor: User,
) -> ModelBrandMember:
    _require_assignment_permission(session, actor)
    if relationship_type not in MODEL_BRAND_RELATIONSHIP_TYPES:
        raise ValueError(f"Invalid relationship type: {relationship_type}")
    if user.status != USER_STATUS_ACTIVE or not user.is_active:
        raise PermissionError("Only active users can be assigned to a model")
    member = session.get(
        ModelBrandMember,
        {
            "model_brand_id": model_brand.id,
            "user_id": user.id,
            "relationship_type": relationship_type,
        },
    )
    if member is None:
        member = ModelBrandMember(
            model_brand=model_brand,
            user=user,
            relationship_type=relationship_type,
        )
        session.add(member)
        session.flush()
        emit_event(
            session,
            actor=actor,
            event_name="member.assigned",
            resource_type="model_brand",
            resource_id=str(model_brand.id),
            payload={
                "user_id": user.id,
                "relationship_type": relationship_type,
            },
        )
        session.expire(model_brand, ["members"])
        _emit_model_health(session, model_brand, actor=actor)
    return member


def remove_model_member(
    session: Session,
    model_brand: ModelBrand,
    user: User,
    relationship_type: str,
    *,
    actor: User,
) -> None:
    _require_assignment_permission(session, actor)
    member = session.get(
        ModelBrandMember,
        {
            "model_brand_id": model_brand.id,
            "user_id": user.id,
            "relationship_type": relationship_type,
        },
    )
    if member is not None:
        session.delete(member)
        session.flush()
        emit_event(
            session,
            actor=actor,
            event_name="member.removed",
            resource_type="model_brand",
            resource_id=str(model_brand.id),
            payload={
                "user_id": user.id,
                "relationship_type": relationship_type,
            },
        )
        session.expire(model_brand, ["members"])
        _emit_model_health(session, model_brand, actor=actor)


def model_audit_logs(session: Session, model_brand: ModelBrand, *, limit: int = 10) -> list[AuditLog]:
    return list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.resource_type == "model_brand", AuditLog.resource_id == str(model_brand.id))
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        ).all()
    )


def active_users_for_assignment(session: Session) -> list[User]:
    return list(
        session.scalars(
            select(User)
            .where(User.status == USER_STATUS_ACTIVE, User.is_active.is_(True))
            .order_by(User.display_name, User.username, User.id)
        ).all()
    )


def summarize_members(model_brand: ModelBrand) -> dict[str, list[User]]:
    summary: dict[str, list[User]] = {relationship_type: [] for relationship_type in MODEL_BRAND_RELATIONSHIP_TYPES}
    for member in model_brand.members:
        summary.setdefault(member.relationship_type, []).append(member.user)
    return summary


# TODO: attach Accounts through explicit model_brand_id foreign keys.
# TODO: attach Revenue rollups after account foundations exist.
# TODO: attach Proxy Assignments through account or model-level policies.
# TODO: attach Automation Rules once simulation mode has run records.
# TODO: attach Daily Briefings through report/event aggregation.
# TODO: attach AI Operations Brain recommendations from model health and events.
