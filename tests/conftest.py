"""Shared pytest fixtures for the podcast cutter test suite."""
from __future__ import annotations

from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="run tests marked @pytest.mark.integration (hits real services)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--integration"):
        return
    skip = pytest.mark.skip(reason="needs --integration to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def repo_root() -> Path:
    """Absolute path to the repo root, regardless of cwd."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def fixtures_dir(repo_root: Path) -> Path:
    return repo_root / "shared" / "test_fixtures"
