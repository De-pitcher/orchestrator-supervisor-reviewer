"""T27 corrected S4 runner (builder-side tool, lives under ignored .ai/).

One process:
  1. makes the repository root and the tests directory explicitly importable;
  2. invokes OsrTests.benchmark_report() exactly once and retains the ACTUAL
     returned report as JSON with its SHA-256;
  3. runs the 10 selected S4 unittest IDs in the same process so the three
     benchmark consumers reuse the same cache key.

No report is reconstructed, and no standalone benchmark is run after S4.
"""

import hashlib
import json
import os
import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"
EVIDENCE = Path(os.environ.get(
    "T27_EVIDENCE_DIR",
    str(REPO / ".ai" / "reviews" / "T27.final-evidence.corrected"),
))

S4_IDS = [
    "test_osr.OsrTests.test_seams_plan_check_warning_when_seams_table_missing",
    "test_osr.OsrTests.test_spec_triage_blocks_until_human_unblocks",
    "test_osr.OsrTests.test_task_check_enforces_seam_authoritative_source_in_context_files",
    "test_osr.OsrTests.test_unanchored_mock_heuristic_flags_mock_without_fixture_and_waiver_resolves",
    "test_osr.OsrTests.test_unconfirmed_commands_block_approval",
    "test_osr.OsrTests.test_verify_command_must_be_confirmed",
    "test_osr.OsrTests.test_waiver_rules",
    "test_osr.OsrTests.test_adversarial_eval_suite_benchmarks_catch_rate",
    "test_osr.OsrTests.test_phase6_benchmark_and_honest_reporting",
    "test_osr.OsrTests.test_phase6_version_and_docs_integrity",
]


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.chdir(str(REPO))
    # Repository root first for scripts.* and evals.*; tests directory so the
    # unittest names resolve to this very module object (same class cache).
    sys.path.insert(0, str(TESTS))
    sys.path.insert(0, str(REPO))

    import evals.eval_suite as eval_suite
    import test_osr

    calls = {"count": 0}
    original = eval_suite.run_adversarial_benchmark

    def counting_runner(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    eval_suite.run_adversarial_benchmark = counting_runner

    started = time.time()
    report = test_osr.OsrTests.benchmark_report()
    report_bytes = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report_path = EVIDENCE / "S4.benchmark-report.json"
    report_path.write_bytes(report_bytes)

    cache = test_osr.OsrTests._benchmark_cache
    runner_meta = {
        "schema": "osr.t27.s4-runner.v1",
        "runner_file": ".ai/t27_s4_runner.py",
        "runner_argv": [sys.executable, ".ai/t27_s4_runner.py"],
        "working_directory": os.getcwd(),
        "import_paths": [str(REPO), str(TESTS)],
        "sys_path_head": [p for p in sys.path[:4]],
        "python_executable": sys.executable,
        "python_version": sys.version,
        "benchmark_report_file": (EVIDENCE / "S4.benchmark-report.json").relative_to(REPO).as_posix(),
        "benchmark_report_sha256": sha_bytes(report_bytes),
        "benchmark_report_invocations": calls["count"],
        "cache_key": None,
        "cache_keys_after": [repr(k) for k in cache.keys()],
        "cache_entry_is_returned_report": cache.get(None) is report,
        "selected_ids": list(S4_IDS),
        "report_summary": {
            "version": report.get("version"),
            "total_cheats_tested": report.get("total_cheats_tested"),
            "cheats_caught": report.get("cheats_caught"),
            "catch_rate": report.get("catch_rate"),
            "clean_runs_tested": report.get("clean_runs_tested"),
            "false_positives": report.get("false_positives"),
            "false_positive_rate": report.get("false_positive_rate"),
            "known_misses": [v.get("id") for v in report.get("known_misses", [])],
            "caught_ids": sorted(v.get("id") for v in report.get("caught_vectors", [])),
            "vector_status": {v.get("id"): v.get("status") for v in report.get("vectors", [])},
        },
    }
    meta_path = EVIDENCE / "S4.runner.json"
    meta_path.write_text(json.dumps(runner_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    suite = unittest.TestLoader().loadTestsFromNames(S4_IDS)
    print("S4 runner argv: %r" % (runner_meta["runner_argv"],))
    print("S4 working directory: %s" % runner_meta["working_directory"])
    print("S4 import paths: %r" % (runner_meta["import_paths"],))
    print("S4 benchmark report: %s sha256=%s invocations=%d" % (
        runner_meta["benchmark_report_file"], runner_meta["benchmark_report_sha256"], calls["count"]))
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    elapsed = round(time.time() - started, 3)

    runner_meta["tests_run"] = result.testsRun
    runner_meta["test_failures"] = len(result.failures)
    runner_meta["test_errors"] = len(result.errors)
    runner_meta["ok"] = result.wasSuccessful() and calls["count"] == 1 and cache.get(None) is report
    runner_meta["elapsed_seconds"] = elapsed
    meta_path.write_text(json.dumps(runner_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.exit(0 if runner_meta["ok"] else 1)


if __name__ == "__main__":
    main()
