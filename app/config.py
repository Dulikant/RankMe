from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    admin_tg_id: int

    gemini_api_key: str

    free_scans_limit: int = 2

    database_url: str = "sqlite+aiosqlite:///./data/bot.db"

    kaspi_phone: str = "+7 700 000 0000"
    kaspi_name: str = "Автор"
    pro_price_kzt: int = 2990
    lifetime_price_kzt: int = 9900

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://") and "asyncpg" not in url:
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


settings = Settings()