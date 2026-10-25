# AI Failure Hunter

AI Failure Hunter is a small, evidence-first tool for finding edge-case failures in Python functions. It generates deterministic boundary inputs, optionally asks hosted Gemma for additional typed inputs, executes every case in a separate process, minimizes reproducible failures, and exports regression tests.

The included sample finds a real seeded bug: a sorting function uses `set()` and silently drops duplicate values.

## Quick start

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Export the key in your shell (the app deliberately does not load or persist secrets itself):

```bash
export GEMINI_API_KEY="your-key-from-Google-AI-Studio"
streamlit run streamlit_app.py
```

The app remains useful without a key: select **Boundary only**, or select an AI strategy and read the clear fallback status. To run the optional API:

```bash
uvicorn failure_hunter.api:app --reload
```

Run tests and the benchmark:

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
PYTHONPATH=. python benchmark/run_benchmark.py
```

`pytest` can also run the same test files after dependencies are installed.

## Workflow

1. Paste or upload a small Python file and select a module-level function.
2. Confirm each parameter's supported JSON type.
3. Choose a test strategy and an executable expectation (oracle).
4. Run the tests and inspect actual outputs, exceptions, timeouts, and evidence.
5. Download the JSON report or a Python regression test.

Supported parameter types are `int`, `float`, `str`, `bool`, `list[int]`, and `list[str]`. The deliberately small oracle set covers sorting, summing, identity, non-negative results, and “must not raise.” Free-text expected behavior gives Gemma context but is never treated as a reliable oracle.

If no executable oracle is selected, an exception is labeled **suspected**, not confirmed. A model guess never confirms a failure.

## Gemma integration

The integration follows Google's current hosted Gemma guidance:

- SDK: [`google-genai`](https://ai.google.dev/gemini-api/docs/libraries)
- Authentication: a Google AI Studio API key in `GEMINI_API_KEY`
- Default model: [`gemma-4-26b-a4b-it`](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api)
- Request: `client.models.generate_content(model=..., contents=...)`

Google's current structured-output support table does not list Gemma. Consequently this project does **not** assume Gemini-only constrained decoding is available: it asks Gemma for one plain JSON object, parses it with Pydantic, checks exact parameter names and types, enforces length/range limits, and discards invalid candidates before execution. Gemma sees only the selected function snippet (maximum 6 KB), its signature, and the developer's description—not the complete source file.

Gemma generates candidate inputs and hypotheses, then explains up to five observed failures and may suggest a fix. These explanations are displayed as advisory model analysis. Suggested code is never executed automatically. Missing keys, unavailable SDK/model, malformed output, network failures, and rate limits produce a visible status while deterministic tests continue.

## Architecture

```text
Streamlit / FastAPI
        │
        ▼
service.py ── boundaries.py
    │        ├─ gemma.py (hosted input generation + analysis)
    │        └─ minimizer.py
    ▼
runner.py ── subprocess ── worker.py ── submitted function
    │
    ├─ reporting.py (JSON + regression test)
    └─ storage.py (local runs/*.json)
```

The main app never calls `eval` or `exec`. The worker uses `exec` only inside a fresh subprocess, with a wall-clock timeout, CPU/file limits, bounded JSON inputs, and bounded captured output. Each test gets a fresh worker, so state is not shared between cases.

## Safety limitations

A subprocess with resource limits is **not a complete security sandbox**. Submitted code can still access resources available to the local user, and macOS does not provide the same address-space limit used on Linux. Use this only with code you reasonably trust. Do not expose this execution endpoint to arbitrary public submissions without a stronger isolation boundary such as a locked-down VM or sandbox service.

Other intentional limits:

- module-level synchronous functions only;
- JSON-like scalar/list inputs only;
- no arbitrary property expressions or automatic execution of model-written code;
- no authentication, accounts, Docker, cloud storage, or background job system;
- local JSON history instead of SQLite;
- Hypothesis is retained as a lightweight declared dependency for a future approved-property mode, but this minimal build uses one clear boundary/AI workflow rather than exposing another partially implemented strategy.

## Benchmark

The benchmark uses the same 8-test budget on two seeded-bug targets and one correct control. It counts a discovery only when an explicit executable oracle is violated. Run it again on your machine to refresh [`benchmark/results/latest.json`](benchmark/results/latest.json).

Actual result measured on 2026-10-25 in this environment:

| Strategy | Seeded bugs found | Confirmed failures | Tests | False-positive rate | Minimization success |
|---|---:|---:|---:|---:|---:|
| Boundary | 2 / 2 | 5 | 23 | 0% | 60% |
| Gemma | Not measured | — | — | — | — |

The latest boundary run took 8.56 seconds wall-clock. The Gemma comparison was not measured because `GEMINI_API_KEY` was not configured; the result file says so explicitly. It would be misleading to count deterministic fallback cases as AI-generated results. With a key configured, the same benchmark script records the exact model identifier, AI status, per-target duration, test index of the first failure, and AI results under the same budget.

## Verification record

Verified locally on 2026-10-25 with Python 3.13.3:

- all 14 pytest tests passed in 19.57 seconds;
- `pip check` reported no broken requirements; FastAPI 0.162.0, google-genai 1.75.0, Hypothesis 6.170.9, pytest 8.4.2, Streamlit 1.66.1, and Uvicorn 0.54.0 are installed;
- every Python module, the Streamlit entry point, tests, and benchmark compiled successfully;
- FastAPI completed application startup, but this restricted environment prohibited both TCP and Unix-domain socket binding;
- FastAPI was therefore exercised through its in-process HTTP test client: `/health`, `/functions`, `/runs` POST, and `/runs` GET all returned HTTP 200; the run executed 8 cases, found 2 confirmed failures, and appeared in history;
- the no-key AI path displayed the missing-credential message, executed 8 deterministic fallback cases, and found 2 confirmed failures;
- the benchmark found both seeded bugs and no failure in the correct control;
- `GEMINI_API_KEY` was not configured, so no live Gemma response was requested or claimed;
- Streamlit imports successfully, but this restricted verification environment prohibits socket binding, so browser-level launch verification remains external.

On a machine with PyPI access, use the Quick start commands above, then verify the two servers with:

```bash
curl http://127.0.0.1:8000/health
streamlit run streamlit_app.py
```

The earlier dependency download timeout was resolved by retrying with a longer pip timeout. The existing dependency declarations were left unchanged.

## Project status

The minimal definition of done is implemented: paste/upload a supported function, execute real tests, find the included seeded bug, distinguish confirmed from suspected issues, inspect/minimize the reproducer, request Gemma analysis when configured, persist the run, and export a regression test. Larger property languages, public multi-tenant execution, and elaborate dashboards are intentionally out of scope.
