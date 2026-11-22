from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    database_url: str = 'postgresql+psycopg://umb:umb_local@127.0.0.1:55436/umb'
    data_dir: Path = ROOT / '.data'
    ollama_url: str = 'http://127.0.0.1:11434'
    ollama_model: str = 'umb-bielik'
    embedding_model: Path = ROOT / '.data/models/multilingual-e5-base'
    trusted_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8080", "http://localhost:8080"]
    cookie_secure: bool = False
    max_upload_mb: int = 20
    max_pages: int = 80
    max_page_pixels: int = 40_000_000
    tessdata_prefix: Path = ROOT / '.data/tessdata'
    soffice: str = 'soffice'

settings = Settings()
settings.data_dir = settings.data_dir.resolve()
settings.embedding_model = settings.embedding_model.resolve()
settings.tessdata_prefix = settings.tessdata_prefix.resolve()
for name in ['files', 'exports', 'pages', 'tmp']:
    (settings.data_dir / name).mkdir(parents=True, exist_ok=True)
