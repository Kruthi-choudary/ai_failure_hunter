from __future__ import annotations

import json

import streamlit as st

from failure_hunter.models import HuntRequest
from failure_hunter.reporting import regression_test_source, report_json
from failure_hunter.service import run_hunt
from failure_hunter.source import SourceError, discover_functions
from failure_hunter.storage import RunStore


SAMPLE = '''def buggy_sort(values: list[int]) -> list[int]:
    """Return values in ascending order while preserving duplicates."""
    return sorted(set(values))  # bug: duplicates disappear
'''
TYPE_OPTIONS = ["int", "float", "str", "bool", "list[int]", "list[str]"]
ORACLES = {
    "Review only (no executable oracle)": "review",
    "Must not raise": "no_exception",
    "Equals sorted(first argument)": "sorted",
    "Equals sum(first argument)": "sum",
    "Equals first argument": "identity",
    "Returns a non-negative number": "non_negative",
}


st.set_page_config(page_title="AI Failure Hunter", page_icon="⌁", layout="wide")
st.markdown(
    """<style>
    .stApp { color: #e8e9ea; }
    h1 { font-size: 2rem !important; letter-spacing: -0.04em; }
    [data-testid="stMetric"] { border-left: 2px solid #66d9a8; padding-left: 1rem; }
    .status { color:#9da3a8; font-size:.9rem; }
    </style>""",
    unsafe_allow_html=True,
)
st.title("AI Failure Hunter")
st.caption("Find reproducible failures in small Python functions. Evidence first; AI analysis is advisory.")

if "source" not in st.session_state:
    st.session_state.source = SAMPLE

with st.sidebar:
    st.subheader("Run history")
    history = RunStore().list(10)
    if history:
        for item in history:
            st.caption(f"{item['run_id']} · {item['function_name']} · {item['confirmed']} confirmed")
    else:
        st.caption("No saved runs yet.")

uploaded = st.file_uploader("Upload a Python file", type=["py"])
if uploaded and st.button("Load uploaded code"):
    if uploaded.size > 30_000:
        st.error("The initial version accepts source files up to 30 KB.")
    else:
        st.session_state.source = uploaded.getvalue().decode("utf-8")

source = st.text_area("Python source", key="source", height=280)
try:
    discovered = discover_functions(source)
    if not discovered:
        st.warning("Add at least one module-level function.")
        st.stop()
except SourceError as exc:
    st.error(str(exc))
    st.stop()

left, right = st.columns(2)
with left:
    function_name = st.selectbox("Function", [item["name"] for item in discovered])
    selected = next(item for item in discovered if item["name"] == function_name)
    parameter_types = {}
    for parameter in selected["parameters"]:
        annotation = parameter["annotation"]
        default_index = TYPE_OPTIONS.index(annotation) if annotation in TYPE_OPTIONS else 0
        parameter_types[parameter["name"]] = st.selectbox(
            f"Type of {parameter['name']}", TYPE_OPTIONS, index=default_index, key=f"type_{function_name}_{parameter['name']}"
        )
    description = st.text_input("Function description", value="Sort values in ascending order, preserving duplicates.")
    expected_behavior = st.text_area("Expected behavior", value="Output has the same items and multiplicities in sorted order.", height=80)
with right:
    oracle_label = st.selectbox("Executable expectation", list(ORACLES))
    strategy = st.selectbox("Testing strategy", ["boundary", "both", "ai"], format_func=lambda x: {"boundary":"Boundary only", "both":"Boundary + Gemma", "ai":"Gemma (boundary fallback)"}[x])
    num_tests = st.slider("Test budget", 1, 50, 12)
    timeout = st.slider("Per-test timeout (seconds)", 0.1, 3.0, 1.0, 0.1)
    st.info("Only the selected function snippet and description are sent to Google when Gemma is enabled.")

if st.button("Run tests", type="primary", use_container_width=True):
    try:
        request = HuntRequest(
            source=source,
            function_name=function_name,
            parameter_types=parameter_types,
            description=description,
            expected_behavior=expected_behavior,
            oracle=ORACLES[oracle_label],
            strategy=strategy,
            num_tests=num_tests,
            timeout_seconds=timeout,
        )
        with st.spinner("Executing isolated test cases…"):
            report = run_hunt(request)
            RunStore().save(request, report)
        st.session_state.last_request = request
        st.session_state.last_report = report
    except Exception as exc:
        st.error(str(exc))

if "last_report" in st.session_state:
    report = st.session_state.last_report
    request = st.session_state.last_request
    confirmed = sum(f.verification_status == "confirmed" for f in report.failures)
    suspected = sum(f.verification_status == "suspected" for f in report.failures)
    timeouts = sum(row["status"] == "timeout" for row in report.results)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Executed", report.tests_executed)
    c2.metric("Confirmed", confirmed)
    c3.metric("Suspected", suspected)
    c4.metric("Timeouts", timeouts)
    st.caption(f"AI status: {report.ai_status} · Run {report.run_id} · {report.duration_ms:.0f} ms")

    st.subheader("Failures")
    if not report.failures:
        st.success("No failures were found under the selected expectation and test budget.")
    for failure in report.failures:
        with st.expander(f"{failure.failure_id} · {failure.verification_status.upper()} · {failure.classification}"):
            st.write("Original input", failure.original_input)
            st.write("Minimized input", failure.minimized_input or "No smaller reproducer found")
            st.write("Expected", failure.expected)
            st.write("Actual", failure.actual)
            st.write("Reproduce", failure.reproduction_steps)
            st.write("Gemma analysis", failure.explanation or "Not available for this run.")
            if failure.suggested_fix:
                st.code(failure.suggested_fix, language="python")

    st.subheader("Execution log")
    st.dataframe(report.results, use_container_width=True)
    d1, d2 = st.columns(2)
    d1.download_button("Download JSON report", report_json(report), f"failure-hunter-{report.run_id}.json", "application/json", use_container_width=True)
    d2.download_button("Download regression test", regression_test_source(request, report), f"test_regression_{report.run_id}.py", "text/x-python", use_container_width=True)

