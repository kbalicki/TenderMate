from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    claude_model: str = "sonnet"
    data_dir: Path = Path("./data")
    database_url: str = "sqlite+aiosqlite:///./data/tendermate.db"
    frontend_url: str = "http://localhost:5173"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "tenders").mkdir(exist_ok=True)


settings = Settings()
