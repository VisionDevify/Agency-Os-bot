from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardStats:
    total_users: int = 0
    active_users: int = 0
    accounts: int = 0
    healthy_proxies: int = 0
    open_tasks: int = 0
    open_incidents: int = 0


def placeholder_dashboard_stats() -> DashboardStats:
    return DashboardStats(
        total_users=1,
        active_users=1,
        accounts=0,
        healthy_proxies=0,
        open_tasks=0,
        open_incidents=0,
    )
