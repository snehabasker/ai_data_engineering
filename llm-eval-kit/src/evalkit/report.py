"""Reports: build, persist, compare against a baseline, render markdown and a static HTML dashboard."""
from __future__ import annotations

import datetime as dt
import html
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .core import CaseResult


def build_report(target: str, results: list[CaseResult]) -> dict[str, Any]:
    suites: dict[str, Any] = {}
    for r in results:
        s = suites.setdefault(r.suite, {"n": 0, "passed": 0, "categories": {}})
        s["n"] += 1
        s["passed"] += r.passed
        c = s["categories"].setdefault(r.category, {"n": 0, "passed": 0})
        c["n"] += 1
        c["passed"] += r.passed
    for s in suites.values():
        s["pass_rate"] = round(s["passed"] / s["n"], 4)
        for c in s["categories"].values():
            c["pass_rate"] = round(c["passed"] / c["n"], 4)
    total, passed = len(results), sum(r.passed for r in results)
    return {"schema": 1, "target": target, "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "overall": {"n": total, "passed": passed, "pass_rate": round(passed / total, 4) if total else 0.0},
            "suites": suites, "cases": [asdict(r) for r in results]}


def save_report(report: dict[str, Any], out: Path) -> Path:
    hist = out / "history"
    hist.mkdir(parents=True, exist_ok=True)
    stamp = report["timestamp"].replace(":", "").replace("-", "")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", report["target"])
    path = hist / f"{stamp}_{safe}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def compare(baseline: dict[str, Any], current: dict[str, Any], max_drop: float = 0.0) -> list[str]:
    """Regressions: suite pass-rate drops beyond `max_drop`, and any individual case that passed before and fails now."""
    out = []
    for name, cur in current["suites"].items():
        base = baseline["suites"].get(name)
        if base and base["pass_rate"] - cur["pass_rate"] > max_drop + 1e-9:
            out.append(f"suite '{name}' dropped {base['pass_rate']:.0%} -> {cur['pass_rate']:.0%}")
    was = {c["id"]: c["passed"] for c in baseline["cases"]}
    out += [f"case '{c['id']}' regressed (passed in baseline)" for c in current["cases"] if was.get(c["id"]) and not c["passed"]]
    return out


def to_markdown(report: dict[str, Any]) -> str:
    L = [f"# Eval report — {report['target']}", "", f"Overall: **{report['overall']['pass_rate']:.0%}** "
         f"({report['overall']['passed']}/{report['overall']['n']})", "", "| Suite | Pass rate | Categories |", "|---|---|---|"]
    for name, s in report["suites"].items():
        cats = ", ".join(f"{k} {v['passed']}/{v['n']}" for k, v in s["categories"].items())
        L.append(f"| {name} | {s['pass_rate']:.0%} ({s['passed']}/{s['n']}) | {cats} |")
    fails = [c for c in report["cases"] if not c["passed"]]
    L += ["", f"## Failures ({len(fails)})", ""]
    L += [f"- `{c['id']}` [{c['suite']}/{c['category']}] — {c['detail']}" for c in fails] or ["None."]
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------------------------- dashboard

_CSS = """
:root{--bg:#fff;--fg:#1a1d21;--muted:#5f6b7a;--line:#d9dee5;--card:#f6f8fa;--good:#1a7f4b;--bad:#c62f3b;--s1:#2563eb;--s2:#c2410c;--s3:#7c3aed}
@media (prefers-color-scheme:dark){:root{--bg:#0f1419;--fg:#e6e9ee;--muted:#98a2b3;--line:#2a323d;--card:#171d25;--good:#3fb27f;--bad:#f0616d;--s1:#6ea0ff;--s2:#f59a5b;--s3:#b79cff}}
*{box-sizing:border-box}body{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:960px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}p.sub{color:var(--muted);margin:0 0 16px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}
.card b{display:block;font-size:24px}.card span{color:var(--muted);font-size:13px}table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}.bad{color:var(--bad)}.good{color:var(--good)}
svg{width:100%;height:auto;background:var(--card);border:1px solid var(--line);border-radius:8px}.legend span{margin-right:14px;font-size:13px}
"""
_COLORS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--good)"]


def _trend_svg(runs: list[dict[str, Any]], suites: list[str]) -> str:
    W, H, pad = 640, 220, 34
    n = max(len(runs), 1)
    x = lambda i: pad + (W - 2 * pad) * (i / (n - 1) if n > 1 else 0.5)  # noqa: E731
    y = lambda v: H - pad - (H - 2 * pad) * v  # noqa: E731
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Pass rate per suite across runs">']
    for g in (0, 0.5, 1):
        parts.append(f'<line x1="{pad}" x2="{W - pad}" y1="{y(g)}" y2="{y(g)}" stroke="var(--line)"/>'
                     f'<text x="4" y="{y(g) + 4}" font-size="11" fill="var(--muted)">{int(g * 100)}%</text>')
    for k, s in enumerate(suites):
        pts = [(x(i), y(r["suites"][s]["pass_rate"])) for i, r in enumerate(runs) if s in r["suites"]]
        col = _COLORS[k % len(_COLORS)]
        if len(pts) > 1:
            parts.append(f'<polyline fill="none" stroke="{col}" stroke-width="2" points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}"/>')
        parts += [f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.5" fill="{col}"/>' for a, b in pts]
    parts.append("</svg>")
    return "".join(parts)


def build_dashboard(history_dir: Path) -> str:
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(history_dir.glob("*.json"))]
    runs.sort(key=lambda r: r["timestamp"])
    if not runs:
        return "<!doctype html><title>No runs</title><p>No reports found.</p>"
    latest = runs[-1]
    suites = sorted({s for r in runs for s in r["suites"]})
    e = html.escape
    cards = "".join(f'<div class="card"><b class="{"good" if s["pass_rate"] == 1 else "bad"}">{s["pass_rate"]:.0%}</b><span>{e(n)} ({s["passed"]}/{s["n"]})</span></div>'
                    for n, s in latest["suites"].items())
    legend = "".join(f'<span style="color:{_COLORS[i % len(_COLORS)]}">&#9632; {e(s)}</span>' for i, s in enumerate(suites))
    rows = "".join(f'<tr><td>{e(r["timestamp"])}</td><td>{e(r["target"])}</td>' +
                   "".join(f'<td>{r["suites"][s]["pass_rate"]:.0%}</td>' if s in r["suites"] else "<td>–</td>" for s in suites) + "</tr>" for r in reversed(runs))
    fails = "".join(f'<tr><td>{e(c["id"])}</td><td>{e(c["suite"])}/{e(c["category"])}</td><td>{e(c["detail"])}</td></tr>' for c in latest["cases"] if not c["passed"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Eval Dashboard</title><style>{_CSS}</style></head><body><main>
<h1>Eval regression dashboard</h1><p class="sub">Latest run: {e(latest["target"])} · {e(latest["timestamp"])} · {len(runs)} run(s) in history</p>
<div class="cards">{cards}</div>
<h2>Pass rate over runs</h2><div class="legend">{legend}</div>{_trend_svg(runs, suites)}
<h2>Failures in latest run ({sum(1 for c in latest["cases"] if not c["passed"])})</h2>
<table><tr><th>Case</th><th>Suite</th><th>Detail</th></tr>{fails or '<tr><td colspan="3">None</td></tr>'}</table>
<h2>History</h2><table><tr><th>Time</th><th>Target</th>{"".join(f"<th>{e(s)}</th>" for s in suites)}</tr>{rows}</table>
</main></body></html>"""
