"""
Kavach — Configuration Management
==================================
Centralized configuration loading with validation and sensible defaults.
"""
import os
from typing import Optional


class Config:
    """Application configuration with environment variable validation."""
    
    # Weather Provider Settings
    IMD_ENABLED: bool = os.getenv("IMD_ENABLED", "false").lower() == "true"
    IMD_API_KEY: Optional[str] = os.getenv("IMD_API_KEY") or None
    IMD_API_BASE_URL: str = os.getenv("IMD_API_BASE_URL", "https://mausam.imd.gov.in/api")
    
    WEATHER_ENABLE_FALLBACK: bool = os.getenv("WEATHER_ENABLE_FALLBACK", "true").lower() == "true"
    WEATHER_DEMO_FALLBACK: bool = os.getenv("WEATHER_DEMO_FALLBACK", "false").lower() == "true"
    
    # Location Settings
    WEATHER_COUNTRY: str = os.getenv("WEATHER_COUNTRY", "India")
    WEATHER_STATE: str = os.getenv("WEATHER_STATE", "West Bengal")
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")
    
    # Cache Settings (in seconds)
    WEATHER_CACHE_TTL_CURRENT_S: int = int(os.getenv("WEATHER_CACHE_TTL_CURRENT_S", "600"))
    WEATHER_CACHE_TTL_FORECAST_S: int = int(os.getenv("WEATHER_CACHE_TTL_FORECAST_S", "3600"))
    WEATHER_CACHE_TTL_WARNINGS_S: int = int(os.getenv("WEATHER_CACHE_TTL_WARNINGS_S", "300"))
    WEATHER_STALE_AFTER_S: int = int(os.getenv("WEATHER_STALE_AFTER_S", "1800"))
    
    # Historical Data
    DATA_GOV_IN_API_KEY: Optional[str] = os.getenv("DATA_GOV_IN_API_KEY") or None
    
    # Testing
    KAVACH_RUN_LIVE_INTEGRATION_TESTS: bool = os.getenv("KAVACH_RUN_LIVE_INTEGRATION_TESTS", "false").lower() == "true"
    
    # API Settings
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_WORKERS: int = int(os.getenv("API_WORKERS", "1"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    @classmethod
    def validate(cls) -> list[str]:
        """Validate configuration and return list of warnings."""
        warnings = []
        
        # Warn if IMD is enabled but likely not configured
        if cls.IMD_ENABLED and not cls.IMD_API_KEY:
            warnings.append(
                "IMD_ENABLED=true but IMD_API_KEY is not set. "
                "IMD requires IP whitelisting; set IMD_ENABLED=false until whitelisted."
            )
        
        # Warn if demo fallback is enabled (should only be for demos)
        if cls.WEATHER_DEMO_FALLBACK:
            warnings.append(
                "WEATHER_DEMO_FALLBACK=true. This should only be enabled for demos/offline mode. "
                "Set to false for production with real weather data."
            )
        
        # Warn if cache TTLs are too short (could hammer APIs)
        if cls.WEATHER_CACHE_TTL_CURRENT_S < 300:
            warnings.append(
                f"WEATHER_CACHE_TTL_CURRENT_S={cls.WEATHER_CACHE_TTL_CURRENT_S}s is very short. "
                "Consider 600s (10min) minimum to avoid excessive API calls."
            )
        
        # Warn if running in debug mode
        if cls.DEBUG:
            warnings.append(
                "DEBUG=true. Disable debug mode in production for security and performance."
            )
        
        return warnings
    
    @classmethod
    def summary(cls) -> dict:
        """Return configuration summary (safe for logging - no secrets)."""
        return {
            "weather_provider": {
                "imd_enabled": cls.IMD_ENABLED,
                "fallback_enabled": cls.WEATHER_ENABLE_FALLBACK,
                "demo_fallback": cls.WEATHER_DEMO_FALLBACK,
            },
            "location": {
                "country": cls.WEATHER_COUNTRY,
                "state": cls.WEATHER_STATE,
                "timezone": cls.TIMEZONE,
            },
            "cache_ttl": {
                "current": f"{cls.WEATHER_CACHE_TTL_CURRENT_S}s",
                "forecast": f"{cls.WEATHER_CACHE_TTL_FORECAST_S}s",
                "warnings": f"{cls.WEATHER_CACHE_TTL_WARNINGS_S}s",
            },
            "api": {
                "host": cls.API_HOST,
                "port": cls.API_PORT,
                "workers": cls.API_WORKERS,
                "debug": cls.DEBUG,
            },
        }


# Validate on import
_warnings = Config.validate()
if _warnings:
    import sys
    print("⚠️  Configuration warnings:", file=sys.stderr)
    for warning in _warnings:
        print(f"  - {warning}", file=sys.stderr)
