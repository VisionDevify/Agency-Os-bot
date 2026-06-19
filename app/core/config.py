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
    environment: str | None = Field(default=None, alias="APP_ENV")
    allow_sqlite_fallback: bool = Field(default=False, alias="ALLOW_SQLITE_FALLBACK")
    bot_instance_id: str | None = Field(default=None, alias="BOT_INSTANCE_ID")
    bot_primary_instance: bool = Field(default=True, alias="BOT_PRIMARY_INSTANCE")
    allow_polling_without_redis: bool = Field(default=False, alias="ALLOW_POLLING_WITHOUT_REDIS")
    bot_instance_active_seconds: int = Field(default=180, alias="BOT_INSTANCE_ACTIVE_SECONDS")
    proxy_real_health_checks_enabled: bool = Field(default=False, alias="PROXY_REAL_HEALTH_CHECKS_ENABLED")
    proxy_real_location_checks_enabled: bool = Field(default=False, alias="PROXY_REAL_LOCATION_CHECKS_ENABLED")
    proxy_health_timeout_seconds: int = Field(default=10, alias="PROXY_HEALTH_TIMEOUT_SECONDS")
    proxy_location_provider: str = Field(default="ipwhois", alias="PROXY_LOCATION_PROVIDER")
    backup_s3_endpoint: str | None = Field(default=None, alias="BACKUP_S3_ENDPOINT")
    backup_s3_bucket: str | None = Field(default=None, alias="BACKUP_S3_BUCKET")
    backup_s3_region: str | None = Field(default=None, alias="BACKUP_S3_REGION")
    backup_s3_access_key: SecretStr = Field(default=SecretStr(""), alias="BACKUP_S3_ACCESS_KEY")
    backup_s3_secret_key: SecretStr = Field(default=SecretStr(""), alias="BACKUP_S3_SECRET_KEY")
    backup_b2_key_id: SecretStr = Field(default=SecretStr(""), alias="BACKUP_B2_KEY_ID")
    backup_b2_application_key: SecretStr = Field(default=SecretStr(""), alias="BACKUP_B2_APPLICATION_KEY")
    backup_b2_bucket: str | None = Field(default=None, alias="BACKUP_B2_BUCKET")
    telegram_bot_token: SecretStr = Field(default=SecretStr(""), alias="TELEGRAM_BOT_TOKEN")
    database_url: str = Field(default="", alias="DATABASE_URL")
    redis_url: str = Field(default="", alias="REDIS_URL")
    app_secret_key: SecretStr = Field(default=SecretStr(""), alias="APP_SECRET_KEY")
    encryption_key: SecretStr = Field(default=SecretStr(""), alias="ENCRYPTION_KEY")
    owner_telegram_id: int | None = Field(default=None, alias="OWNER_TELEGRAM_ID")


settings = Settings()
