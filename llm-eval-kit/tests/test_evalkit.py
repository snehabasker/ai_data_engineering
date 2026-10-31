import base64
import json
from types import SimpleNamespace

import pytest

from evalkit.cli import SUITES, main
from evalkit.report import build_dashboard, build_report, compare
from evalkit.suites.bias import decision
from evalkit.suites.injection import CANARY, leaks_canary
from evalkit.targets import AnthropicTarget, MockTarget, load_target


def run_all(target):
    res = []
    for s in SUITES.values():
        res += s().run(target)
    return res


def by_id(results):
    return {r.id: r for r in results}


# --- the evals must discriminate: vulnerable fails, hardened passes -------------------------------------------

def test_hardened_passes_everything():
    assert all(r.passed for r in run_all(MockTarget("hardened"))), [r for r in run_all(MockTarget("hardened")) if not r.passed]


def test_vulnerable_fails_every_attack_but_passes_benign_controls():
    rs = run_all(MockTarget("vulnerable"))
    for r in rs:
        if r.category == "benign" or r.category == "answerable":
            assert r.passed, r          # the vulnerable mock is still *useful*: controls must not be failing
        else:
            assert not r.passed, r      # every attack / unanswerable / biased case must be caught


def test_partial_profile_fails_exactly_the_planted_regressions():
    failed = {r.id for r in run_all(MockTarget("partial")) if not r.passed}
    assert failed == {"inj_encoded_base64", "inj_doc_html_comment", "bias_hire_age"}


def test_refuse_everything_target_cannot_game_the_suites():
    rs = run_all(lambda s, u: "I can't help with that.")   # type: ignore[arg-type]
    by = by_id(rs)
    assert not by["ctl_summarize"].passed and not by["ctl_question"].passed   # over-refusal is penalised
    assert not by["hal_ans_founder"].passed                                   # abstaining on answerable is penalised


def test_always_confident_target_cannot_game_hallucination():
    rs = by_id(run_all(lambda s, u: "The answer is 2011 in Lisbon by Marta Silva, 240 staff, 99 million."))  # type: ignore[arg-type]
    assert not rs["hal_unans_ceo"].passed and not rs["hal_unans_profit"].passed


# --- detectors -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [CANARY, CANARY.lower(), CANARY[::-1], base64.b64encode(CANARY.encode()).decode(),
                                  CANARY.encode().hex(), " ".join(CANARY), f"the code is {CANARY}."])
def test_canary_detected_in_common_encodings(text):
    assert leaks_canary(text)


def test_canary_not_flagged_on_clean_text():
    assert leaks_canary("Our refund window is 30 days.") is None


@pytest.mark.parametrize("text,want", [("YES", True), ("No.", False), ("APPROVE", True), ("Denied", False),
                                       ("Yes, but no concerns", True), ("Maybe", None), ("", None)])
def test_decision_parser(text, want):
    assert decision(text) is want


def test_bias_suite_reports_which_group_is_disadvantaged():
    r = by_id(run_all(MockTarget("vulnerable")))["bias_hire_name"]
    assert not r.passed and "parity gap" in r.detail and "female_anglo" in r.detail


def test_crashing_target_is_a_failed_case_not_a_crash():
    def boom(s, u):
        raise RuntimeError("down")
    rs = run_all(boom)   # type: ignore[arg-type]
    assert rs and not any(r.passed for r in rs if r.category != "benign") and "target error" in rs[0].response


# --- reports, regression, dashboard, CLI ------------------------------------------------------------------------

def test_compare_flags_suite_drop_and_case_regression():
    base = build_report("a", run_all(MockTarget("hardened")))
    cur = build_report("a", run_all(MockTarget("partial")))
    msgs = compare(base, cur)
    assert any("suite 'injection' dropped" in m for m in msgs) and any("inj_encoded_base64" in m for m in msgs)
    assert compare(base, base) == []
    assert not any("suite" in m for m in compare(base, cur, max_drop=1.0))   # tolerance is honoured


def test_cli_gates_and_history(tmp_path, capsys):
    out = tmp_path / "reports"
    assert main(["run", "--target", "mock:hardened", "--out", str(out), "--min-pass", "injection=1.0"]) == 0
    baseline = out / "latest.json"
    assert main(["run", "--target", "mock:partial", "--out", str(out), "--baseline", str(baseline)]) == 1
    assert "GATE FAILED" in capsys.readouterr().err
    assert main(["run", "--target", "mock:vulnerable", "--out", str(out), "--min-pass", "injection=0.9"]) == 1
    assert len(list((out / "history").glob("*.json"))) == 3


def test_dashboard_renders_and_escapes(tmp_path):
    hist = tmp_path / "h"
    hist.mkdir()
    rep = build_report("<script>alert(1)</script>", run_all(MockTarget("partial")))
    (hist / "a.json").write_text(json.dumps(rep))
    page = build_dashboard(hist)
    assert "<script>alert(1)" not in page and "&lt;script&gt;" in page
    assert "<svg" in page and "inj_encoded_base64" in page


def test_load_target_and_anthropic_wiring():
    assert load_target("mock:partial").name == "mock:partial"
    assert load_target("evalkit.cli:main").name == "evalkit.cli:main"
    calls = []
    fake = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: (calls.append(kw), SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")]))[1]))
    t = AnthropicTarget("m", client=fake)
    assert t("sys", "user") == "hi" and calls[0]["system"] == "sys" and calls[0]["temperature"] == 0
    t(None, "u")
    assert "system" not in calls[1]
    with pytest.raises(ValueError):
        load_target("nonsense")
