"""MLflow integration: the MLflow scorers must give exactly the verdicts of the native runner (no drift between the
two paths), and logged metrics must equal the report. Skipped when mlflow is not installed (core stays dep-free)."""
import io
import json

import pytest

mlflow = pytest.importorskip("mlflow")

from evalkit.core import run_pattern_cases  # noqa: E402
from evalkit.report import build_report  # noqa: E402
from evalkit.suites.hallucination import HallucinationSuite  # noqa: E402
from evalkit.suites.injection import InjectionSuite  # noqa: E402
from evalkit.targets import MockTarget, OllamaTarget, load_target  # noqa: E402


@pytest.fixture(autouse=True)
def _tracking(tmp_path, monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("profile", ["vulnerable", "partial", "hardened"])
@pytest.mark.parametrize("suite_cls", [InjectionSuite, HallucinationSuite])
def test_rule_scorer_matches_native_runner(profile, suite_cls):
    from evalkit.mlflow_integration import make_rule_scorer
    target, suite = MockTarget(profile), suite_cls()
    cases = suite.cases()
    native = {r.id: r.passed for r in run_pattern_cases(suite.name, cases, target)}
    rule = make_rule_scorer(suite.name, cases)
    for c in cases:
        fb = rule(outputs=target(c.system, c.user), expectations={"case_id": c.id})
        assert fb.value == native[c.id], c.id


def test_rule_scorer_fails_target_errors():
    from evalkit.mlflow_integration import make_rule_scorer
    cases = InjectionSuite().cases()
    rule = make_rule_scorer("injection", cases)
    fb = rule(outputs="[target error: RuntimeError: boom]", expectations={"case_id": cases[0].id})
    assert fb.value is False and "target error" in fb.rationale


def test_genai_evaluate_end_to_end_partial():
    from evalkit.mlflow_integration import genai_evaluate
    m = genai_evaluate(MockTarget("partial"), {"injection": InjectionSuite(), "hallucination": HallucinationSuite()})
    assert m["injection"]["injection_rule/mean"] == pytest.approx(12 / 14)
    assert m["hallucination"]["hallucination_rule/mean"] == 1.0


def test_log_report_metrics_equal_report():
    from evalkit.mlflow_integration import log_report, report_metrics
    target = MockTarget("partial")
    report = build_report(target.name, InjectionSuite().run(target))
    run_id = log_report(report)
    logged = mlflow.get_run(run_id).data.metrics
    assert logged == pytest.approx(report_metrics(report))
    assert logged["injection_pass_rate"] == pytest.approx(12 / 14, abs=1e-4)  # report rounds to 4 dp


def test_ollama_target_request_shape(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"], seen["body"] = req.full_url, json.loads(req.data)
        return io.BytesIO(json.dumps({"message": {"content": "hi"}}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    t = load_target("ollama:qwen2.5:7b")
    assert isinstance(t, OllamaTarget) and t.name == "ollama:qwen2.5:7b"
    assert t("sys", "hello") == "hi"
    assert seen["url"].endswith("/api/chat")
    assert seen["body"]["model"] == "qwen2.5:7b" and seen["body"]["options"]["temperature"] == 0
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]
