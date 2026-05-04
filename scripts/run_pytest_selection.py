#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def expand_targets(raw_targets: list[str]) -> list[str]:
    targets = raw_targets or ["tests"]
    collected: list[str] = []
    for target in targets:
        path = Path(target)
        if not path.exists():
            raise FileNotFoundError(f"Pytest target does not exist: {target}")
        if path.is_dir():
            for item in sorted(path.rglob("test_*.py")):
                if item.is_file():
                    collected.append(str(item))
        elif path.suffix == ".py":
            collected.append(str(path))
    seen: set[str] = set()
    result: list[str] = []
    for item in collected:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def main(argv: list[str]) -> int:
    try:
        selected = expand_targets(argv[1:])
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not selected:
        print("No matching pytest files found.", file=sys.stderr)
        return 2
    cmd = [sys.executable, "-m", "pytest", "-q", *selected]
    print("Running:", " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
