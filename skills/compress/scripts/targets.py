#!/usr/bin/env python3
"""Target parsing and expansion for caveman-compress."""

from __future__ import annotations

import ast
import glob
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TargetResolution:
    files: list[Path]
    unmatched: list[str]


def _split_raw_target(raw: str) -> list[str]:
    stripped = raw.strip()
    if not stripped:
        return []

    if stripped[0] in "[(" and stripped[-1] in "])":
        try:
            parsed = ast.literal_eval(stripped)
        except (SyntaxError, ValueError):
            parsed = None
        if isinstance(parsed, (list, tuple, set)):
            return [str(item).strip() for item in parsed if str(item).strip()]

    parts = [piece.strip() for piece in re.split(r"[\n,]+", stripped) if piece.strip()]
    return parts or [stripped]


def _expand_target(target: str, cwd: Path) -> list[Path]:
    expanded_target = Path(target).expanduser()

    if glob.has_magic(str(expanded_target)):
        pattern = str(expanded_target)
        if not expanded_target.is_absolute():
            pattern = str((cwd / expanded_target).resolve())
        matches = [Path(match) for match in glob.glob(pattern, recursive=True)]
        return sorted(path for path in matches if path.is_file())

    candidate = expanded_target
    if not candidate.is_absolute():
        candidate = cwd / candidate
    return [candidate] if candidate.exists() and candidate.is_file() else []


def resolve_targets(raw_targets: list[str], *, cwd: Path | None = None) -> TargetResolution:
    base_dir = (cwd or Path.cwd()).resolve()
    files: list[Path] = []
    unmatched: list[str] = []
    seen: set[Path] = set()

    for raw_target in raw_targets:
        for target in _split_raw_target(raw_target):
            matches = _expand_target(target, base_dir)
            if not matches:
                unmatched.append(target)
                continue
            for match in matches:
                resolved = match.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(resolved)

    return TargetResolution(files=files, unmatched=unmatched)
