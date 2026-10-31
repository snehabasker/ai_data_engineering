"""CLI:  evalkit run --target mock:partial --baseline reports/baseline.json --min-pass injection=1.0
        evalkit dashboard reports/history -o docs/dashboard.html"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .report import build_dashboard, build_report, compare, save_report, to_markdown
from .suites.bias import BiasSuite
from .suites.hallucination import HallucinationSuite
from .suites.injection import InjectionSuite
from .targets import load_target

SUITES = {"injection": InjectionSuite, "hallucination": HallucinationSuite, "bias": BiasSuite}


def cmd_run(a: argparse.Namespace) -> int:
    # Read the baseline first: it is commonly reports/latest.json, which save_report() overwrites below.
    baseline = json.loads(a.baseline.read_text(encoding="utf-8")) if a.baseline else None
    target = load_target(a.target)
    results = []
    for name in a.suites.split(","):
        results += SUITES[name]().run(target)
    report = build_report(target.name, results)
    path = save_report(report, a.out)
    print(to_markdown(report))
    print(f"saved {path}")

    problems = []
    for spec in a.min_pass or []:
        suite, _, v = spec.partition("=")
        got = report["suites"].get(suite, {}).get("pass_rate")
        if got is None or got < float(v):
            problems.append(f"suite '{suite}' pass rate {got} < required {v}")
    if baseline:
        problems += compare(baseline, report, a.max_regression)
    for p in problems:
        print(f"GATE FAILED: {p}", file=sys.stderr)
    return 1 if problems else 0


def cmd_dashboard(a: argparse.Namespace) -> int:
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(build_dashboard(a.history), encoding="utf-8")
    print(f"wrote {a.output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="evalkit")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--target", required=True, help="mock:<profile> | anthropic:<model> | module:function")
    r.add_argument("--suites", default=",".join(SUITES))
    r.add_argument("--out", type=Path, default=Path("reports"))
    r.add_argument("--baseline", type=Path)
    r.add_argument("--max-regression", type=float, default=0.0)
    r.add_argument("--min-pass", action="append", metavar="SUITE=RATE")
    r.set_defaults(fn=cmd_run)
    d = sub.add_parser("dashboard")
    d.add_argument("history", type=Path)
    d.add_argument("-o", "--output", type=Path, default=Path("docs/dashboard.html"))
    d.set_defaults(fn=cmd_dashboard)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
