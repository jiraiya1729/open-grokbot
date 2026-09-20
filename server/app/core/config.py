from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")
    app_name: str = "Open-GrokBot API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://grokbot:grokbot@localhost:5432/grokbot"
    auth_mode: str = "local"
    local_user_name: str = "Local User"
    local_user_email: str = "local@open-grokbot.test"
    local_workspace_name: str = "My Workspace"
    cors_origins: str = "http://localhost:3000"
    model_provider: str = "bedrock"
    inngest_event_url: str = "http://localhost:8288/e/dev_key"
    inngest_signing_key: str = ""
    inngest_event_key: str = "dev_key"
    enable_inline_worker: bool = True
    bedrock_region: str = "us-east-1"
    bedrock_model_id: str = "moonshotai.kimi-k2.5"
    recent_message_limit: int = 24
    data_root: str = "./data"
    max_upload_bytes: int = 25 * 1024 * 1024
    computer_provider: str = "docker"
    computer_daemon_url: str = "http://localhost:8010"
    computer_daemon_token: str = "local-computer-daemon"
    computer_viewer_secret: str = "local-viewer-secret-change-me"
    computer_viewer_public_url: str = "http://localhost:8010"
    computer_viewer_ttl_seconds: int = 300
    computer_takeover_ttl_seconds: int = 300
    computer_image: str = "open-grokbot-sandbox:0.3"
    computer_memory_mb: int = 1024
    computer_cpus: float = 1.0
    computer_pids_limit: int = 256
    computer_tool_timeout_seconds: int = 30
    computer_tool_output_bytes: int = 64 * 1024
    app_encryption_key: str = "test-encryption-key-32-chars-long"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
