import pytest

from app.bot.navigation import screen_for_page
from app.models.audit import AuditLog
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.services.auth import (
    USER_STATUS_ACTIVE,
    assign_role_to_user,
    get_or_create_telegram_user,
    setup_owner_if_needed,
)
from app.services.model_brands import (
    archive_model_brand,
    assign_model_member,
    create_model_brand,
    remove_model_member,
    update_model_brand,
)
from app.services.model_health import HEALTH_CRITICAL, HEALTH_HEALTHY, HEALTH_WARNING, calculate_model_health
from app.services.permissions import PermissionPrincipal, RoleName

from tests.utils import session_scope


def _active_user(session, telegram_id: int, display_name: str):
    user = get_or_create_telegram_user(
        session,
        telegram_user_id=telegram_id,
        display_name=display_name,
        owner_telegram_id=1,
    )
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def test_create_update_and_archive_model_emit_events() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)

        model = create_model_brand(
            session,
            actor=owner,
            display_name="Fortuna",
            stage_name="Solstice",
            notes="Launch profile",
        )
        update_model_brand(session, model, actor=owner, display_name="Fortuna Updated", status="warning")
        archive_model_brand(session, model, actor=owner)

        actions = [log.action for log in session.query(AuditLog).all()]
        assert model.display_name == "Fortuna Updated"
        assert model.status == "archived"
        assert "model.created" in actions
        assert "model.updated" in actions
        assert "model.archived" in actions
        assert "model.health.changed" in actions


def test_assign_manager_chatter_and_va() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Team Model")
        manager = _active_user(session, 10, "Manager User")
        chatter = _active_user(session, 11, "Chatter User")
        va = _active_user(session, 12, "VA User")

        assign_model_member(session, model, manager, "manager", actor=owner)
        assign_model_member(session, model, chatter, "chatter", actor=owner)
        assign_model_member(session, model, va, "va", actor=owner)

        memberships = {
            (member.user_id, member.relationship_type)
            for member in session.query(ModelBrandMember).all()
        }
        assert (manager.id, "manager") in memberships
        assert (chatter.id, "chatter") in memberships
        assert (va.id, "va") in memberships
        assert session.query(AuditLog).filter_by(action="member.assigned").count() == 3


def test_remove_assignment_emits_event() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Removal Model")
        manager = _active_user(session, 20, "Manager User")
        assign_model_member(session, model, manager, "manager", actor=owner)

        remove_model_member(session, model, manager, "manager", actor=owner)

        assert session.query(ModelBrandMember).count() == 0
        assert session.query(AuditLog).filter_by(action="member.removed").count() == 1


def test_health_calculation_tracks_team_and_incident_risk() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Health Model")

        health = calculate_model_health(model)
        assert health.status == HEALTH_WARNING
        assert health.inputs.unassigned_manager is True
        assert health.inputs.unassigned_chatter_team is True

        manager = _active_user(session, 30, "Manager User")
        chatter = _active_user(session, 31, "Chatter User")
        assign_model_member(session, model, manager, "manager", actor=owner)
        assign_model_member(session, model, chatter, "chatter", actor=owner)

        healthy = calculate_model_health(model)
        critical = calculate_model_health(model, open_incidents=5, disabled_accounts=5)
        assert healthy.status == HEALTH_HEALTHY
        assert healthy.score == 100
        assert critical.status == HEALTH_CRITICAL


def test_assignment_requires_manage_users_or_manage_accounts() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Permission Model")
        viewer = _active_user(session, 40, "Viewer User")
        assign_role_to_user(session, viewer, RoleName.VIEWER)
        target = _active_user(session, 41, "Target User")

        with pytest.raises(PermissionError):
            assign_model_member(session, model, target, "manager", actor=viewer)

        assert session.query(AuditLog).filter_by(action="access.denied").count() == 1


def test_create_model_requires_manage_accounts() -> None:
    with session_scope() as session:
        setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        viewer = _active_user(session, 50, "Viewer User")
        assign_role_to_user(session, viewer, RoleName.VIEWER)

        with pytest.raises(PermissionError):
            create_model_brand(session, actor=viewer, display_name="Blocked Model")

        assert session.query(ModelBrand).count() == 0
        assert session.query(AuditLog).filter_by(action="access.denied").count() == 1


def test_model_telegram_callbacks_do_not_crash_and_can_create_assign() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        target = _active_user(session, 60, "Assignable User")
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        created_screen = screen_for_page("models:create", principal, session=session, user=owner)
        model = session.query(ModelBrand).one()
        assignment_screen = screen_for_page(
            f"model:{model.id}:team:assign:manager",
            principal,
            session=session,
            user=owner,
        )
        team_screen = screen_for_page(
            f"model:{model.id}:team:assign:manager:{target.id}",
            principal,
            session=session,
            user=owner,
        )
        audit_screen = screen_for_page(f"model:{model.id}:audit", principal, session=session, user=owner)

        assert "Model Detail" in created_screen.text
        assert "Assign Manager" in assignment_screen.text
        assert "Manage Team" in team_screen.text
        assert "Manager: Assignable User" in team_screen.text
        assert "Model Audit History" in audit_screen.text
