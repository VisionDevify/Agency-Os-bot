from dataclasses import dataclass

from app.models.model_brand import ModelBrand

HEALTH_HEALTHY = "Healthy"
HEALTH_WARNING = "Warning"
HEALTH_CRITICAL = "Critical"


@dataclass(frozen=True)
class ModelHealthInputs:
    open_incidents: int = 0
    disabled_accounts: int = 0
    warning_accounts: int = 0
    unassigned_manager: bool = False
    unassigned_chatter_team: bool = False


@dataclass(frozen=True)
class ModelHealth:
    score: int
    status: str
    label: str
    inputs: ModelHealthInputs


def _status_for_score(score: int) -> tuple[str, str]:
    if score >= 80:
        return HEALTH_HEALTHY, "\U0001f7e2 Healthy"
    if score >= 50:
        return HEALTH_WARNING, "\U0001f7e1 Warning"
    return HEALTH_CRITICAL, "\U0001f534 Critical"


def calculate_model_health(
    model_brand: ModelBrand,
    *,
    open_incidents: int = 0,
    disabled_accounts: int = 0,
    warning_accounts: int = 0,
) -> ModelHealth:
    relationship_types = {member.relationship_type for member in model_brand.members}
    inputs = ModelHealthInputs(
        open_incidents=open_incidents,
        disabled_accounts=disabled_accounts,
        warning_accounts=warning_accounts,
        unassigned_manager="manager" not in relationship_types,
        unassigned_chatter_team=not (
            {"chatter_manager", "senior_chatter", "chatter"} & relationship_types
        ),
    )
    score = 100
    score -= min(inputs.open_incidents, 5) * 12
    score -= min(inputs.disabled_accounts, 5) * 10
    score -= min(inputs.warning_accounts, 5) * 6
    if inputs.unassigned_manager:
        score -= 20
    if inputs.unassigned_chatter_team:
        score -= 15
    score = max(0, min(100, score))
    status, label = _status_for_score(score)
    return ModelHealth(score=score, status=status, label=label, inputs=inputs)
