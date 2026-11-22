"""Fixtures shared by data-layer tests."""

from __future__ import annotations

import pytest
from fakes import FakeClock, FakeTrackRepository, InMemorySeedRepository


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def seed_repository() -> InMemorySeedRepository:
    return InMemorySeedRepository()


@pytest.fixture
def track_repository() -> FakeTrackRepository:
    return FakeTrackRepository()
