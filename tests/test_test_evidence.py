"""Regression tests for R22 (T24): bind named test passes to the current run.

``TestTestEvidenceCleanControl`` is the activation baseline: current unittest
verbose output still yields its passing tests, and plain supplied text stays
the only source.

Every other class reproduces a bypass that existed before T24:

* ``extract_passed_tests`` scans every ``.ai/logs/*.xml`` file, so a historical
  report can satisfy today's acceptance and negative-test gates;
* ``cmd_verify`` re-reads each recorded log without checking ``output_sha``, so
  replaced log bytes become test evidence;
* names printed by a command that exited nonzero are still recorded as passes;
* gates use substring matching, so ``test_a_extra`` satisfies ``test_a`` and a
  short name silently collides with two different qualified tests;
* a missing declared negative test only warns while verify still succeeds.

These tests are expected to FAIL until named evidence is bound to the current,
digest-checked command output. Controls that already pass today stay in the
module so the fix cannot over-reject valid current-run evidence.
"""
import argparse
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.osr as osr


LEGIT_SAMPLE = (
    "import unittest\n"
    "\n"
    "\n"
    "class SampleTest(unittest.TestCase):\n"
    "    def test_alpha(self):\n"
    "        self.assertEqual('a' + 'b', 'ab')\n"
)

DUP_TESTS = (
    "import unittest\n"
    "\n"
    "\n"
    "class AlphaTest(unittest.TestCase):\n"
    "    def test_user(self):\n"
    "        self.assertEqual('a' + 'b', 'ab')\n"
    "\n"
    "\n"
    "class BetaTest(unittest.TestCase):\n"
    "    def test_user(self):\n"
    "        self.assertEqual('c' + 'd', 'cd')\n"
)

SUFFIX_TESTS = (
    "import unittest\n"
    "\n"
    "\n"
    "class ExtraTest(unittest.TestCase):\n"
    "    def test_missing_user_extra(self):\n"
    "        self.assertEqual('x' + 'y', 'xy')\n"
)

FAILED_RUNNER = (
    "import sys\n"
    "sys.stdout.write('test_required (failed_runner.Suite.test_required) ... ok\\n')\n"
    "sys.stdout.write('\\n----------------------------------------------------------------------\\n')\n"
    "sys.stdout.write('Ran 1 test in 0.001s\\n\\nOK\\n')\n"
    "sys.exit(1)\n"
)

PYTEST_LIKE_RUNNER = (
    "import sys\n"
    "sys.stdout.write('tests/test_param.py::test_add[alpha] PASSED\\n')\n"
    "sys.stdout.write('tests/test_param.py::test_add[beta] PASSED\\n')\n"
    "sys.stdout.write('============================== 2 passed in 0.01s ==============================\\n')\n"
)

PYTEST_DOTTED_PARAM_RUNNER = (
    "import sys\n"
    "sys.stdout.write('tests/test_p.py::test_add[value.with.dot] PASSED\\n')\n"
    "sys.stdout.write('============================== 1 passed in 0.01s ==============================\\n')\n"
)

MIXED_BARE_QUALIFIED_RUNNER = (
    "import sys\n"
    "sys.stdout.write('test_bare ... ok\\n')\n"
    "sys.stdout.write('test_other (suite.Case.test_other) ... ok\\n')\n"
    "sys.stdout.write('\\n----------------------------------------------------------------------\\n')\n"
    "sys.stdout.write('Ran 2 tests in 0.001s\\n\\nOK\\n')\n"
)

CLASS_STYLE_OUTPUT = (
    "test_user (suite_a.Case) ... ok\n"
    "test_user (suite_b.Case) ... ok\n"
)

MIXED_BARE_QUALIFIED_OUTPUT = (
    "test_bare ... ok\n"
    "test_other (suite.Case.test_other) ... ok\n"
)

MIXED_SAME_NAME_RUNNER = (
    "import sys\n"
    "sys.stdout.write('test_user ... ok\\n')\n"
    "sys.stdout.write('test_user (suite.Case.test_user) ... ok\\n')\n"
    "sys.stdout.write('\\n----------------------------------------------------------------------\\n')\n"
    "sys.stdout.write('Ran 2 tests in 0.001s\\n\\nOK\\n')\n"
)

MIXED_SAME_NAME_OUTPUT = (
    "test_user ... ok\n"
    "test_user (suite.Case.test_user) ... ok\n"
)

FORGED_LOG = (
    "test_required (forged.Suite.test_required) ... ok\n"
    "\n"
    "----------------------------------------------------------------------\n"
    "Ran 1 test in 0.001s\n"
    "\n"
    "OK\n"
)


PLAN_HEADER = (
    "# Plan\n\n"
    "## Goal\n"
    "Bind named test evidence to the current command run.\n\n"
    "## Non-goals\n"
    "No policy changes outside named test evidence.\n\n"
    "## Requirements\n"
    "- R1: Bind named evidence to the current run\n"
)


CARD_TEMPLATE = (
    "# T1: current-run named evidence\n\n"
    "id: T1\n"
    "requirements: R1\n"
    "depends_on:\n"
    "allowed_files: app.py\n"
    "forbidden_files:\n"
    "context_files:\n"
    "verify: {verify}\n"
    "{negative}"
    "\n"
    "## Goal\n"
    "Bind named test evidence to this run.\n\n"
    "## Constraints\n"
    "Use only this throwaway project.\n\n"
    "## Do not\n"
    "Accept historical or tampered evidence.\n\n"
    "## Definition of done\n"
    "Only current successful output satisfies the declared names.\n"
)


def _python(rel):
    """Shell command that runs a file of this throwaway project."""
    return '"%s" %s' % (sys.executable, rel)


def _discover(start_dir):
    """Shell command that discovers and runs the project's unittest directory."""
    return '"%s" -m unittest discover -s %s -v' % (sys.executable, start_dir)


class TestTestEvidenceCleanControl(unittest.TestCase):
    """Clean control fixture for T24 (R22): current unittest pass extraction.
    
    Verifies that extract_passed_tests extracts passed test names
    from standard unittest verbose output.
    """

    def test_clean_control_current_unittest_pass_extraction(self):
        sample_output = (
            "test_feature_alpha (tests.test_sample.SampleTest) ... ok\n"
            "test_feature_beta (tests.test_sample.SampleTest) ... ok\n"
            "\n"
            "----------------------------------------------------------------------\n"
            "Ran 2 tests in 0.005s\n"
            "\n"
            "OK\n"
        )
        passed = osr.extract_passed_tests(sample_output)
        self.assertIn("test_feature_alpha", passed)
        self.assertIn("test_feature_beta", passed)


class _EvidenceProjectCase(unittest.TestCase):
    """Drive real start/verify handlers against a throwaway project."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_root = osr.ROOT
        self._old_json = osr.JSON_MODE
        osr.ROOT = Path(self._tmp.name)
        osr.JSON_MODE = False
        for name in ("tasks", "logs", "snapshots"):
            osr.ai(name).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        osr.JSON_MODE = self._old_json
        osr.ROOT = self._old_root
        self._tmp.cleanup()

    # -- project construction -------------------------------------------------
    def write(self, rel, text):
        p = osr.ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def setUpProject(self, verify_cmd, negative_tests=(), ac_test=None, ac_text=None):
        if ac_text is None:
            ac_text = (
                "The current run emits [%s] and that exact test passes" % ac_test
                if ac_test
                else "The current run records the declared test evidence"
            )
        plan = PLAN_HEADER + "  - AC: %s\n  - Check: auto\n" % ac_text
        osr.ai("PLAN.md").write_text(plan, encoding="utf-8")

        negative = ""
        if negative_tests:
            negative = "negative_tests: %s\n" % ", ".join(negative_tests)
        card = CARD_TEMPLATE.format(verify=verify_cmd, negative=negative)
        osr.ai("tasks", "T1.md").write_text(card, encoding="utf-8")
        self.write("app.py", "value = 1\n")

        cfg = dict(osr.DEFAULT_CFG)
        cfg["commands"] = {"task_check": {"cmd": verify_cmd, "verified": True}}
        osr.save_cfg(cfg)

        osr.Ledger().append(
            "cmd_confirm", name="task_check", cmd=verify_cmd, ok=True, exit=0,
            run_id="seed-confirm", log="seed.log", output_sha="0" * 64,
        )

        # Real approval lineage for a project that expects an approved
        # workflow. The strengthened start gate requires a plan_approved entry
        # bound to the current tree, so the throwaway project approves itself
        # through the real handler. This is fixture scaffolding only; it is not
        # a human approval of the real repository.
        self.quiet(osr.cmd_approve, argparse.Namespace(by=["temp-human"], secret=None))

    def stale_xml(self, test_name, filename="20200101-000000-stale.xml"):
        return self.write(
            ".ai/logs/" + filename,
            '<testsuite><testcase name="%s" classname="old.Suite" /></testsuite>' % test_name,
        )

    # -- command driving ------------------------------------------------------
    def quiet(self, fn, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            return fn(*args)

    def start(self):
        return self.quiet(osr.cmd_start, argparse.Namespace(task="T1", model="test-model"))

    def verify_with_output(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            with self.assertRaises(SystemExit) as caught:
                osr.cmd_verify(argparse.Namespace(task="T1"))
        return caught.exception.code, out.getvalue()

    def verify(self):
        return self.verify_with_output()[0]

    # -- evidence inspection --------------------------------------------------
    def verify_entry(self):
        return osr.Ledger().latest("verify", "T1")

    def passed_tests(self):
        entry = self.verify_entry()
        if entry is None:
            return None
        return set(entry["data"].get("passed_tests", []))

    def gates(self):
        cfg = osr.load_cfg()
        st = osr.load_state()
        card = osr.parse_card("T1")
        gates, _ = osr.gate_status(cfg, st, osr.Ledger(), "T1", card)
        return {name: (ok, msg) for name, ok, msg in gates}

    def assertNotRecordedAsPass(self, name):
        passed = self.passed_tests() or set()
        self.assertNotIn(
            name, passed,
            "%r was recorded as a current-run pass: %r" % (name, sorted(passed)),
        )

    def assertGateNotSatisfied(self, name):
        gate = self.gates().get(name)
        if gate is None:
            # No fresh passing verify record exists, so the named gate cannot
            # be satisfied either: this is also a rejection.
            return
        self.assertFalse(
            gate[0],
            "gate %r accepted stale/foreign evidence (%s)" % (name, gate[1]),
        )


class TestCurrentRunControls(_EvidenceProjectCase):
    """R22 controls: valid current unittest evidence still passes."""

    def test_unambiguous_short_name_passes_verify_and_gates(self):
        self.write("sample_tests/test_sample.py", LEGIT_SAMPLE)
        self.setUpProject(_discover("sample_tests"), negative_tests=["test_alpha"],
                          ac_test="test_alpha")
        self.start()

        code = self.verify()
        self.assertEqual(code, 0, "a genuine current pass was rejected")

        self.assertIsNotNone(self.verify_entry(), "verify recorded no evidence")
        self.assertIn("test_alpha", self.passed_tests())
        gates = self.gates()
        self.assertTrue(gates["verify"][0], gates["verify"][1])
        self.assertTrue(gates["test-test_alpha"][0], gates["test-test_alpha"][1])
        self.assertTrue(gates["negative-test-test_alpha"][0],
                        gates["negative-test-test_alpha"][1])

    def test_supplied_current_output_is_still_parsed(self):
        sample_output = (
            "test_fresh (sample_tests.test_sample.SampleTest.test_fresh) ... ok\n"
            "\n----------------------------------------------------------------------\n"
            "Ran 1 test in 0.001s\n\nOK\n"
        )
        passed = osr.extract_passed_tests(sample_output)
        self.assertIn("test_fresh", passed)


class TestStaleXmlEvidence(_EvidenceProjectCase):
    """R22: old XML reports in .ai/logs are never current evidence."""

    def test_directory_xml_is_not_scanned_for_current_evidence(self):
        self.stale_xml("test_stale_only")
        passed = osr.extract_passed_tests("current run output has no test lines\n")
        self.assertNotIn(
            "test_stale_only", passed,
            "a historical XML report was treated as current run evidence",
        )

    def test_stale_xml_cannot_satisfy_a_current_negative_test(self):
        self.write("sample_tests/test_sample.py", LEGIT_SAMPLE)
        self.setUpProject(_discover("sample_tests"), negative_tests=["test_stale_only"])
        self.start()
        self.stale_xml("test_stale_only")

        code = self.verify()
        self.assertNotRecordedAsPass("test_stale_only")
        self.assertNotEqual(code, 0, "verify passed using a stale XML report")
        self.assertGateNotSatisfied("negative-test-test_stale_only")

    def test_stale_xml_cannot_satisfy_a_current_acceptance_gate(self):
        self.write("sample_tests/test_sample.py", LEGIT_SAMPLE)
        self.setUpProject(_discover("sample_tests"), ac_test="test_stale_only")
        self.start()
        self.stale_xml("test_stale_only")

        self.verify()
        self.assertNotRecordedAsPass("test_stale_only")
        self.assertGateNotSatisfied("test-test_stale_only")


class TestTamperedLogEvidence(_EvidenceProjectCase):
    """R22: logs used for extraction must match their recorded digest."""

    def test_replaced_log_bytes_do_not_supply_a_pass(self):
        self.write("sample_tests/test_sample.py", LEGIT_SAMPLE)
        self.setUpProject(_discover("sample_tests"), negative_tests=["test_required"])
        self.start()

        original = osr.write_command_log

        def tampered(label, text, *args, **kwargs):
            run_id, name, digest = original(label, text, *args, **kwargs)
            (osr.ai("logs") / name).write_text(FORGED_LOG, encoding="utf-8")
            return run_id, name, digest

        with mock.patch.object(osr, "write_command_log", side_effect=tampered):
            code, output = self.verify_with_output()

        self.assertNotRecordedAsPass("test_required")
        self.assertNotEqual(
            code, 0,
            "verify trusted a log whose bytes no longer match output_sha\n%s" % output,
        )
        self.assertGateNotSatisfied("negative-test-test_required")


class TestFailedCommandEvidence(_EvidenceProjectCase):
    """R22: a nonzero command cannot supply test names as passes."""

    def test_failed_command_test_names_are_not_passes(self):
        self.write("failed_runner.py", FAILED_RUNNER)
        self.setUpProject(_python("failed_runner.py"), negative_tests=["test_required"])
        self.start()

        code = self.verify()
        self.assertNotEqual(code, 0, "a failing command produced a passing verify")
        entry = self.verify_entry()
        self.assertIsNotNone(entry, "verify recorded no evidence")
        self.assertFalse(entry["data"].get("ok"), "a failed command produced ok evidence")
        self.assertNotRecordedAsPass("test_required")
        self.assertGateNotSatisfied("negative-test-test_required")


class TestMissingNegativeTest(_EvidenceProjectCase):
    """R22: a missing declared negative test fails verify, not just warns."""

    def test_missing_declared_negative_test_fails_verify(self):
        self.write("sample_tests/test_sample.py", LEGIT_SAMPLE)
        self.setUpProject(_discover("sample_tests"), negative_tests=["test_absent_negative"],
                          ac_test="test_alpha")
        self.start()

        code, output = self.verify_with_output()
        self.assertNotEqual(
            code, 0,
            "verify succeeded while the declared negative test never ran\n%s" % output,
        )
        self.assertNotRecordedAsPass("test_absent_negative")
        self.assertGateNotSatisfied("negative-test-test_absent_negative")


class TestTestIdentityCollisions(_EvidenceProjectCase):
    """R22: exact qualified identity; ambiguous short names fail."""

    def test_suffix_collision_does_not_satisfy_shorter_declaration(self):
        self.write("suffix_tests/test_user_extra.py", SUFFIX_TESTS)
        self.setUpProject(_discover("suffix_tests"), negative_tests=["test_missing_user"])
        self.start()

        code, output = self.verify_with_output()
        self.assertNotEqual(
            code, 0,
            "test_missing_user_extra satisfied the declared test_missing_user\n%s" % output,
        )
        self.assertGateNotSatisfied("negative-test-test_missing_user")

    def test_duplicate_short_names_are_reported_as_ambiguous(self):
        self.write("dup_tests/test_dup.py", DUP_TESTS)
        self.setUpProject(_discover("dup_tests"), negative_tests=["test_user"])
        self.start()

        code, output = self.verify_with_output()
        self.assertNotEqual(
            code, 0,
            "an ambiguous short name was silently accepted\n%s" % output,
        )
        self.assertIn(
            "ambiguous", output.lower(),
            "the rejection diagnostic does not explain the ambiguity:\n%s" % output,
        )
        self.assertGateNotSatisfied("negative-test-test_user")

    def test_exact_qualified_name_satisfies_the_gate(self):
        self.write("sample_tests/test_sample.py", LEGIT_SAMPLE)
        self.setUpProject(
            _discover("sample_tests"),
            negative_tests=["test_sample.SampleTest.test_alpha"],
        )
        self.start()

        code = self.verify()
        self.assertEqual(code, 0, "an exact qualified identity was rejected")
        self.assertIn("test_sample.SampleTest.test_alpha", self.passed_tests())
        gate = self.gates()["negative-test-test_sample.SampleTest.test_alpha"]
        self.assertTrue(gate[0], gate[1])

    def test_two_qualified_tests_are_both_satisfiable_exactly(self):
        self.write("dup_tests/test_dup.py", DUP_TESTS)
        self.setUpProject(
            _discover("dup_tests"),
            negative_tests=[
                "test_dup.AlphaTest.test_user",
                "test_dup.BetaTest.test_user",
            ],
        )
        self.start()

        code = self.verify()
        self.assertEqual(code, 0, "qualified identities were rejected because their short names collide")
        gates = self.gates()
        for name in ("test_dup.AlphaTest.test_user", "test_dup.BetaTest.test_user"):
            self.assertTrue(gates["negative-test-" + name][0],
                            gates["negative-test-" + name][1])


class TestParameterizedIdentities(_EvidenceProjectCase):
    """R22: parameter identities are preserved, not collapsed or suffixed."""

    def test_captured_pytest_qualified_id_is_recognised(self):
        vendor = (Path(__file__).resolve().parent.parent
                  / "docs" / "vendor" / "runner_outputs" / "pytest_output.txt")
        passed = osr.extract_passed_tests(vendor.read_text(encoding="utf-8"))
        self.assertIn(
            "test_mod.py::test_case", passed,
            "the captured pytest identity was not preserved: %r" % (passed,),
        )

    def test_exact_parameter_identity_satisfies_the_gate(self):
        self.write("pytest_like_runner.py", PYTEST_LIKE_RUNNER)
        self.setUpProject(
            _python("pytest_like_runner.py"),
            negative_tests=["tests/test_param.py::test_add[alpha]"],
        )
        self.start()

        code = self.verify()
        self.assertEqual(code, 0, "an exact parameterized identity was rejected")
        gate = self.gates()["negative-test-tests/test_param.py::test_add[alpha]"]
        self.assertTrue(gate[0], gate[1])

    def test_different_parameter_identity_does_not_satisfy(self):
        self.write("pytest_like_runner.py", PYTEST_LIKE_RUNNER)
        self.setUpProject(
            _python("pytest_like_runner.py"),
            negative_tests=["tests/test_param.py::test_add[gamma]"],
        )
        self.start()

        code = self.verify()
        self.assertNotEqual(code, 0, "a different parameter identity was accepted")
        self.assertGateNotSatisfied("negative-test-tests/test_param.py::test_add[gamma]")


class TestAcceptanceDeclarationTags(_EvidenceProjectCase):
    """R22: every syntactically declared acceptance test becomes a gate.

    The old bracketed-tag regex only allowed ``[a-zA-Z0-9_.:-]``, so a pytest
    path declaration such as ``[tests/test_param.py::test_absent]`` was silently
    skipped and never produced an acceptance gate at all.
    """

    def test_pytest_path_declaration_creates_a_failing_acceptance_gate(self):
        self.write("sample_tests/test_sample.py", LEGIT_SAMPLE)
        self.setUpProject(_discover("sample_tests"),
                          ac_test="tests/test_param.py::test_absent")
        self.start()

        code = self.verify()
        self.assertEqual(
            code, 0,
            "a failing acceptance declaration must not be turned into a verify failure",
        )
        gates = self.gates()
        key = "test-tests/test_param.py::test_absent"
        self.assertIn(
            key, gates,
            "a declared pytest acceptance test disappeared from the gates: %r"
            % (sorted(gates),),
        )
        self.assertFalse(
            gates[key][0],
            "an absent acceptance test satisfied its gate (%s)" % (gates[key][1],),
        )

    def test_nested_parameter_declaration_satisfies_the_gate(self):
        self.write("pytest_like_runner.py", PYTEST_LIKE_RUNNER)
        self.setUpProject(_python("pytest_like_runner.py"),
                          ac_test="tests/test_param.py::test_add[alpha]")
        self.start()

        code = self.verify()
        self.assertEqual(code, 0, "a genuine current parameterized pass was rejected")
        gates = self.gates()
        key = "test-tests/test_param.py::test_add[alpha]"
        self.assertIn(
            key, gates,
            "a nested parameter declaration disappeared from the gates: %r"
            % (sorted(gates),),
        )
        self.assertTrue(gates[key][0], gates[key][1])

    def test_unsupported_declared_form_rejects_with_a_diagnostic(self):
        self.write("sample_tests/test_sample.py", LEGIT_SAMPLE)
        self.setUpProject(_discover("sample_tests"),
                          ac_test="tests/test_param.py::test_add[*]")
        self.start()
        self.verify()

        gates = self.gates()
        key = "test-tests/test_param.py::test_add[*]"
        self.assertIn(
            key, gates,
            "an unsupported declared form disappeared from the gates: %r"
            % (sorted(gates),),
        )
        self.assertFalse(gates[key][0], "an unsupported declaration was accepted")
        self.assertIn(
            "unsupported", gates[key][1].lower(),
            "the rejection does not explain the unsupported form: %s" % (gates[key][1],),
        )

    def test_whitespace_parameter_declaration_creates_a_failing_gate(self):
        self.write("pytest_like_runner.py", PYTEST_LIKE_RUNNER)
        self.setUpProject(
            _python("pytest_like_runner.py"),
            ac_text=(
                "The current run emits "
                "[tests/test_p.py::test_add[value with space]] "
                "and that exact test passes"
            ),
        )
        self.start()
        self.verify()

        gates = self.gates()
        key = "test-tests/test_p.py::test_add[value with space]"
        self.assertIn(
            key, gates,
            "a whitespace-containing declaration disappeared from the gates: %r"
            % (sorted(gates),),
        )
        self.assertFalse(
            gates[key][0],
            "unsupported whitespace identity passed using other parameter evidence (%s)"
            % (gates[key][1],),
        )
        self.assertIn(
            "unsupported", gates[key][1].lower(),
            "the rejection does not explain the unsupported identity: %s"
            % (gates[key][1],),
        )

    def test_deeper_parameter_declaration_keeps_the_complete_identity(self):
        self.write("pytest_like_runner.py", PYTEST_LIKE_RUNNER)
        self.setUpProject(
            _python("pytest_like_runner.py"),
            ac_text=(
                "The current run emits "
                "[tests/test_p.py::test_add[[nested]]] "
                "and that exact test passes"
            ),
        )
        self.start()
        self.verify()

        gates = self.gates()
        key = "test-tests/test_p.py::test_add[[nested]]"
        self.assertNotIn(
            "test-nested", gates,
            "a deeper bracket declaration was reinterpreted as its inner name: %r"
            % (sorted(gates),),
        )
        self.assertIn(
            key, gates,
            "the complete deeper bracket declaration disappeared from the gates: %r"
            % (sorted(gates),),
        )
        self.assertFalse(
            gates[key][0],
            "an unrun deeper bracket identity satisfied its gate (%s)"
            % (gates[key][1],),
        )

    def test_outermost_declarations_keep_complete_identities(self):
        tags = osr.acceptance_test_tags(
            "Use [tests/test_p.py::test_add[value with space]] "
            "and [tests/test_p.py::test_add[[nested]]]"
        )
        self.assertEqual(
            tags,
            [
                "tests/test_p.py::test_add[value with space]",
                "tests/test_p.py::test_add[[nested]]",
            ],
            "outermost declarations were not retained whole: %r" % (tags,),
        )

    def test_deeper_bracket_identity_is_supported_literally(self):
        matched, reason = osr.resolve_test_declaration(
            "tests/test_p.py::test_add[[nested]]",
            ["tests/test_p.py::test_add[[nested]]"],
        )
        self.assertEqual(
            reason, "ok",
            "a complete literal deeper bracket identity was rejected: %r" % (matched,),
        )
        self.assertEqual(matched, ["tests/test_p.py::test_add[[nested]]"])


class TestClassStyleUnittestQualifiers(unittest.TestCase):
    """R22: the documented ``method (module.Class) ... ok`` form keeps its class.

    ``docs/vendor/runner_outputs/unittest_output.txt`` contains
    ``test_case (test_mod.TestClass) ... ok``. Discarding the qualifier collapses
    this identity to ``test_case`` and hides collisions between two classes that
    both define the same method.
    """

    def test_captured_unittest_fixture_identity_is_canonical(self):
        vendor = (Path(__file__).resolve().parent.parent
                  / "docs" / "vendor" / "runner_outputs" / "unittest_output.txt")
        passed = osr.extract_passed_tests(vendor.read_text(encoding="utf-8"))
        self.assertIn(
            "test_mod.TestClass.test_case", passed,
            "the documented class-style identity was not constructed: %r" % (passed,),
        )
        self.assertIn("test_case", passed)

    def test_exact_class_style_declaration_resolves(self):
        canonical, _aliases = osr.extract_test_identities(CLASS_STYLE_OUTPUT)
        matched, reason = osr.resolve_test_declaration("suite_a.Case.test_user", canonical)
        self.assertEqual(
            reason, "ok",
            "an exact class-style identity did not resolve: %r" % (canonical,),
        )
        self.assertEqual(matched, ["suite_a.Case.test_user"])

    def test_ambiguous_class_style_short_declaration_rejects(self):
        canonical, _aliases = osr.extract_test_identities(CLASS_STYLE_OUTPUT)
        matched, reason = osr.resolve_test_declaration("test_user", canonical)
        self.assertEqual(
            reason, "ambiguous",
            "two class-style tests were collapsed into one short name: %r" % (canonical,),
        )
        self.assertEqual(matched, ["suite_a.Case.test_user", "suite_b.Case.test_user"])


class TestMixedBareAndQualifiedEvidence(_EvidenceProjectCase):
    """R22: a genuine bare pass survives alongside qualified identities."""

    def test_mixed_evidence_keeps_the_genuine_bare_pass(self):
        self.write("mixed_runner.py", MIXED_BARE_QUALIFIED_RUNNER)
        self.setUpProject(_python("mixed_runner.py"), negative_tests=["test_bare"])
        self.start()

        code = self.verify()
        self.assertEqual(
            code, 0,
            "a genuine bare pass was rejected because another test was qualified",
        )
        gates = self.gates()
        self.assertTrue(gates["negative-test-test_bare"][0],
                        gates["negative-test-test_bare"][1])

    def test_derived_aliases_are_not_canonical_identities(self):
        self.write("mixed_runner.py", MIXED_BARE_QUALIFIED_RUNNER)
        self.setUpProject(_python("mixed_runner.py"))
        self.start()
        self.verify()

        entry = self.verify_entry()
        self.assertIsNotNone(entry, "verify recorded no evidence")
        canonical = set(entry["data"].get("canonical_tests") or [])
        self.assertEqual(
            canonical, {"test_bare", "suite.Case.test_other"},
            "canonical evidence must not include derived short-name aliases: %r"
            % (sorted(canonical),),
        )

    def test_bare_identity_does_not_hide_a_same_name_collision(self):
        canonical, _aliases = osr.extract_test_identities(MIXED_SAME_NAME_OUTPUT)
        self.assertEqual(
            sorted(canonical), ["suite.Case.test_user", "test_user"],
            "the bare and qualified identities were not kept distinct: %r"
            % (sorted(canonical),),
        )
        matched, reason = osr.resolve_test_declaration("test_user", canonical)
        self.assertEqual(
            reason, "ambiguous",
            "a bare exact match hid a second test with the same terminal name: %r"
            % (canonical,),
        )
        self.assertEqual(matched, ["suite.Case.test_user", "test_user"])


class TestSameTerminalNameBareAndQualified(_EvidenceProjectCase):
    """R22: a bare exact match must not bypass short-name uniqueness.

    ``test_user ... ok`` and ``test_user (suite.Case.test_user) ... ok`` are two
    distinct canonical tests. Declaring the short name must be ambiguous, and a
    negative declaration must fail verify rather than accept either candidate.
    """

    def test_short_negative_declaration_is_ambiguous_end_to_end(self):
        self.write("mixed_same_name_runner.py", MIXED_SAME_NAME_RUNNER)
        self.setUpProject(
            _python("mixed_same_name_runner.py"),
            negative_tests=["test_user"],
            ac_text="The current run emits [test_user] and that exact test passes",
        )
        self.start()

        code, output = self.verify_with_output()
        self.assertNotEqual(
            code, 0,
            "a short declaration with two same-name candidates was accepted\n%s" % output,
        )
        self.assertIn(
            "ambiguous", output.lower(),
            "the rejection diagnostic does not explain the ambiguity:\n%s" % output,
        )
        for identity in ("suite.Case.test_user", "test_user"):
            self.assertIn(
                identity, output,
                "candidate %r is missing from the ambiguity diagnostic:\n%s"
                % (identity, output),
            )

        gates = self.gates()
        for key in ("negative-test-test_user", "test-test_user"):
            self.assertIn(
                key, gates,
                "a same-name short declaration disappeared from the gates: %r"
                % (sorted(gates),),
            )
            self.assertFalse(
                gates[key][0],
                "gate %r accepted one of two same-name candidates (%s)"
                % (key, gates[key][1]),
            )
            self.assertIn(
                "ambiguous", gates[key][1].lower(),
                "gate %r does not explain the ambiguity: %s" % (key, gates[key][1]),
            )

        entry = self.verify_entry()
        self.assertIsNotNone(entry, "verify recorded no evidence")
        canonical = set(entry["data"].get("canonical_tests") or [])
        self.assertEqual(
            canonical, {"test_user", "suite.Case.test_user"},
            "derived aliases must not be invented as executed tests: %r"
            % (sorted(canonical),),
        )


class TestDottedParameterIdentity(unittest.TestCase):
    """R22: dots inside a parameter value are part of the identity."""

    def test_terminal_name_preserves_dotted_parameter(self):
        self.assertEqual(
            osr.terminal_test_name("tests/test_p.py::test_add[value.with.dot]"),
            "test_add[value.with.dot]",
            "splitting on dots corrupted the parameter identity",
        )


class TestDottedParameterEvidence(_EvidenceProjectCase):
    """R22: exact, short and wrong dotted-parameter declarations behave."""

    def test_exact_and_short_dotted_parameter_declarations_pass(self):
        self.write("dotted_runner.py", PYTEST_DOTTED_PARAM_RUNNER)
        self.setUpProject(
            _python("dotted_runner.py"),
            negative_tests=[
                "tests/test_p.py::test_add[value.with.dot]",
                "test_add[value.with.dot]",
            ],
        )
        self.start()

        code = self.verify()
        self.assertEqual(code, 0, "a dotted parameter identity was rejected")
        gates = self.gates()
        for name in ("tests/test_p.py::test_add[value.with.dot]",
                     "test_add[value.with.dot]"):
            key = "negative-test-" + name
            self.assertIn(key, gates)
            self.assertTrue(gates[key][0], gates[key][1])

    def test_different_dotted_parameter_rejects(self):
        self.write("dotted_runner.py", PYTEST_DOTTED_PARAM_RUNNER)
        self.setUpProject(
            _python("dotted_runner.py"),
            negative_tests=["tests/test_p.py::test_add[value.with.out]"],
        )
        self.start()

        code = self.verify()
        self.assertNotEqual(code, 0, "a different dotted parameter was accepted")
        self.assertGateNotSatisfied("negative-test-tests/test_p.py::test_add[value.with.out]")


if __name__ == "__main__":
    unittest.main()
