from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_generation_policy_path() -> Path:
    return repo_root() / "spec" / "policy" / "project_ai_java_mybatis_generation_policy.yaml"


def load_generation_policy(path: str | Path | None = None) -> dict[str, Any]:
    policy_path = Path(path) if path is not None else default_generation_policy_path()
    return yaml.safe_load(policy_path.read_text(encoding="utf-8"))
