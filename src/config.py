from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigurationError(ValueError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    gam_network_code: str
    gam_application_name: str
    gam_client_id: str
    gam_client_secret: str
    gam_refresh_token: str
    database_url: str
    min_baseline_impressions: int = 1000
    drop_threshold_pct: float = 50.0


def load_settings() -> Settings:
    required_env_vars = {
        'GAM_NETWORK_CODE': os.getenv('GAM_NETWORK_CODE'),
        'GAM_APPLICATION_NAME': os.getenv('GAM_APPLICATION_NAME'),
        'GAM_CLIENT_ID': os.getenv('GAM_CLIENT_ID'),
        'GAM_CLIENT_SECRET': os.getenv('GAM_CLIENT_SECRET'),
        'GAM_REFRESH_TOKEN': os.getenv('GAM_REFRESH_TOKEN'),
        'DATABASE_URL': os.getenv('DATABASE_URL'),
    }

    missing = [name for name, value in required_env_vars.items() if not value]
    if missing:
        joined = ', '.join(sorted(missing))
        raise ConfigurationError(f'Missing required environment variables: {joined}')

    min_baseline_impressions = _parse_int_env(
        'MIN_BASELINE_IMPRESSIONS',
        default=1000,
    )
    drop_threshold_pct = _parse_float_env(
        'DROP_THRESHOLD_PCT',
        default=50.0,
    )

    if min_baseline_impressions < 0:
        raise ConfigurationError('MIN_BASELINE_IMPRESSIONS must be zero or greater')
    if drop_threshold_pct < 0:
        raise ConfigurationError('DROP_THRESHOLD_PCT must be zero or greater')

    return Settings(
        gam_network_code=required_env_vars['GAM_NETWORK_CODE'] or '',
        gam_application_name=required_env_vars['GAM_APPLICATION_NAME'] or '',
        gam_client_id=required_env_vars['GAM_CLIENT_ID'] or '',
        gam_client_secret=required_env_vars['GAM_CLIENT_SECRET'] or '',
        gam_refresh_token=required_env_vars['GAM_REFRESH_TOKEN'] or '',
        database_url=required_env_vars['DATABASE_URL'] or '',
        min_baseline_impressions=min_baseline_impressions,
        drop_threshold_pct=drop_threshold_pct,
    )


def _parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == '':
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f'{name} must be an integer, got {raw_value!r}') from exc


def _parse_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == '':
        return default

    try:
        return float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f'{name} must be a number, got {raw_value!r}') from exc
