"""Shared utilities: structured logging, configuration, and helpers.

This module bootstraps ``structlog`` with JSON output for production
and pretty-print for development. It also provides a thin configuration
loader based on environment variables and TOML files.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import structlog


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(*, json_output: bool = False, level: str = "INFO") -> None:
    """Configure ``structlog`` for the process.

    Args:
        json_output: If True, emit JSON lines (production).
                     If False, use coloured console output (development).
        level: Minimum log level (DEBUG / INFO / WARNING / ERROR).
    """
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.get_level_from_name(level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for the given module name.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A structured logger instance.
    """
    return structlog.get_logger(name)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class Config:
    """Simple hierarchical configuration.

    Resolution order (first wins):
        1. Explicit keyword arguments.
        2. Environment variables (``HL_PAPER_<UPPER_KEY>``).
        3. Built-in defaults.

    Example::

        cfg = Config(initial_balance="5000")
        balance = cfg.get_decimal("initial_balance", default=Decimal("10000"))
    """

    # Sensible defaults for a paper trading session.
    _DEFAULTS: dict[str, str] = {
        "initial_balance": "10000",
        "latency_ms": "50",
        "market": "OUTCOME-DEMO",
        "log_level": "INFO",
        "log_json": "false",
        "max_order_size": "1000",
        "max_open_orders": "50",
    }

    ENV_PREFIX = "HL_PAPER_"

    def __init__(self, **overrides: str) -> None:
        self._overrides = {k.lower(): v for k, v in overrides.items()}

    # -- accessors ----------------------------------------------------------

    def get(self, key: str, *, default: Optional[str] = None) -> str:
        """Return a config value as string.

        Args:
            key: Configuration key (case-insensitive).
            default: Fallback if not found anywhere.

        Returns:
            Resolved configuration value.

        Raises:
            KeyError: If the key is not found and no default is provided.
        """
        k = key.lower()

        # 1. explicit override
        if k in self._overrides:
            return self._overrides[k]

        # 2. environment variable
        env_key = f"{self.ENV_PREFIX}{k.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return env_val

        # 3. built-in default
        if k in self._DEFAULTS:
            return self._DEFAULTS[k]

        if default is not None:
            return default

        raise KeyError(f"Config key '{key}' not found")

    def get_int(self, key: str, *, default: Optional[int] = None) -> int:
        """Return a config value as int."""
        try:
            return int(self.get(key))
        except KeyError:
            if default is not None:
                return default
            raise

    def get_decimal(self, key: str, *, default: Optional[Decimal] = None) -> Decimal:
        """Return a config value as ``Decimal``."""
        try:
            return Decimal(self.get(key))
        except KeyError:
            if default is not None:
                return default
            raise

    def get_bool(self, key: str, *, default: Optional[bool] = None) -> bool:
        """Return a config value as bool (``true/1/yes`` → True)."""
        try:
            return self.get(key).lower() in ("true", "1", "yes")
        except KeyError:
            if default is not None:
                return default
            raise


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

def decimal_round(value: Decimal, places: int = 4) -> Decimal:
    """Round a Decimal to the given number of decimal places.

    Args:
        value: The value to round.
        places: Number of decimal places.

    Returns:
        Rounded Decimal.
    """
    quantize_str = "0." + "0" * places
    return value.quantize(Decimal(quantize_str))
