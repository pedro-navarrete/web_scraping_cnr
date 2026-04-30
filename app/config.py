"""Configuración de la aplicación mediante variables de entorno."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables de entorno con valores por defecto."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Servidor
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # Playwright / navegador
    headless: bool = True
    browser_pool_size: int = 3
    page_timeout_ms: int = 30000

    # URL del CNR
    cnr_url: str = "https://www.e.cnr.gob.sv/ClaveCatastral/"


# Instancia global de configuración
settings = Settings()
