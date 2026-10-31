"""Core types. A *target* is anything that maps (system, user) -> text; a *suite* turns a target into results."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol


TARGET_ERROR = "[target error"


class Target(Protocol):
    name: str

    def __call__(self, system: str | None, user: str) -> str: ...


@dataclass
class CaseResult:
    id: str
    suite: str
    category: str
    passed: bool
    detail: str
    response: str = ""
    latency_ms: float = 0.0


class Suite(Protocol):
    name: str

    def run(self, target: Target) -> list[CaseResult]: ...


def timed_call(target: Target, system: str | None, user: str) -> tuple[str, float]:
    t0 = time.perf_counter()
    try:
        out = target(system, user)
    except Exception as e:  # a crashing target is a failed case, not a crashed run
        out = f"{TARGET_ERROR}: {type(e).__name__}: {e}]"
    return out, (time.perf_counter() - t0) * 1000


@dataclass
class PatternCase:
    """Declarative case: response must match `must_match` (if set) and must not match `must_not_match`."""
    id: str
    category: str
    user: str
    system: str | None = None
    must_match: str | None = None
    must_not_match: str | None = None
    check_fns: list[Callable[[str], str | None]] = field(default_factory=list)  # return an error string or None

    def evaluate(self, response: str) -> tuple[bool, str]:
        if self.must_match and not re.search(self.must_match, response, re.I | re.S):
            return False, f"expected /{self.must_match}/"
        if self.must_not_match and re.search(self.must_not_match, response, re.I | re.S):
            return False, f"forbidden /{self.must_not_match}/ present"
        for fn in self.check_fns:
            if (err := fn(response)) is not None:
                return False, err
        return True, "ok"


def run_pattern_cases(suite: str, cases: list[PatternCase], target: Target) -> list[CaseResult]:
    out = []
    for c in cases:
        resp, ms = timed_call(target, c.system, c.user)
        # An absence of leaked text proves nothing when the target never answered: errors always fail.
        ok, detail = (False, "target error") if resp.startswith(TARGET_ERROR) else c.evaluate(resp)
        out.append(CaseResult(c.id, suite, c.category, ok, detail, resp[:300], round(ms, 1)))
    return out
