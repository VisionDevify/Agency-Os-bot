from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Fortuna OS Bot"
    app_display_name: str = Field(default="Fortuna OS", alias="APP_DISPLAY_NAME")
    app_version: str | None = Field(default=None, alias="APP_VERSION")
    git_commit: str | None = Field(default=None, alias="GIT_COMMIT")
    deployed_at: str | None = Field(default=None, alias="DEPLOYED_AT")
    railway_deployment_id: str | None = Field(default=None, alias="RAILWAY_DEPLOYMENT_ID")
    telegram_bot_token: SecretStr = Field(default=SecretStr(""), alias="TELEGRAM_BOT_TOKEN")
    database_url: str = Field(default="", alias="DATABASE_URL")
    redis_url: str = Field(default="", alias="REDIS_URL")
    app_secret_key: SecretStr = Field(default=SecretStr(""), alias="APP_SECRET_KEY")
    encryption_key: SecretStr = Field(default=SecretStr(""), alias="ENCRYPTION_KEY")
    owner_telegram_id: int | None = Field(default=None, alias="OWNER_TELEGRAM_ID")


settings = Settings()
