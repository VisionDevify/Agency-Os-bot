from __future__ import annotations

from app.bot.screens.command_center import (
    render_command_center_home,
    render_score_detail_page,
    render_scores_page,
)
from app.models.command_center import ScoreSnapshot
from app.services.auth import setup_owner_if_needed
from app.services.live_scores import SCORE_WEIGHTS, build_command_center_report, record_score_snapshots
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.reliability import SHORTCUT_BY_COMMAND, render_command_shortcut
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=7101, owner_telegram_id=7101, display_name="Owner")


def _principal(owner) -> PermissionPrincipal:
    return PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)


def test_score_weights_sum_to_100() -> None:
    for score_name, weights in SCORE_WEIGHTS.items():
        assert sum(weights.values()) == 100, score_name


def test_command_center_home_is_simple_and_evidence_backed() -> None:
    with session_scope() as session:
        owner = _owner(session)
        screen = render_command_center_home(session, owner)

        assert "Fortuna Command Center" in screen.text
        assert "Agency OS Readiness" in screen.text
        assert "Fastest Gain" in screen.text
        assert "metadata_json" not in screen.text
        assert "callback_data" not in screen.text
        assert "entity_id" not in screen.text


def test_scores_and_score_details_show_breakdown_without_raw_ids() -> None:
    with session_scope() as session:
        owner = _owner(session)
        scores = render_scores_page(session, owner)
        detail = render_score_detail_page(session, "revenue_intelligence", owner)

        assert "Scores" in scores.text
        assert "deterministic" in scores.text
        assert "Revenue Intelligence" in detail.text
        assert "Breakdown" in detail.text
        assert "Fan Data" in detail.text
        assert "No fan data model is connected yet." in detail.text
        assert "raw" not in detail.text.casefold()


def test_missing_revenue_data_lowers_confidence() -> None:
    with session_scope() as session:
        _owner(session)
        report = build_command_center_report(session)
        revenue = report.scores["revenue_intelligence"]

        assert revenue.score_percent < 40
        assert revenue.confidence == "low"
        assert any("Fan" in item or "whale" in item.casefold() for item in revenue.weak_spots)


def test_score_snapshots_record_only_meaningful_changes() -> None:
    with session_scope() as session:
        _owner(session)
        report = build_command_center_report(session)
        created = record_score_snapshots(session, report.scores.values())
        second = record_score_snapshots(session, report.scores.values())

        assert created
        assert second == ()
        assert session.query(ScoreSnapshot).count() == len(created)


def test_new_and_legacy_command_shortcuts_route_to_screens() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        expected = {
            "command_center": "Fortuna Command Center",
            "scores": "Scores",
            "intelligence": "Intelligence",
            "operations": "Operations",
            "systems": "Systems",
            "admin": "Admin",
            "reliability": "Reliability Center",
            "recovery": "Recovery",
        }

        for command, marker in expected.items():
            assert command in SHORTCUT_BY_COMMAND
            screen = render_command_shortcut(session, command=command, principal=principal, user=owner)
            assert marker in screen.text
