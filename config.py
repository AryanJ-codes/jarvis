"""Central configuration — loads .env and exposes typed settings."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
    BRAVE_API_KEY: str = os.environ.get("BRAVE_API_KEY", "")
    GMAIL_ADDRESS: str = os.environ.get("GMAIL_ADDRESS", "")
    GMAIL_APP_PASSWORD: str = os.environ.get("GMAIL_APP_PASSWORD", "")
    DEFAULT_EMAIL: str = os.environ.get("DEFAULT_EMAIL", "")
    DB_PATH: str = os.environ.get("DB_PATH", "jarvis.db")
    MODEL: str = "claude-opus-4-6"
    MAX_TOKENS: int = 4096
    HISTORY_LIMIT: int = 40
    PICOVOICE_ACCESS_KEY: str = os.environ.get("PICOVOICE_ACCESS_KEY", "")
    MORNING_BRIEFING_TIME: str = os.environ.get("MORNING_BRIEFING_TIME", "08:00")
    USER_NAME: str = os.environ.get("USER_NAME", "sir")
    WEB_PORT: int = int(os.environ.get("WEB_PORT", "7777"))

    def validate(self) -> list[str]:
        """Return list of missing required keys."""
        missing = []
        if not self.ANTHROPIC_API_KEY:
            missing.append("ANTHROPIC_API_KEY")
        return missing


config = Config()
