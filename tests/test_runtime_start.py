from app.runtime.railway_start import (
    api_command,
    bot_command,
    is_railway_environment,
    runtime_role,
    should_start_api,
    should_start_bot,
)


def test_runtime_detects_railway_environment() -> None:
    assert is_railway_environment({"RAILWAY_ENVIRONMENT_ID": "prod"}) is True
    assert is_railway_environment({"DATABASE_URL": "postgres://example"}) is False


def test_runtime_defaults_railway_to_api_only() -> None:
    env = {
        "RAILWAY_ENVIRONMENT_ID": "prod",
        "TELEGRAM_BOT_TOKEN": "masked",
        "REDIS_URL": "redis://example",
    }

    assert runtime_role(env) == "api"
    assert should_start_api(env) is True
    assert should_start_bot(env) is False


def test_runtime_does_not_treat_public_agency_bot_service_name_as_worker() -> None:
    env = {
        "RAILWAY_ENVIRONMENT_ID": "prod",
        "RAILWAY_SERVICE_NAME": "Agency-Os-bot",
        "TELEGRAM_BOT_TOKEN": "masked",
        "REDIS_URL": "redis://example",
    }

    assert runtime_role(env) == "api"
    assert should_start_api(env) is True
    assert should_start_bot(env) is False


def test_runtime_starts_bot_on_railway_worker_when_required_values_exist() -> None:
    env = {
        "RAILWAY_ENVIRONMENT_ID": "prod",
        "RAILWAY_SERVICE_NAME": "Bot Worker",
        "TELEGRAM_BOT_TOKEN": "masked",
        "REDIS_URL": "redis://example",
    }

    assert runtime_role(env) == "bot"
    assert should_start_api(env) is False
    assert should_start_bot(env) is True


def test_runtime_starts_bot_when_required_values_exist_without_railway_markers() -> None:
    env = {"TELEGRAM_BOT_TOKEN": "masked"}

    assert should_start_api(env) is True
    assert should_start_bot(env) is True


def test_runtime_bot_start_does_not_require_redis() -> None:
    env = {"TELEGRAM_BOT_TOKEN": "masked", "REDIS_URL": ""}

    assert should_start_bot(env) is True


def test_runtime_bot_start_can_be_disabled_for_local_api_container() -> None:
    env = {
        "TELEGRAM_BOT_TOKEN": "masked",
        "REDIS_URL": "redis://example",
        "FORTUNA_START_BOT_WITH_API": "false",
    }

    assert should_start_bot(env) is False


def test_runtime_bot_start_can_be_disabled_even_on_railway() -> None:
    env = {
        "RAILWAY_ENVIRONMENT_ID": "prod",
        "RAILWAY_SERVICE_NAME": "Bot Worker",
        "TELEGRAM_BOT_TOKEN": "masked",
        "REDIS_URL": "redis://example",
        "FORTUNA_START_BOT_WITH_API": "false",
    }

    assert should_start_bot(env) is False


def test_runtime_commands_do_not_embed_secrets() -> None:
    api = " ".join(api_command({"PORT": "9000", "TELEGRAM_BOT_TOKEN": "secret-token"}))
    bot = " ".join(bot_command())

    assert "9000" in api
    assert "app.bot.runner" in bot
    assert "secret-token" not in api
    assert "secret-token" not in bot
