from dataclasses import dataclass

from app.models.account import Account

ACCOUNT_HEALTH_HEALTHY = "Healthy"
ACCOUNT_HEALTH_WARNING = "Warning"
ACCOUNT_HEALTH_CRITICAL = "Critical"
ACCOUNT_HEALTH_DISABLED = "Disabled"


@dataclass(frozen=True)
class AccountHealth:
    score: int
    status: str
    label: str
    reasons: tuple[str, ...]


def calculate_account_health(account: Account) -> AccountHealth:
    reasons: list[str] = []
    if account.status in {"disabled", "archived"}:
        return AccountHealth(
            score=0,
            status=ACCOUNT_HEALTH_DISABLED,
            label="\u26ab Disabled",
            reasons=("disabled_or_archived",),
        )

    score = 100
    if account.status == "critical":
        score -= 60
        reasons.append("critical_status")
    if account.status == "warning":
        score -= 25
        reasons.append("warning_status")
    if account.auth_status in {"expired", "locked"}:
        score -= 55
        reasons.append(f"auth_{account.auth_status}")
    if account.auth_status == "needs_login":
        score -= 35
        reasons.append("needs_login")
    if account.auth_status == "needs_2fa":
        score -= 30
        reasons.append("needs_2fa")
    if account.auth_status == "not_connected":
        score -= 20
        reasons.append("not_connected")
    if account.model_brand_id is None:
        score -= 30
        reasons.append("unassigned_model_brand")
    # TODO: include missing proxy once proxy assignment semantics exist.

    score = max(0, min(100, score))
    if score >= 80:
        status, label = ACCOUNT_HEALTH_HEALTHY, "\U0001f7e2 Healthy"
    elif score >= 50:
        status, label = ACCOUNT_HEALTH_WARNING, "\U0001f7e1 Warning"
    else:
        status, label = ACCOUNT_HEALTH_CRITICAL, "\U0001f534 Critical"
    return AccountHealth(score=score, status=status, label=label, reasons=tuple(reasons))
