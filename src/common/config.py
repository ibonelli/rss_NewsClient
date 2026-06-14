"""Configuration loader for pelis-feed.

Loads YAML configuration from config.yaml (or config.yaml.example as fallback).
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

__all__ = ["load_config"]

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = "config.yaml"
_EXAMPLE_CONFIG_PATH = "config.yaml.example"


def load_config(path: str | None = None) -> dict:
    """Load configuration from a YAML file.

    Args:
        path: Optional explicit path to a config file. If None, tries
              config.yaml then config.yaml.example in the current directory.

    Returns:
        Parsed configuration as a dictionary.

    Raises:
        FileNotFoundError: If no config file can be found.
        yaml.YAMLError: If the config file contains invalid YAML.
    """
    if path is not None:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
    else:
        config_path = Path(_DEFAULT_CONFIG_PATH)
        if not config_path.exists():
            config_path = Path(_EXAMPLE_CONFIG_PATH)
            if not config_path.exists():
                raise FileNotFoundError(
                    f"No config file found. Expected {_DEFAULT_CONFIG_PATH} "
                    f"or {_EXAMPLE_CONFIG_PATH} in the current directory."
                )
            logger.warning(
                "config.yaml not found, falling back to %s", _EXAMPLE_CONFIG_PATH
            )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    logger.info("Configuration loaded from %s", config_path)
    return config
