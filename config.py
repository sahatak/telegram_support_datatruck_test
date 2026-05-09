import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    BOT_TOKEN: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))

    SUPABASE_URL: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    SUPABASE_KEY: str = field(default_factory=lambda: os.getenv("SUPABASE_SERVICE_KEY", ""))

    VECTOR_TABLE: str = field(default_factory=lambda: os.getenv("VECTOR_TABLE", "documents"))
    CONTENT_COLUMN: str = field(default_factory=lambda: os.getenv("CONTENT_COLUMN", "content"))

    def validate(self) -> None:
        missing = [
            name
            for name, value in [
                ("BOT_TOKEN", self.BOT_TOKEN),
                ("SUPABASE_URL", self.SUPABASE_URL),
                ("SUPABASE_KEY", self.SUPABASE_KEY),
            ]
            if not value
        ]
        if missing:
            raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")


config = Config()
