"""The site's settings: config/settings.toml, read by the Where They Stand sites' shared loader (wts-core,
``wts_core.settings``), and the facts about this site that are fixed in its code.

The loader reads config/settings.toml (or the file named by ``COUNCILS_CONFIG``), then ``settings.local.toml`` in
the data folder if there is one (laid over it one level deep), then any overrides given by name
(``**{"usage.daily_spend_cap_usd": 1.0}``). The data folder is ``COUNCILS_DATA_DIR``, else ``[paths] data_dir``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

from wts_core import settings as core

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "settings.toml"
STATIC_DIR = REPO_ROOT / "data_static"
# Raise this whenever the briefing instructions (rag/prompts.py) or the answer's shape change: it is part of the
# answer cache's key, so a briefing written under the old instructions is never served as if written under the new.
INSTRUCTIONS_VERSION = "2"


def _version() -> str:
    try:
        return metadata.version("councils")
    except metadata.PackageNotFoundError:      # run from the source without being installed
        return "0"


SITE = core.Site(
    name="Where Councils Stand",
    package="councils",
    env_prefix="COUNCILS",      # COUNCILS_DATA_DIR, COUNCILS_CONFIG, COUNCILS_ANTHROPIC_API_KEY, COUNCILS_B2_BUCKET…
    root=REPO_ROOT,
    hosts=("wherecouncilsstand.com", "www.wherecouncilsstand.com"),
    state_file="state.db",
    version=_version(),
    instructions_version=INSTRUCTIONS_VERSION,
)


class Settings(core.Settings):
    """The shared package's settings, with this site's own accessors."""

    @property
    def start_date(self) -> date:
        """Start of the record for every council (May 2018)."""
        return date.fromisoformat(self.section("archive").get("start_date", "2018-05-01"))

    @property
    def modgov(self) -> dict[str, Any]:
        return self.section("modgov")

    @property
    def archive(self) -> dict[str, Any]:
        return self.section("archive")

    @property
    def ranking(self) -> dict[str, Any]:
        return self.section("ranking")

    @property
    def embedding(self) -> dict[str, Any]:
        return self.section("embedding")

    # Data layout -------------------------------------------------------------
    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def parquet_dir(self) -> Path:
        return self.data_dir / "parquet"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def logs_dir(self) -> Path:
        """The structured log of briefings (the stages each reached and how it ended; never a reader's words)."""
        return self.data_dir / "logs"

    @property
    def reports_dir(self) -> Path:
        """The weekly reports, written by ``councils weekly-report``."""
        return self.data_dir / "reports"


def load_settings(config_path: str | Path | None = None, env: Mapping[str, str] | None = None,
                  **overrides: Any) -> Settings:
    return core.load_settings(Settings, SITE, config_path, env, **overrides)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
