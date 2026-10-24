"""Settings loaded from config/settings.toml, with environment overrides."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "settings.toml"
STATIC_DIR = REPO_ROOT / "data_static"


@dataclass(frozen=True)
class Settings:
    raw: dict[str, Any]
    data_dir: Path
    config_path: Path
    overrides: dict[str, Any] = field(default_factory=dict)

    def section(self, name: str) -> dict[str, Any]:
        return self.raw.get(name, {})

    @property
    def start_date(self) -> date:
        """Start of the record for every council (May 2018)."""
        return date.fromisoformat(self.section("archive").get("start_date", "2018-05-01"))

    @property
    def modgov(self) -> dict[str, Any]:
        return self.section("modgov")

    # Data layout -------------------------------------------------------------
    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def parquet_dir(self) -> Path:
        return self.data_dir / "parquet"


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def load_settings(config_path: str | Path | None = None, **overrides: Any) -> Settings:
    path = _resolve(config_path or os.environ.get("COUNCILS_CONFIG") or DEFAULT_CONFIG)
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    data_dir = _resolve(os.environ.get("COUNCILS_DATA_DIR") or raw.get("paths", {}).get("data_dir", "data"))
    local = data_dir / "settings.local.toml"
    if local.exists():
        with open(local, "rb") as fh:
            for section, values in tomllib.load(fh).items():
                raw.setdefault(section, {}).update(values)
    for dotted, value in overrides.items():
        section, _, key = dotted.partition(".")
        raw.setdefault(section, {})[key] = value
    return Settings(raw=raw, data_dir=data_dir, config_path=path, overrides=overrides)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
