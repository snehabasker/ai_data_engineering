# AI & Data Engineering

Three small, tested projects covering the stack behind production LLM and data work. Each has its own README with
results and an explicit "limits" section.

| Project | What it is | Highlights |
|---|---|---|
| [analytics-agent](analytics-agent) | Text-to-SQL analytics agent over a governed semantic layer | FastAPI + LangGraph, Qdrant retrieval (hashing or Cohere Embed/Rerank), DuckDB, SQL AST guardrails, tracing, 43-case eval suite with CI gate, DSPy prompt optimisation, MLflow experiment tracking, Dockerfile. [How Claude was used](analytics-agent/docs/AI_WORKFLOW.md) |
| [llm-eval-kit](llm-eval-kit) | Dependency-free LLM evaluation & safety harness | Prompt-injection, hallucination and bias/fairness suites; regression gating; static dashboard; optional MLflow logging and `mlflow.genai.evaluate` scorers. 36 tests |
| [lakehouse-pipeline](lakehouse-pipeline) | Messy data → tested star schema | dbt + DuckDB, quarantine instead of silent drops, Parquet marts, 39 data tests plus oracle tests against the clean source, daily schedule |

## Status — read this first

- **Live-model results are from a local open model (qwen2.5:7b via Ollama), not Claude.** The Claude code paths are
  tested against mocked clients only. analytics-agent: DSPy-optimised planner 82.4% vs heuristic baseline 88.2% on the
  held-out golden set; llm-eval-kit: qwen2.5:7b passes 36% of injection cases. Details and caveats are in each README.
- **Docker and the remote-Qdrant path are written but unbuilt.** **Nothing runs on Databricks**; MLflow runs use a
  local SQLite store (the same code logs to Databricks with `MLFLOW_TRACKING_URI=databricks`, untested).
- Everything else was run locally (Windows, Python 3.11): `analytics-agent` 61 tests, `llm-eval-kit` 36 tests,
  `lakehouse-pipeline` 9 oracle tests + 52 dbt nodes.
- CI workflows live in [.github/workflows](.github/workflows), one per project, triggered by changes under that
  project's folder. They had not run on GitHub when this was written.

Each project was built with Claude Code; the process, including mistakes caught along the way, is documented in
[analytics-agent/docs/AI_WORKFLOW.md](analytics-agent/docs/AI_WORKFLOW.md).
