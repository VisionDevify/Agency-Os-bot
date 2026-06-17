from fastapi import APIRouter

from app.services.automations import simulation_status
from app.services.healing import self_healing_status
from app.services.proxies import rotation_status

router = APIRouter(prefix="/api")


@router.get("/dashboard")
async def dashboard() -> dict[str, object]:
    return {
        "modules": [
            "users",
            "roles",
            "permissions",
            "audit_logs",
            "accounts",
            "proxies",
            "tasks",
            "incidents",
            "reports",
            "automations",
        ],
        "placeholders": {
            "proxy_rotation": rotation_status(),
            "automation_simulation": simulation_status(),
            "self_healing": self_healing_status(),
        },
    }
