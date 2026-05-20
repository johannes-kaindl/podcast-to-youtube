"""Shared pytest fixtures."""
import json
from pathlib import Path
import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def stdout_snippet(fixtures_dir: Path):
    def _read(name: str) -> list[str]:
        path = fixtures_dir / "stdout-snippets" / f"{name}.txt"
        return [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    return _read
