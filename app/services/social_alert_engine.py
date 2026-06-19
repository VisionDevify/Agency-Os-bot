from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.reporting import NotificationDeliveryAttempt
from app.models.social import SocialCommentProfile
from app.models.user import User
from app.services.notifications import active_targets_for_purposes, create_delivery_attempt
from app.services.recommendations import upsert_recommendation
from app.services.social_compliance import compliance_gate
from app.services.social_evidence import profile_evidence, profile_evidence_summary
from app.services.social_events import create_social_event


def profile_lead_alert_text(profile: SocialCommentProfile) -> str:
    return "\n".join(
        [
            "Profile Lead",
            "",
            f"Fortuna found @{profile.username} worth reviewing.",
            "",
            "Why it matters",
            profile_evidence_summary(profile),
            "",
            "Next Best Move",
            "Review the profile manually. Fortuna will not follow, like, or comment.",
        ]
    )


def route_profile_lead_alert(
    session: Session,
    profile: SocialCommentProfile,
    *,
    actor: User | None,
    simulate_only: bool = True,
) -> list[NotificationDeliveryAttempt]:
    evidence = profile_evidence(profile)
    gate = compliance_gate(
        session,
        entity_type="social_comment_profile",
        entity_id=profile.id,
        entity=profile,
        actor=actor,
        action="alert",
        evidence=evidence,
    )
    if not gate.allowed:
        create_social_event(
            session,
            event_type="social.alert.blocked",
            event_category="alert",
            source_module="alert_engine",
            entity_type="social_comment_profile",
            entity_id=profile.id,
            actor=actor,
            status="blocked",
            severity="medium",
            summary=gate.reason,
            details={"compliance_log_id": gate.compliance_log_id},
            evidence=evidence,
        )
        return []
    targets = active_targets_for_purposes(session, ["alerts"])
    if not targets:
        upsert_recommendation(
            session,
            actor=actor,
            recommendation_type="social_profile_alert_target_missing",
            title="Register Fortuna Alerts",
            description="Fortuna found a profile lead, but no Alerts destination is configured yet.",
            severity="warning",
            entity_type="social_comment_profile",
            entity_id=profile.id,
            metadata={"manual_only": True, "simulated": True},
        )
        create_social_event(
            session,
            event_type="social.alert.simulated",
            event_category="alert",
            source_module="alert_engine",
            entity_type="social_comment_profile",
            entity_id=profile.id,
            actor=actor,
            status="skipped",
            severity="low",
            summary="Fortuna simulated this alert because no Alerts target is configured.",
            details={"target_missing": True},
            evidence=evidence,
        )
        return []
    attempts: list[NotificationDeliveryAttempt] = []
    for target in targets:
        attempts.append(
            create_delivery_attempt(
                session,
                target,
                event_type="social.profile_lead.alert",
                actor=actor,
                status="skipped" if simulate_only else "pending",
                metadata={
                    "profile_id": profile.id,
                    "profile": f"@{profile.username}",
                    "simulated": simulate_only,
                    "message": profile_lead_alert_text(profile),
                    "auto_posting": False,
                },
            )
        )
    create_social_event(
        session,
        event_type="social.alert.simulated" if simulate_only else "social.alert.queued",
        event_category="alert",
        source_module="alert_engine",
        entity_type="social_comment_profile",
        entity_id=profile.id,
        actor=actor,
        status="skipped" if simulate_only else "pending",
        severity="info",
        summary="Fortuna prepared a profile lead alert for an approved destination.",
        details={"attempts": len(attempts), "simulated": simulate_only},
        evidence=evidence,
    )
    return attempts
