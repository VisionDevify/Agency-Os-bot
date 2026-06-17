def self_healing_status() -> dict[str, str]:
    return {
        "status": "simulation_required",
        "message": "Self-healing can rotate and retest proxies, but automatic activation requires owner approval.",
    }
