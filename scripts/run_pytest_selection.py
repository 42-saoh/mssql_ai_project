#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITE_FILE = ROOT / "tests" / "suites.yaml"


def _load_simple_suite_yaml(text: str) -> dict[str, list[str]]:
    suites: dict[str, list[str]] = {}
    in_suites = False
    current: str | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        stripped = raw_line.strip()
        if stripped == "suites:":
            in_suites = True
            continue
        if not in_suites:
            continue
        if raw_line.startswith("  ") and not raw_line.startswith("    ") and stripped.endswith(":"):
            current = stripped[:-1]
            suites[current] = []
            continue
        if raw_line.startswith("    - ") and current:
            suites[current].append(stripped[2:].strip())
            continue
        raise ValueError(f"Unsupported tests/suites.yaml line: {raw_line}")
    return suites


def _load_suites() -> dict[str, list[str]]:
    if not SUITE_FILE.exists():
        return {}
    text = SUITE_FILE.read_text(encoding="utf-8")
    try:
        import yaml
    except ModuleNotFoundError:
        payload = {"suites": _load_simple_suite_yaml(text)}
    else:
        payload = yaml.safe_load(text) or {}
    suites = payload.get("suites", payload)
    result: dict[str, list[str]] = {}
    for name, targets in suites.items():
        if not isinstance(targets, list):
            raise ValueError(f"Pytest suite alias must map to a list: @{name}")
        result[str(name)] = [str(target) for target in targets]
    return result


def _repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _expand_one(
    target: str,
    suites: dict[str, list[str]],
    stack: tuple[str, ...],
) -> list[str]:
    if target.startswith("@"):
        suite_name = target[1:]
        if not suite_name:
            raise FileNotFoundError("Pytest suite alias is empty.")
        if suite_name in stack:
            chain = " -> ".join((*stack, suite_name))
            raise ValueError(f"Pytest suite alias cycle detected: {chain}")
        if suite_name not in suites:
            raise FileNotFoundError(f"Pytest suite alias does not exist: @{suite_name}")
        collected: list[str] = []
        for suite_target in suites[suite_name]:
            collected.extend(_expand_one(suite_target, suites, (*stack, suite_name)))
        return collected

    path_text, separator, node_selector = target.partition("::")
    raw_path = Path(path_text)
    path = raw_path if raw_path.is_absolute() else ROOT / raw_path
    if not path.exists():
        raise FileNotFoundError(f"Pytest target does not exist: {target}")
    if path.is_dir():
        if separator:
            raise FileNotFoundError(f"Pytest node selector requires a file target: {target}")
        return [
            _repo_relative(item)
            for item in sorted(path.rglob("test_*.py"))
            if item.is_file()
        ]
    if path.suffix == ".py":
        suffix = f"::{node_selector}" if separator else ""
        return [f"{_repo_relative(path)}{suffix}"]
    return []


def expand_targets(raw_targets: list[str]) -> list[str]:
    targets = raw_targets or ["tests"]
    suites = _load_suites()
    collected: list[str] = []
    for target in targets:
        collected.extend(_expand_one(target, suites, ()))
    seen: set[str] = set()
    result: list[str] = []
    for item in collected:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def split_targets_and_pytest_args(raw_args: list[str]) -> tuple[list[str], list[str]]:
    """Split suite/path targets from pytest options after a literal ``--``."""
    if "--" not in raw_args:
        return raw_args, []
    separator_index = raw_args.index("--")
    return raw_args[:separator_index], raw_args[separator_index + 1 :]


def main(argv: list[str]) -> int:
    raw_targets, pytest_args = split_targets_and_pytest_args(argv[1:])
    try:
        selected = expand_targets(raw_targets)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not selected:
        print("No matching pytest files found.", file=sys.stderr)
        return 2
    cmd = [sys.executable, "-m", "pytest", "-q", *pytest_args, *selected]
    print("Running:", " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
