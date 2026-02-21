from pathlib import Path

from pydantic_settings import BaseSettings


_LOCAL_DATA = Path.home() / ".local" / "share" / "tendermate"


class Settings(BaseSettings):
    claude_model: str = "sonnet"
    data_dir: Path = _LOCAL_DATA
    database_url: str = f"sqlite+aiosqlite:///{_LOCAL_DATA / 'tendermate.db'}"
    frontend_url: str = "http://localhost:5173"
    scraper_url: str = "https://scraper.tools.k4.pl/scrape"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "tenders").mkdir(exist_ok=True)


settings = Settings()
