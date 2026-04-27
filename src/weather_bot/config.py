"""Runtime configuration.

Pulled from environment variables with sane defaults. No secrets in Phase 1.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WEATHER_BOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: Path = Field(default=REPO_ROOT / "data" / "weather_bot.db")
    log_dir: Path = Field(default=REPO_ROOT / "logs")
    log_level: str = Field(default="INFO")

    # API endpoints
    open_meteo_ensemble_url: str = "https://ensemble-api.open-meteo.com/v1/ensemble"
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    polymarket_clob_url: str = "https://clob.polymarket.com"
    iem_asos_url: str = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"

    # HTTP behavior
    http_timeout_s: float = 20.0
    http_max_retries: int = 4
    http_backoff_min_s: float = 1.0
    http_backoff_max_s: float = 30.0

    # Cadences (seconds)
    forecast_pull_interval_s: int = 3600        # hourly
    polymarket_pull_interval_s: int = 900       # every 15 minutes
    settlement_check_interval_s: int = 3600     # hourly

    # Models to pull from Open-Meteo ensemble API.
    # gfs025 returns the 31-member GFS ensemble (1 control + 30 perturbed).
    # ecmwf_ifs025 returns the 51-member ECMWF ensemble.
    ensemble_models: tuple[str, ...] = ("gfs025", "ecmwf_ifs025")

    # Forecast horizon to keep (days).
    forecast_days: int = 10

    # Trading thresholds (used by analysis layer, not execution).
    ev_threshold: float = 0.03           # minimum edge to mark would_trade
    kelly_fraction: float = 0.25         # quarter-Kelly cap
    transaction_cost: float = 0.03       # 3 cents round trip default


settings = Settings()
