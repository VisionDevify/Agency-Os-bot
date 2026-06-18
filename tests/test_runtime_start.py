from app.runtime.railway_start import api_command, bot_command, is_railway_environment, should_start_bot


def test_runtime_detects_railway_environment() -> None:
    assert is_railway_environment({"RAILWAY_ENVIRONMENT_ID": "prod"}) is True
    assert is_railway_environment({"DATABASE_URL": "postgres://example"}) is False


def test_runtime_starts_bot_on_railway_when_required_values_exist() -> None:
    env = {
        "RAILWAY_ENVIRONMENT_ID": "prod",
        "TELEGRAM_BOT_TOKEN": "masked",
        "REDIS_URL": "redis://example",
    }

    assert should_start_bot(env) is True


def test_runtime_does_not_start_bot_locally_by_default() -> None:
    env = {"TELEGRAM_BOT_TOKEN": "masked", "REDIS_URL": "redis://example"}

    assert should_start_bot(env) is False


def test_runtime_bot_start_can_be_disabled_even_on_railway() -> None:
    env = {
        "RAILWAY_ENVIRONMENT_ID": "prod",
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
