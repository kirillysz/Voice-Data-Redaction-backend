import secrets

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    JWT_SECRET_KEY: str = secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRES: bool = True
    JWT_EXPIRES_MINUTES: int = 30

    UPLOAD_DIR: Path = Path("app/static/uploads")
    OUTPUT_DIR: Path = Path("app/static/output")

    UPLOAD_DIR.mkdir(exist_ok=True, parents=True)
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

    ALLOWED_EXTENSIONS: list = [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".webm"]

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    QWEN_API_URL: str = "http://127.0.0.1:2222"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def create_dirs(self) -> Settings:
        self.UPLOAD_DIR.mkdir(exist_ok=True)
        self.OUTPUT_DIR.mkdir(exist_ok=True)
        return self

settings = Settings()
