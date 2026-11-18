import os
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from hypothesis import settings

from wayback_machine_archiver import clients, workflow

settings.register_profile("ci", max_examples=100)
settings.register_profile("long", max_examples=20_000, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))


@dataclass
class VirtualClock:
    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def virtual_clock(monkeypatch: pytest.MonkeyPatch) -> VirtualClock:
    clock = VirtualClock()
    virtual_time = SimpleNamespace(time=clock.time, sleep=clock.sleep)
    monkeypatch.setattr(workflow, "time", virtual_time)
    monkeypatch.setattr(clients, "time", virtual_time)
    return clock
