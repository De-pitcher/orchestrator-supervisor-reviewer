import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import scripts.osr as osr


def _sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _raw_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _py(code):
    """Build a shell command that runs `code` with this interpreter."""
    return '"%s" -c "%s"' % (sys.executable, code)


class _TempRootCase(unittest.TestCase):
    """Runs every test against a throwaway project root."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_root = osr.ROOT
        self.old_json = osr.JSON_MODE
        osr.ROOT = Path(self.tmpdir.name)
        osr.JSON_MODE = True

    def tearDown(self):
        osr.JSON_MODE = self.old_json
        osr.ROOT = self.old_root
        self.tmpdir.cleanup()

    def log_path(self, name):
        return osr.ai("logs") / name


class TestRunLogsCleanControl(unittest.TestCase):
    """Clean control fixture for T22 (R20): retained log digest.

    Verifies that saving a command log retains the exact written bytes
    and produces a digest matching the expected SHA-256 in standard text mode.
    """

    def test_clean_control_retained_log_digest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_root = osr.ROOT
            try:
                osr.ROOT = Path(tmpdir)
                label = "clean_control_run"
                sample_output = "Line 1: command started\nLine 2: completed successfully\n"
                expected_sha = hashlib.sha256(sample_output.encode("utf-8")).hexdigest()

                log_name = osr.save_log(1, label, sample_output)
                log_file = osr.ai("logs") / log_name

                self.assertTrue(log_file.exists(), f"Log file {log_file} must exist")
                content = log_file.read_text(encoding="utf-8")
                self.assertEqual(content, sample_output)
                actual_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
                self.assertEqual(actual_sha, expected_sha)
            finally:
                osr.ROOT = old_root


class TestRunLogsImmutability(_TempRootCase):
    """R20: same-label writes, frozen clocks, concurrency and collisions.

    Each executed command must own one immutable log file. A second write with
    the same label at the same clock reading must not destroy the first one.
    """

    def test_frozen_clock_same_label_writes_keep_both_outputs(self):
        payload1 = "first execution output: attempt 1\n"
        payload2 = "second execution output: attempt 2\n"

        with mock.patch("time.strftime", return_value="20261023-120000"):
            log1 = osr.save_log(0, "task_run", payload1)
            log2 = osr.save_log(0, "task_run", payload2)

        self.assertNotEqual(log1, log2, "Frozen clock must not collapse two runs onto one log name")
        path1, path2 = self.log_path(log1), self.log_path(log2)
        self.assertTrue(path1.exists(), "First log must still exist")
        self.assertTrue(path2.exists(), "Second log must exist")
        self.assertEqual(path1.read_bytes(), payload1.encode("utf-8"))
        self.assertEqual(path2.read_bytes(), payload2.encode("utf-8"))

    def test_same_label_rapid_writes_keep_both_outputs(self):
        payload1 = "rapid write one\n"
        payload2 = "rapid write two\n"

        log1 = osr.save_log(0, "rapid_label", payload1)
        log2 = osr.save_log(0, "rapid_label", payload2)

        self.assertNotEqual(log1, log2)
        self.assertEqual(self.log_path(log1).read_text(encoding="utf-8"), payload1)
        self.assertEqual(self.log_path(log2).read_text(encoding="utf-8"), payload2)

    def test_sequence_hint_separates_same_label_writes(self):
        log1 = osr.save_log(1, "seq_label", "seq one\n")
        log2 = osr.save_log(2, "seq_label", "seq two\n")

        self.assertNotEqual(log1, log2)
        self.assertEqual(self.log_path(log1).read_text(encoding="utf-8"), "seq one\n")
        self.assertEqual(self.log_path(log2).read_text(encoding="utf-8"), "seq two\n")

    def test_concurrent_same_label_writers_retain_every_payload(self):
        payloads = ["concurrent writer A\n", "concurrent writer B\n"]
        results, errors = [], []
        barrier = threading.Barrier(len(payloads))

        def worker(payload):
            try:
                barrier.wait(timeout=10)
                results.append((payload,) + osr.write_command_log("concurrent_label", payload))
            except Exception as exc:  # surfaced by the assertions below
                errors.append(exc)

        with mock.patch("time.strftime", return_value="20261023-130000"):
            threads = [threading.Thread(target=worker, args=(p,)) for p in payloads]
            for t in threads:
                t.start()
            for t in threads:
                t.join(30)
            alive = [t for t in threads if t.is_alive()]

        self.assertEqual(alive, [], "Concurrent writers must finish within the bound")
        self.assertEqual(errors, [])
        self.assertEqual(len(results), len(payloads))
        run_ids = [run_id for _, run_id, _, _ in results]
        names = [name for _, _, name, _ in results]
        self.assertEqual(len(set(run_ids)), len(payloads), "Concurrent writers produced duplicate run ids")
        self.assertEqual(len(set(names)), len(payloads), "Concurrent writers produced duplicate log paths")
        for payload, _, name, digest in results:
            self.assertEqual(self.log_path(name).read_bytes(), payload.encode("utf-8"))
            self.assertEqual(digest, _raw_sha(self.log_path(name)))

    def test_repeated_candidate_is_retried_not_overwritten(self):
        old_payload = "original evidence bytes\n"
        new_payload = "replacement attempt bytes\n"

        with mock.patch("time.strftime", return_value="20261023-140000"), \
                mock.patch.object(osr, "new_run_id", return_value="fixedrun"):
            first_id, first, first_digest = osr.write_command_log("collide", old_payload)
            first_bytes = self.log_path(first).read_bytes()
            second_id, second, second_digest = osr.write_command_log("collide", new_payload)

            self.assertNotEqual(first_id, second_id,
                                "A collision retry must return a distinct effective run id")
            self.assertNotEqual(first, second, "A repeated candidate name must not be reused")
            self.assertEqual(self.log_path(first).read_bytes(), first_bytes,
                             "Existing log bytes were rewritten")
            self.assertEqual(self.log_path(first).read_bytes(), old_payload.encode("utf-8"))
            self.assertEqual(self.log_path(second).read_bytes(), new_payload.encode("utf-8"))
            self.assertEqual(first_digest, _raw_sha(self.log_path(first)))
            self.assertEqual(second_digest, _raw_sha(self.log_path(second)))
            self.assertIn(first_id, first)
            self.assertIn(second_id, second)

    def test_exhausted_retries_fail_and_preserve_existing_bytes(self):
        old_payload = "protected bytes\n"

        with mock.patch("time.strftime", return_value="20261023-150000"), \
                mock.patch.object(osr, "new_run_id", return_value="fixedrun"):
            first_id, first, _ = osr.write_command_log("exhaust", old_payload)
            before = self.log_path(first).read_bytes()

            with mock.patch.object(osr, "LOG_WRITE_ATTEMPTS", 1):
                with self.assertRaises(OSError):
                    osr.write_command_log("exhaust", "must not land\n")

            self.assertEqual(self.log_path(first).read_bytes(), before,
                             "Failed allocation must leave the previous log untouched")
            self.assertEqual([p.name for p in osr.ai("logs").glob("*.log")], [first])

        fresh_id, fresh, fresh_digest = osr.write_command_log("exhaust", "fresh run bytes\n")
        self.assertNotEqual(fresh_id, first_id, "A fresh run id must not reuse the failed identity")
        self.assertNotEqual(fresh, first, "A fresh run id must still allocate a log")
        self.assertEqual(self.log_path(fresh).read_text(encoding="utf-8"), "fresh run bytes\n")
        self.assertEqual(fresh_digest, _raw_sha(self.log_path(fresh)))

    def test_run_ids_are_nonempty_and_unique(self):
        ids = set()
        for _ in range(5):
            run_id, log_name, digest = osr.write_command_log("ids", "ping\n")
            self.assertTrue(run_id, "run_id must be nonempty")
            self.assertEqual(digest, _raw_sha(self.log_path(log_name)))
            ids.add(run_id)
        self.assertEqual(len(ids), 5, "run_id must be unique per executed command")


class TestRunLogsCommandOutput(_TempRootCase):
    """R20: recorded output_sha must match the bytes retained on disk."""

    def _run(self, code, label, timeout=60):
        return osr.run_recorded(_py(code), {"command_timeout_seconds": timeout}, label)

    def test_successful_command_lf_payload_exact_bytes(self):
        expected = b"line1\nline2\n"
        res = self._run("import sys; sys.stdout.buffer.write(b'line1\\nline2\\n')", "lf_run")

        self.assertEqual(res["exit"], 0)
        self.assertTrue(res["ok"], "Successful command must be recorded as ok")
        self.assertEqual(self.log_path(res["log"]).read_bytes(), expected,
                         "LF output must be stored as LF bytes")
        self.assertEqual(res["output_sha"], _sha_bytes(expected))
        self.assertEqual(res["output_sha"], _raw_sha(self.log_path(res["log"])))

    def test_crlf_payload_is_not_double_translated(self):
        expected = b"alpha\r\nbeta\r\n"
        res = self._run("import sys; sys.stdout.buffer.write(b'alpha\\r\\nbeta\\r\\n')", "crlf_run")

        self.assertEqual(res["exit"], 0)
        self.assertEqual(self.log_path(res["log"]).read_bytes(), expected,
                         "CRLF input must stay CRLF, not become CR-CR-LF")
        self.assertEqual(res["output_sha"], _sha_bytes(expected))
        self.assertEqual(res["output_sha"], _raw_sha(self.log_path(res["log"])))

    def test_unicode_payload_exact_bytes(self):
        expected = b"caf\xc3\xa9 \xe2\x9c\x93 \xf0\x9f\x98\x80\n"
        res = self._run(
            "import sys; sys.stdout.buffer.write(b'caf\\xc3\\xa9 \\xe2\\x9c\\x93 \\xf0\\x9f\\x98\\x80\\n')",
            "unicode_run",
        )

        self.assertEqual(res["exit"], 0)
        self.assertEqual(self.log_path(res["log"]).read_bytes(), expected)
        self.assertEqual(res["output_sha"], _sha_bytes(expected))
        self.assertEqual(res["output_sha"], _raw_sha(self.log_path(res["log"])))
        self.assertEqual(self.log_path(res["log"]).read_text(encoding="utf-8"), "caf\u00e9 \u2713 \U0001F600\n")

    def test_failed_command_retains_stdout_stderr_and_digest(self):
        res = self._run(
            "import sys; sys.stdout.write('partial out\\n'); sys.stderr.write('fatal err\\n'); sys.exit(2)",
            "failure_run",
        )

        self.assertEqual(res["exit"], 2)
        self.assertFalse(res["ok"], "Failing command must not be recorded as ok")
        raw = self.log_path(res["log"]).read_bytes()
        self.assertIn(b"partial out", raw, "stdout of a failing command must be retained")
        self.assertIn(b"fatal err", raw, "stderr of a failing command must be retained")
        self.assertEqual(res["output_sha"], _raw_sha(self.log_path(res["log"])))
        self.assertEqual(res["output_sha"], _sha_bytes(raw))

    def test_timeout_output_is_retained(self):
        res = self._run(
            "import sys, time; sys.stdout.buffer.write(b'partial-timeout-output\\n'); "
            "sys.stdout.flush(); time.sleep(3)",
            "timeout_run",
            timeout=1,
        )

        self.assertTrue(res["timeout"], "Slow command must be recorded as a timeout")
        self.assertEqual(res["exit"], 124)
        raw = self.log_path(res["log"]).read_bytes()
        self.assertIn(b"partial-timeout-output", raw, "Partial output before the timeout must be retained")
        self.assertEqual(res["output_sha"], _raw_sha(self.log_path(res["log"])))
        self.assertEqual(res["output_sha"], _sha_bytes(raw))

    def test_two_same_label_recorded_commands_keep_own_digest(self):
        first = self._run("import sys; sys.stdout.buffer.write(b'payload-one\\n')", "same_label_runs")
        second = self._run("import sys; sys.stdout.buffer.write(b'payload-two\\n')", "same_label_runs")

        self.assertNotEqual(first["log"], second["log"], "Same label must not share a log file")
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertTrue(first["run_id"])
        self.assertTrue(second["run_id"])
        self.assertEqual(self.log_path(first["log"]).read_bytes(), b"payload-one\n")
        self.assertEqual(self.log_path(second["log"]).read_bytes(), b"payload-two\n")
        self.assertEqual(first["output_sha"], _raw_sha(self.log_path(first["log"])))
        self.assertEqual(second["output_sha"], _raw_sha(self.log_path(second["log"])))
        self.assertNotEqual(first["output_sha"], second["output_sha"])

    def test_downstream_reread_of_each_command_log_is_independent(self):
        first = self._run("import sys; sys.stdout.buffer.write(b'first-reread-marker\\n')", "reread_label")
        second = self._run("import sys; sys.stdout.buffer.write(b'second-reread-marker\\n')", "reread_label")

        first_text = self.log_path(first["log"]).read_text(encoding="utf-8")
        second_text = self.log_path(second["log"]).read_text(encoding="utf-8")
        self.assertIn("first-reread-marker", first_text)
        self.assertNotIn("second-reread-marker", first_text)
        self.assertIn("second-reread-marker", second_text)
        self.assertNotIn("first-reread-marker", second_text)
        combined = first_text + "\n" + second_text
        self.assertIn("first-reread-marker", combined)
        self.assertIn("second-reread-marker", combined)

    def test_recorded_metadata_is_complete_and_ledger_serializable(self):
        res = self._run("import sys; sys.stdout.buffer.write(b'meta\\n')", "meta_run")

        for key in ("cmd", "exit", "ok", "run_id", "log", "output_sha", "timeout", "suspect"):
            self.assertIn(key, res, "run_recorded must expose %r for ledger records" % key)
        self.assertEqual(res["cmd"], _py("import sys; sys.stdout.buffer.write(b'meta\\n')"))
        self.assertEqual(res["exit"], 0)
        self.assertTrue(res["run_id"])
        self.assertTrue(self.log_path(res["log"]).exists())
        json.dumps(res, sort_keys=True)


class _LedgerProjectCase(_TempRootCase):
    """Drive real osr commands against a throwaway project and inspect its ledger."""

    PLAN = (
        "# Plan\n\n"
        "## Goal\n"
        "Exercise command evidence wiring in a throwaway project.\n\n"
        "## Non-goals\n"
        "No production code or policy changes.\n\n"
        "## Requirements\n"
        "- R1: Retain one command log per executed command\n"
        "  - AC: Each executed command records a run id and a digest matching its own log bytes\n"
        "  - Check: auto\n"
    )

    def setUp(self):
        super().setUp()
        osr.JSON_MODE = False

    def _write_project(self, commands, global_verify=()):
        for name in ("tasks", "logs", "snapshots"):
            osr.ai(name).mkdir(parents=True, exist_ok=True)
        osr.ai("PLAN.md").write_text(self.PLAN, encoding="utf-8")
        card = (
            "# T1: ledger wiring\n\n"
            "id: T1\n"
            "requirements: R1\n"
            "depends_on:\n"
            "allowed_files: app.py\n"
            "forbidden_files:\n"
            "context_files:\n"
            "verify: %s\n\n"
            "## Goal\n"
            "Prove that command runs are recorded in the ledger.\n\n"
            "## Constraints\n"
            "Use only this throwaway project.\n\n"
            "## Do not\n"
            "Change command authorization policy.\n\n"
            "## Definition of done\n"
            "Ledger entries carry run identities and matching log digests.\n"
        ) % commands["task_check"]
        osr.ai("tasks", "T1.md").write_text(card, encoding="utf-8")
        (osr.ROOT / "app.py").write_text("value = 1\n", encoding="utf-8")

        cfg = dict(osr.DEFAULT_CFG)
        cfg["commands"] = {n: {"cmd": c, "verified": True} for n, c in commands.items()}
        cfg["global_verify"] = list(global_verify)
        osr.save_cfg(cfg)

        led = osr.Ledger()
        for n, c in commands.items():
            led.append("cmd_confirm", name=n, cmd=c, ok=True, exit=0,
                       run_id="seed-" + n, log="seed.log", output_sha="0" * 64)

        # Real approval lineage: every command this fixture expects to run is
        # confirmed above, and the throwaway project then approves itself
        # through the real handler. The strengthened start gate requires a
        # plan_approved entry bound to the current tree. Fixture scaffolding
        # only; not a human approval of the real repository.
        self._quiet(osr.cmd_approve, argparse.Namespace(by=["temp-human"], secret=None))
        return led

    def _quiet(self, fn, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args)


class TestLedgerWiring(_LedgerProjectCase):
    """Behavioral checks that start/confirm/verify record run identities in the ledger."""

    def test_confirm_ledger_records_run_identity(self):
        cmd = _py("import sys; sys.stdout.write('confirm-marker\\n')")
        self._write_project({"task_check": cmd})
        self._quiet(osr.cmd_confirm, argparse.Namespace())

        entry = osr.Ledger().latest("cmd_confirm")
        self.assertIsNotNone(entry, "cmd_confirm must append a ledger record")
        data = entry["data"]
        self.assertEqual(data["name"], "task_check")
        self.assertEqual(data["cmd"], cmd)
        self.assertTrue(data["ok"])
        self.assertEqual(data["exit"], 0)
        self.assertTrue(data["run_id"], "cmd_confirm must record the run id")
        self.assertNotEqual(data["run_id"], "seed-task_check")
        self.assertTrue(data["log"])
        self.assertEqual(data["output_sha"], _raw_sha(self.log_path(data["log"])))
        self.assertIn("confirm-marker", self.log_path(data["log"]).read_text(encoding="utf-8"))

    def test_start_ledger_baseline_records_run_identity(self):
        cmd = _py("import sys; sys.stdout.write('baseline-marker\\n')")
        self._write_project({"task_check": cmd})
        self._quiet(osr.cmd_start, argparse.Namespace(task="T1", model="test-model"))

        entry = osr.Ledger().latest("start", "T1", 1)
        self.assertIsNotNone(entry, "cmd_start must append a start record")
        baseline = entry["data"]["baseline"]["task_0"]
        self.assertEqual(baseline["cmd"], cmd)
        self.assertTrue(baseline["ok"])
        self.assertEqual(baseline["exit"], 0)
        self.assertTrue(baseline["run_id"], "cmd_start baselines must record the run id")
        self.assertTrue(baseline["log"])
        self.assertEqual(baseline["sha"], _raw_sha(self.log_path(baseline["log"])),
                         "cmd_start must keep the existing sha key matched to its log")
        self.assertIn("baseline-marker", self.log_path(baseline["log"]).read_text(encoding="utf-8"))

    def test_verify_ledger_records_run_identity_and_rereads_each_log(self):
        cmd_global = _py("import sys; sys.stdout.write('test_alpha ... ok\\n')")
        cmd_task = _py("import sys; sys.stdout.write('test_beta ... ok\\n')")
        self._write_project(
            {"global_check": cmd_global, "task_check": cmd_task},
            global_verify=["global_check"],
        )
        self._quiet(osr.cmd_start, argparse.Namespace(task="T1", model="test-model"))

        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                osr.cmd_verify(argparse.Namespace(task="T1"))
        self.assertEqual(caught.exception.code, 0)

        entry = osr.Ledger().latest("verify", "T1", 1)
        self.assertIsNotNone(entry, "cmd_verify must append the run records to the ledger")
        data = entry["data"]
        self.assertTrue(data["ok"])
        results = data["results"]
        self.assertEqual(len(results), 2, "Both executed commands must be recorded")
        by_name = {res["name"]: res for res in results}
        self.assertEqual(set(by_name), {"global_check", "task"})
        for res in results:
            self.assertTrue(res["run_id"], "Ledger verify results must carry a run id")
            self.assertTrue(res["log"])
            self.assertNotIn("tail", res, "Echo tail is not ledger evidence")
            self.assertEqual(res["output_sha"], _raw_sha(self.log_path(res["log"])),
                             "Each result digest must match its own retained log")
        self.assertNotEqual(by_name["global_check"]["run_id"], by_name["task"]["run_id"])
        self.assertNotEqual(by_name["global_check"]["log"], by_name["task"]["log"])
        self.assertIn("test_alpha", data["passed_tests"],
                      "cmd_verify must reread the global command's own log")
        self.assertIn("test_beta", data["passed_tests"],
                      "cmd_verify must reread the task command's own log")


if __name__ == "__main__":
    unittest.main()
