"""Regression tests for R21: authorize the exact confirmed command.

The clean control in ``TestCommandAuthorizationCleanControl`` is the activation
baseline: an exact command confirmed by config and ledger is authorized.

Every other test in this module reproduces a bypass that existed before T23.
They are expected to FAIL until ``is_verify_cmd_confirmed`` (and its quick /
fixture-capture callers) authorize the exact trimmed command string only.
"""
import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import scripts.osr as osr


LEGIT_CMD = "python -m unittest discover -s tests -p test_authorization.py -v"

PLAN_TEXT = (
    "# Plan\n\n"
    "## Goal\n"
    "Exercise exact command authorization.\n\n"
    "## Non-goals\n"
    "No production code or policy changes.\n\n"
    "## Requirements\n"
    "- R1: Authorize the exact confirmed command\n"
    "  - AC: An exact confirmed command is authorized and every variant is rejected\n"
    "  - Check: auto\n"
)


def _script_cmd(script):
    """Build a shell command that runs ``script`` with this interpreter."""
    return '"%s" %s' % (sys.executable, script)


def _config(commands, allow_no_commands=False):
    """Build a config dict; ``commands`` maps name -> (cmd, verified)."""
    cfg = dict(osr.DEFAULT_CFG)
    cfg["commands"] = {
        name: {"cmd": cmd, "verified": verified}
        for name, (cmd, verified) in commands.items()
    }
    cfg["allow_no_commands"] = allow_no_commands
    return cfg


def _confirmation(name, cmd, ok=True):
    return {"type": "cmd_confirm", "data": {"name": name, "cmd": cmd, "ok": ok}}


class _DummyLedger:
    def __init__(self, records):
        self._records = records

    def entries(self):
        return self._records


class TestCommandAuthorizationCleanControl(unittest.TestCase):
    """Clean control fixture for T23 (R21): exact confirmed command.
    
    Verifies that an exact command confirmed in config and ledger
    passes verification command authorization.
    """

    def test_clean_control_exact_confirmed_command(self):
        cmd_str = "python -m unittest discover -s tests -p test_command_authorization.py -v"
        cfg = {
            "allow_no_commands": False,
            "commands": {
                "test_cmd": {
                    "cmd": cmd_str,
                    "verified": True,
                }
            },
        }

        class DummyLedger:
            def entries(self):
                return [{
                    "type": "cmd_confirm",
                    "data": {
                        "name": "test_cmd",
                        "cmd": cmd_str,
                        "ok": True,
                    },
                }]

        dummy_led = DummyLedger()
        self.assertTrue(osr.is_verify_cmd_confirmed(cmd_str, cfg, dummy_led))


class TestExactCommandAuthorization(unittest.TestCase):
    """R21: a confirmation authorizes one exact command, not a command family."""

    def setUp(self):
        self.cfg = _config({"legit": (LEGIT_CMD, True)})
        self.led = _DummyLedger([_confirmation("legit", LEGIT_CMD)])

    def assertRejected(self, candidate):
        self.assertFalse(
            osr.is_verify_cmd_confirmed(candidate, self.cfg, self.led),
            "Command %r inherited authorization from %r" % (candidate, LEGIT_CMD),
        )

    def assertAccepted(self, candidate):
        self.assertTrue(
            osr.is_verify_cmd_confirmed(candidate, self.cfg, self.led),
            "Exact confirmed command %r was rejected" % (candidate,),
        )

    def test_outer_whitespace_is_trimmed(self):
        self.assertAccepted("  %s  " % LEGIT_CMD)
        self.assertAccepted("\t%s \n" % LEGIT_CMD)

    def test_internal_whitespace_difference_is_not_equivalent(self):
        self.assertRejected(LEGIT_CMD.replace("unittest discover", "unittest  discover"))

    def test_different_script_same_executable_is_rejected(self):
        # The original bypass: python arbitrary_script.py after confirming python -m ...
        self.assertRejected('"%s" arbitrary_script.py' % sys.executable)
        self.assertRejected("python arbitrary_script.py")

    def test_different_module_is_rejected(self):
        self.assertRejected(
            "python -m unittest discover -s tests -p test_other.py -v"
        )
        self.assertRejected(
            "python -m pytest tests/test_command_authorization.py -v"
        )

    def test_different_argument_list_is_rejected(self):
        self.assertRejected(LEGIT_CMD + " -k authorization")
        self.assertRejected(LEGIT_CMD.replace("-p", "--pattern"))

    def test_different_executable_is_rejected(self):
        self.assertRejected(
            "python3 -m unittest discover -s tests -p test_authorization.py -v"
        )
        self.assertRejected(
            "bash -c 'python -m unittest discover -s tests -p test_authorization.py -v'"
        )

    def test_quoted_and_unquoted_executable_are_not_equivalent(self):
        self.assertRejected(
            '"python" -m unittest discover -s tests -p test_authorization.py -v'
        )

    def test_shell_suffix_is_rejected(self):
        self.assertRejected(LEGIT_CMD + " && python arbitrary_script.py")
        self.assertRejected(LEGIT_CMD + " ; python arbitrary_script.py")
        self.assertRejected(LEGIT_CMD + " & python arbitrary_script.py")

    def test_redirection_and_pipeline_are_rejected(self):
        self.assertRejected(LEGIT_CMD + " > tests/out.txt")
        self.assertRejected(LEGIT_CMD + " 2>&1")
        self.assertRejected(LEGIT_CMD + " | tee tests/out.txt")

    def test_case_difference_is_rejected(self):
        self.assertRejected(LEGIT_CMD.replace("python", "Python", 1))

    def test_empty_command_is_rejected(self):
        self.assertRejected("")
        self.assertRejected("   ")


class TestMissingConfirmation(unittest.TestCase):
    """R21: config verified=true alone is not confirmation; the ledger decides."""

    def test_config_verified_without_ledger_record_is_rejected(self):
        cfg = _config({"legit": (LEGIT_CMD, True)})
        self.assertFalse(
            osr.is_verify_cmd_confirmed(LEGIT_CMD, cfg, _DummyLedger([])),
            "A config entry with verified=true but no ledger confirmation was authorized",
        )

    def test_no_confirmed_commands_rejects_even_exact_config_command(self):
        cfg = _config({"legit": (LEGIT_CMD, True), "other": ("python other.py", False)})
        self.assertFalse(osr.is_verify_cmd_confirmed(LEGIT_CMD, cfg, _DummyLedger([])))

    def test_unverified_config_entry_with_ledger_record_is_rejected(self):
        cfg = _config({"legit": (LEGIT_CMD, False)})
        led = _DummyLedger([_confirmation("legit", LEGIT_CMD)])
        self.assertFalse(osr.is_verify_cmd_confirmed(LEGIT_CMD, cfg, led))

    def test_failed_confirmation_does_not_authorize(self):
        cfg = _config({"legit": (LEGIT_CMD, True)})
        led = _DummyLedger([_confirmation("legit", LEGIT_CMD, ok=False)])
        self.assertFalse(osr.is_verify_cmd_confirmed(LEGIT_CMD, cfg, led))

    def test_failed_reconfirmation_supersedes_earlier_success(self):
        cfg = _config({"legit": (LEGIT_CMD, True)})
        led = _DummyLedger([
            _confirmation("legit", LEGIT_CMD, ok=True),
            _confirmation("legit", LEGIT_CMD, ok=False),
        ])
        self.assertFalse(
            osr.is_verify_cmd_confirmed(LEGIT_CMD, cfg, led),
            "A failed reconfirmation left the earlier success in force",
        )

    def test_changed_config_command_invalidates_old_confirmation(self):
        old_cmd = LEGIT_CMD
        new_cmd = "python -m unittest discover -s tests -p test_other.py -v"
        led = _DummyLedger([_confirmation("legit", old_cmd)])
        self.assertTrue(osr.is_verify_cmd_confirmed(old_cmd, _config({"legit": (old_cmd, True)}), led))
        changed = _config({"legit": (new_cmd, True)})
        self.assertFalse(
            osr.is_verify_cmd_confirmed(old_cmd, changed, led),
            "The replaced command kept its old confirmation",
        )
        self.assertFalse(
            osr.is_verify_cmd_confirmed(new_cmd, changed, led),
            "The edited command inherited the old confirmation",
        )

    def test_empty_configuration_rejects(self):
        cfg = _config({})
        self.assertFalse(osr.is_verify_cmd_confirmed(LEGIT_CMD, cfg, _DummyLedger([])))


class TestCompatibilityEscape(unittest.TestCase):
    """R21: allow_no_commands remains the documented compatibility escape."""

    def test_allow_no_commands_still_permits_execution(self):
        cfg = _config({}, allow_no_commands=True)
        self.assertTrue(osr.is_verify_cmd_confirmed(LEGIT_CMD, cfg, _DummyLedger([])))
        self.assertTrue(
            osr.is_verify_cmd_confirmed('"%s" arbitrary.py' % sys.executable, cfg, _DummyLedger([]))
        )


class _TempProjectCase(unittest.TestCase):
    """Run authorization callers against a throwaway project root."""

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

    def write(self, rel, text):
        p = osr.ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def write_cfg(self, commands, allow_no_commands=False):
        cfg = _config(commands, allow_no_commands=allow_no_commands)
        osr.save_cfg(cfg)
        return cfg

    def confirm(self, name, cmd, ok=True):
        osr.Ledger().append(
            "cmd_confirm",
            name=name,
            cmd=cmd,
            ok=ok,
            exit=0 if ok else 1,
            run_id="seed-" + name,
            log="seed.log",
            output_sha="0" * 64,
        )

    def approve_project(self):
        osr.ai("PLAN.md").write_text(PLAN_TEXT, encoding="utf-8")
        cfg = osr.load_cfg()
        if any(osr.confirmed(cfg, osr.Ledger(), n) for n in cfg.get("commands", {})):
            # Approved-workflow fixture: create real approval lineage bound to
            # this throwaway tree through the real handler. This is temporary
            # project scaffolding, never a human approval of the real repo.
            self.run_approve()
            return
        # Deliberately never-approved control: no command was confirmed, so the
        # fixture keeps the approval absent and only mirrors the input hashes.
        st = osr.load_state()
        st["plan_hash"] = osr.sha_text(PLAN_TEXT)
        st["config_hash"] = osr.sha_config()
        osr.save_state(st)

    def write_plan(self):
        return self.write(".ai/PLAN.md", PLAN_TEXT)

    def run_confirm(self):
        """Run the real confirmation handler inside the throwaway project."""
        return self.quiet(osr.cmd_confirm, argparse.Namespace())

    def run_approve(self, by="temp-human"):
        """Run the real approval handler inside the throwaway project."""
        return self.quiet(osr.cmd_approve, argparse.Namespace(by=[by], secret=None))

    def quiet(self, fn, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            return fn(*args)

    def write_card(self, verify, conformance=None):
        extra = ""
        if conformance is not None:
            extra = "conformance: %s\n" % conformance
        card = (
            "# T1: exact command authorization\n\n"
            "id: T1\n"
            "requirements: R1\n"
            "depends_on:\n"
            "allowed_files: app.py, legit.py, attacker.py\n"
            "forbidden_files:\n"
            "context_files:\n"
            "verify: %s\n"
            "%s\n"
            "## Goal\n"
            "Authorize only the exact confirmed command.\n\n"
            "## Constraints\n"
            "Use a throwaway project.\n\n"
            "## Do not\n"
            "Loosen the authorization gate.\n\n"
            "## Definition of done\n"
            "Variants are rejected and the exact command is authorized.\n"
        ) % (verify, extra)
        return self.write(".ai/tasks/T1.md", card)


class TestCardAuthorization(_TempProjectCase):
    """R21: card verify and conformance use the same exact rule."""

    def test_card_verify_exact_confirmed_command_passes(self):
        self.write_cfg({"legit": (LEGIT_CMD, True)})
        self.confirm("legit", LEGIT_CMD)
        self.write_card(verify=LEGIT_CMD)

        card, errs = osr.validate_card("T1", osr.load_cfg(), {"R1": {}})
        self.assertIsNotNone(card)
        self.assertEqual(errs, [])

    def test_card_verify_unconfirmed_variant_is_rejected(self):
        self.write_cfg({"legit": (LEGIT_CMD, True)})
        self.confirm("legit", LEGIT_CMD)
        self.write_card(verify='"%s" attacker.py' % sys.executable)

        _, errs = osr.validate_card("T1", osr.load_cfg(), {"R1": {}})
        self.assertTrue(
            any("not confirmed" in e for e in errs),
            "Unconfirmed verify command was accepted: %r" % (errs,),
        )

    def test_card_verify_without_ledger_confirmation_is_rejected(self):
        self.write_cfg({"legit": (LEGIT_CMD, True)})
        self.write_card(verify=LEGIT_CMD)

        _, errs = osr.validate_card("T1", osr.load_cfg(), {"R1": {}})
        self.assertTrue(
            any("not confirmed" in e for e in errs),
            "verified=true without a ledger confirmation was accepted: %r" % (errs,),
        )

    def test_card_conformance_unconfirmed_variant_is_rejected(self):
        conformance = "python -m unittest discover -s tests -p test_other.py -v"
        self.write_cfg({"legit": (LEGIT_CMD, True)})
        self.confirm("legit", LEGIT_CMD)
        self.write_card(verify=LEGIT_CMD, conformance=conformance)

        _, errs = osr.validate_card("T1", osr.load_cfg(), {"R1": {}})
        self.assertTrue(
            any("conformance" in e and "not confirmed" in e for e in errs),
            "Unconfirmed conformance command was accepted: %r" % (errs,),
        )

    def test_card_conformance_exact_confirmed_command_passes(self):
        conformance = '"%s" -c "import sys; sys.exit(0)"' % sys.executable
        self.write_cfg({"legit": (LEGIT_CMD, True), "conf": (conformance, True)})
        self.confirm("legit", LEGIT_CMD)
        self.confirm("conf", conformance)
        self.write_card(verify=LEGIT_CMD, conformance=conformance)

        _, errs = osr.validate_card("T1", osr.load_cfg(), {"R1": {}})
        self.assertEqual(errs, [])


class TestFixtureCaptureAuthorization(_TempProjectCase):
    """R21: fixture capture must not execute a variant of a confirmed command."""

    def _attacker_marker(self):
        marker_dir = tempfile.TemporaryDirectory()
        self.addCleanup(marker_dir.cleanup)
        marker = Path(marker_dir.name) / "attacker_ran.txt"
        self.write(
            "attacker.py",
            "from pathlib import Path\nPath(%r).write_text('ran', encoding='utf-8')\n" % str(marker),
        )
        return marker

    def test_exact_confirmed_raw_command_is_captured(self):
        cmd = _script_cmd("legit.py")
        self.write("legit.py", "print('fixture-payload')\n")
        self.write_cfg({"legit": (cmd, True)})
        self.confirm("legit", cmd)

        self.quiet(
            osr.cmd_fixture_capture,
            argparse.Namespace(path="fixtures/out.txt", seam="s1", cmd=cmd),
        )

        self.assertIn("fixture-payload", (osr.ROOT / "fixtures/out.txt").read_text(encoding="utf-8"))
        state = osr.load_state()
        self.assertEqual(state["fixtures"]["fixtures/out.txt"]["cmd"], cmd)

    def test_confirmed_config_name_is_still_accepted(self):
        cmd = _script_cmd("legit.py")
        self.write("legit.py", "print('named-payload')\n")
        self.write_cfg({"capture_provider": (cmd, True)})
        self.confirm("capture_provider", cmd)

        self.quiet(
            osr.cmd_fixture_capture,
            argparse.Namespace(path="fixtures/named.txt", seam="s1", cmd="capture_provider"),
        )

        self.assertIn("named-payload", (osr.ROOT / "fixtures/named.txt").read_text(encoding="utf-8"))

    def test_different_script_same_executable_is_not_captured(self):
        marker = self._attacker_marker()
        self.write_cfg({"legit": (LEGIT_CMD, True)})
        self.confirm("legit", LEGIT_CMD)

        with self.assertRaises(SystemExit) as caught:
            self.quiet(
                osr.cmd_fixture_capture,
                argparse.Namespace(
                    path="fixtures/attack.txt",
                    seam="s1",
                    cmd="python attacker.py",
                ),
            )

        self.assertNotEqual(caught.exception.code, 0)
        self.assertFalse(marker.exists(), "fixture-capture executed an unconfirmed command")
        self.assertFalse((osr.ROOT / "fixtures/attack.txt").exists())
        self.assertIsNone(
            osr.Ledger().latest("fixture_capture"),
            "a rejected fixture capture still recorded capture evidence",
        )


class TestQuickAuthorization(_TempProjectCase):
    """R21: quick uses the same authorization rule plus integrity/weak checks."""

    def _project(self, commands, confirm=()):
        self.write_cfg(commands)
        for name in confirm:
            self.confirm(name, commands[name][0])
        self.approve_project()

    def assertNoQuickEvidence(self):
        self.assertIsNone(
            osr.Ledger().latest("quick_verify"),
            "a rejected quick run still recorded successful quick evidence",
        )

    def test_exact_confirmed_command_passes(self):
        cmd = _script_cmd("legit.py")
        self.write("legit.py", "print('quick-ok')\n")
        self._project({"legit": (cmd, True)}, confirm=("legit",))

        self.quiet(osr.cmd_quick, argparse.Namespace(verify=cmd, allowed=None))

        self.assertIsNotNone(osr.Ledger().latest("quick_verify"))

    def test_exact_confirmed_command_passes_without_plan_approval(self):
        cmd = _script_cmd("legit.py")
        self.write("legit.py", "print('quick-ok')\n")
        self.write_cfg({"legit": (cmd, True)})
        self.confirm("legit", cmd)

        self.quiet(osr.cmd_quick, argparse.Namespace(verify=cmd, allowed=None))

        self.assertIsNotNone(osr.Ledger().latest("quick_verify"))

    def test_unconfirmed_different_script_is_not_executed(self):
        marker = tempfile.TemporaryDirectory()
        self.addCleanup(marker.cleanup)
        marker_path = Path(marker.name) / "quick_attacker_ran.txt"
        self.write(
            "attacker.py",
            "from pathlib import Path\nPath(%r).write_text('ran', encoding='utf-8')\n" % str(marker_path),
        )
        self._project({"legit": (LEGIT_CMD, True)}, confirm=("legit",))

        with self.assertRaises(SystemExit) as caught:
            self.quiet(
                osr.cmd_quick,
                argparse.Namespace(verify=_script_cmd("attacker.py"), allowed=None),
            )

        self.assertNotEqual(caught.exception.code, 0)
        self.assertFalse(marker_path.exists(), "quick executed an unconfirmed command")
        self.assertNoQuickEvidence()

    def test_unconfirmed_shell_suffix_is_rejected(self):
        cmd = _script_cmd("legit.py")
        self.write("legit.py", "print('quick-ok')\n")
        self._project({"legit": (cmd, True)}, confirm=("legit",))

        with self.assertRaises(SystemExit) as caught:
            self.quiet(
                osr.cmd_quick,
                argparse.Namespace(verify=cmd + " && echo suffix-ran", allowed=None),
            )

        self.assertNotEqual(caught.exception.code, 0)
        self.assertNoQuickEvidence()

    def test_no_ledger_confirmation_is_rejected(self):
        cmd = _script_cmd("legit.py")
        self.write("legit.py", "print('quick-ok')\n")
        self._project({"legit": (cmd, True)})

        with self.assertRaises(SystemExit) as caught:
            self.quiet(osr.cmd_quick, argparse.Namespace(verify=cmd, allowed=None))

        self.assertNotEqual(caught.exception.code, 0)
        self.assertNoQuickEvidence()

    def test_trivial_command_is_rejected_even_if_confirmed(self):
        self._project({"trivial": ("echo ok", True)}, confirm=("trivial",))

        with self.assertRaises(SystemExit) as caught:
            self.quiet(osr.cmd_quick, argparse.Namespace(verify="echo ok", allowed=None))

        self.assertNotEqual(caught.exception.code, 0)
        self.assertNoQuickEvidence()

    def test_weak_command_is_rejected_even_if_confirmed(self):
        weak = '"%s" -c "import sys; print(\'grep\')"' % sys.executable
        self._project({"weak": (weak, True)}, confirm=("weak",))

        with self.assertRaises(SystemExit) as caught:
            self.quiet(osr.cmd_quick, argparse.Namespace(verify=weak, allowed=None))

        self.assertNotEqual(caught.exception.code, 0)
        self.assertNoQuickEvidence()

    def test_failed_reconfirmation_supersedes_prior_success(self):
        marker_dir = tempfile.TemporaryDirectory()
        self.addCleanup(marker_dir.cleanup)
        marker = Path(marker_dir.name) / "revoked_quick_ran.txt"
        cmd = _script_cmd("legit.py")
        self.write(
            "legit.py",
            "from pathlib import Path\nPath(%r).write_text('ran', encoding='utf-8')\nprint('quick-ok')\n" % str(marker),
        )
        self.write_cfg({"legit": (cmd, True)})
        self.confirm("legit", cmd, ok=True)
        self.approve_project()
        self.confirm("legit", cmd, ok=False)

        self.assertFalse(
            osr.is_verify_cmd_confirmed(cmd, osr.load_cfg(), osr.Ledger()),
            "the later failed reconfirmation did not revoke the earlier success",
        )
        with self.assertRaises(SystemExit) as caught:
            self.quiet(osr.cmd_quick, argparse.Namespace(verify=cmd, allowed=None))

        self.assertNotEqual(caught.exception.code, 0)
        self.assertFalse(marker.exists(), "quick executed a command whose reconfirmation failed")
        self.assertNoQuickEvidence()

    def test_broken_ledger_chain_is_rejected(self):
        cmd = _script_cmd("legit.py")
        self.write("legit.py", "print('quick-ok')\n")
        self._project({"legit": (cmd, True)}, confirm=("legit",))

        ledger_path = osr.ai("ledger.jsonl")
        entries = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        entries[0]["data"]["cmd"] = "tampered command"
        ledger_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")

        with self.assertRaises(SystemExit) as caught:
            self.quiet(osr.cmd_quick, argparse.Namespace(verify=cmd, allowed=None))

        self.assertEqual(caught.exception.code, osr.EXIT_INTEGRITY)

    def test_quick_does_not_create_task_completion_evidence(self):
        cmd = _script_cmd("legit.py")
        self.write("legit.py", "print('quick-ok')\n")
        self._project({"legit": (cmd, True)}, confirm=("legit",))

        self.quiet(osr.cmd_quick, argparse.Namespace(verify=cmd, allowed=None))

        state = osr.load_state()
        self.assertEqual(state["tasks"], {}, "quick wrote task completion state")
        types = [e["type"] for e in osr.Ledger().entries()]
        self.assertIn("quick_verify", types)
        self.assertNotIn("done", types)
        self.assertNotIn("review", types)
        self.assertNotIn("verify", types)


class TestStartVerifyAuthorization(_TempProjectCase):
    """R21: start baselines and verify execution honor the exact rule."""

    def _setup(self, card_verify):
        self.write("legit.py", "print('legit-ok')\n")
        self.write("app.py", "value = 1\n")
        self.write_cfg({"legit": (_script_cmd("legit.py"), True)})
        self.confirm("legit", _script_cmd("legit.py"))
        self.approve_project()
        self.write_card(verify=card_verify)

    def test_exact_confirmed_card_command_starts_and_verifies(self):
        self._setup(_script_cmd("legit.py"))

        self.quiet(osr.cmd_start, argparse.Namespace(task="T1", model="test-model"))
        with self.assertRaises(SystemExit) as caught:
            self.quiet(osr.cmd_verify, argparse.Namespace(task="T1"))

        self.assertEqual(caught.exception.code, 0)

    def test_unconfirmed_attack_command_is_never_executed(self):
        marker_dir = tempfile.TemporaryDirectory()
        self.addCleanup(marker_dir.cleanup)
        marker = Path(marker_dir.name) / "start_attacker_ran.txt"
        self.write(
            "attacker.py",
            "from pathlib import Path\nPath(%r).write_text('ran', encoding='utf-8')\n" % str(marker),
        )
        self._setup(_script_cmd("attacker.py"))

        with self.assertRaises(SystemExit) as caught:
            self.quiet(osr.cmd_start, argparse.Namespace(task="T1", model="test-model"))

        self.assertNotEqual(caught.exception.code, 0)
        self.assertFalse(marker.exists(), "start executed an unconfirmed card verify command")


class TestApprovalDrift(_TempProjectCase):
    """R21: an edited approved command needs confirmation and human reapproval.

    Confirming the edited command is not enough: the configuration no longer
    matches the human-approved config hash, so the real caller must refuse to
    execute until the project is genuinely reapproved.
    """

    def test_changed_command_needs_confirmation_and_reapproval(self):
        marker_dir = tempfile.TemporaryDirectory()
        self.addCleanup(marker_dir.cleanup)
        marker = Path(marker_dir.name) / "drift_ran.txt"

        legit_cmd = _script_cmd("legit.py")
        changed_cmd = _script_cmd("attacker.py")
        self.write("legit.py", "print('legit-ok')\n")
        self.write(
            "attacker.py",
            "from pathlib import Path\nPath(%r).write_text('ran', encoding='utf-8')\nprint('changed-ok')\n" % str(marker),
        )
        self.write("app.py", "value = 1\n")

        self.write_cfg({"legit": (legit_cmd, True)})
        self.confirm("legit", legit_cmd)
        self.approve_project()
        self.write_card(verify=legit_cmd)

        self.quiet(osr.cmd_start, argparse.Namespace(task="T1", model="test-model"))

        # The approved command is edited in config. Its old confirmation names a
        # command that is no longer configured, so it no longer authorizes either.
        self.write_cfg({"legit": (changed_cmd, True)})
        self.assertFalse(
            osr.is_verify_cmd_confirmed(legit_cmd, osr.load_cfg(), osr.Ledger()),
            "the replaced command kept its old confirmation",
        )
        self.assertFalse(
            osr.is_verify_cmd_confirmed(changed_cmd, osr.load_cfg(), osr.Ledger()),
            "the edited command was authorized without its own confirmation",
        )

        # Genuine reconfirmation of the new command succeeds at the authorization
        # layer, but the config approval is still stale.
        self.confirm("legit", changed_cmd)
        self.assertTrue(
            osr.is_verify_cmd_confirmed(changed_cmd, osr.load_cfg(), osr.Ledger()),
            "the reconfirmed exact command was rejected",
        )
        self.write_card(verify=changed_cmd)

        with self.assertRaises(SystemExit) as caught:
            self.quiet(osr.cmd_verify, argparse.Namespace(task="T1"))
        self.assertEqual(
            caught.exception.code,
            osr.EXIT_INTEGRITY,
            "verify ran a reconfirmed but un-reapproved config",
        )
        self.assertFalse(marker.exists(), "verify executed the edited command before reapproval")

        # Only genuine human reapproval binds the edited command and lets the
        # real caller execute it. An approval epoch cannot be established while
        # an attempt is active, so this temporary fixture performs the proper
        # retirement/reset -> reapproval -> new start sequence instead of
        # silently rebasing the existing attempt.
        self.quiet(osr.cmd_reset, argparse.Namespace(
            task="T1", by=["temp-human"], reason="config changed after start", secret=None))
        self.approve_project()
        self.quiet(osr.cmd_start, argparse.Namespace(task="T1", model="test-model"))
        if marker.exists():
            marker.unlink()
        self.assertFalse(marker.exists(), "the reapproval baseline recreated the marker")
        with self.assertRaises(SystemExit) as caught:
            self.quiet(osr.cmd_verify, argparse.Namespace(task="T1"))
        self.assertEqual(caught.exception.code, 0)
        self.assertTrue(marker.exists(), "the reapproved exact command did not execute")

    def _changed_approved_project(self):
        """Genuinely confirm, approve, edit and reconfirm inside a temp project.

        Returns the reconfirmed command and the marker file that the changed
        command writes when it actually runs. The confirmation-time marker is
        removed, so a later run proves execution rather than leftover evidence.
        """
        marker_dir = tempfile.TemporaryDirectory()
        self.addCleanup(marker_dir.cleanup)
        marker = Path(marker_dir.name) / "changed_ran.txt"

        legit_cmd = _script_cmd("legit.py")
        changed_cmd = _script_cmd("changed.py")
        self.write("legit.py", "print('legit-ok')\n")
        self.write(
            "changed.py",
            "from pathlib import Path\nPath(%r).write_text('ran', encoding='utf-8')\nprint('changed-ok')\n" % str(marker),
        )
        self.write_plan()
        self.write_cfg({"legit": (legit_cmd, True)})
        self.run_confirm()
        self.run_approve()

        # Edit the approved command and genuinely reconfirm it. Reconfirmation
        # establishes command identity only; it must not refresh approval.
        self.write_cfg({"legit": (changed_cmd, True)})
        self.run_confirm()
        if marker.exists():
            marker.unlink()
        self.assertFalse(marker.exists(), "the confirmation-time marker was not removed")
        self.assertNotEqual(
            osr.load_state().get("config_hash"),
            osr.sha_config(),
            "the changed config did not make the prior approval stale",
        )
        return changed_cmd, marker

    def assertNoFixtureEvidence(self, path):
        self.assertFalse((osr.ROOT / path).exists(), "a rejected fixture capture wrote its output file")
        self.assertIsNone(
            osr.Ledger().latest("fixture_capture"),
            "a rejected fixture capture still recorded capture evidence",
        )
        self.assertNotIn(path, osr.load_state().get("fixtures", {}))

    def test_quick_rejects_changed_approved_command_until_reapproval(self):
        changed_cmd, marker = self._changed_approved_project()

        with self.assertRaises(SystemExit) as caught:
            self.quiet(osr.cmd_quick, argparse.Namespace(verify=changed_cmd, allowed=None))

        self.assertEqual(caught.exception.code, osr.EXIT_INTEGRITY)
        self.assertFalse(marker.exists(), "quick executed the reconfirmed command before reapproval")
        self.assertIsNone(osr.Ledger().latest("quick_verify"))

        self.run_approve()
        self.quiet(osr.cmd_quick, argparse.Namespace(verify=changed_cmd, allowed=None))

        self.assertTrue(marker.exists(), "quick did not run the exact command after genuine reapproval")
        self.assertIsNotNone(osr.Ledger().latest("quick_verify"))

    def test_named_capture_rejects_changed_approved_command_until_reapproval(self):
        changed_cmd, marker = self._changed_approved_project()
        args = argparse.Namespace(path="fixtures/named.txt", seam="s1", cmd="legit")

        with self.assertRaises(SystemExit) as caught:
            self.quiet(osr.cmd_fixture_capture, args)

        self.assertEqual(caught.exception.code, osr.EXIT_INTEGRITY)
        self.assertFalse(marker.exists(), "named capture executed the reconfirmed command before reapproval")
        self.assertNoFixtureEvidence("fixtures/named.txt")

        self.run_approve()
        self.quiet(osr.cmd_fixture_capture, args)

        self.assertIn("changed-ok", (osr.ROOT / "fixtures/named.txt").read_text(encoding="utf-8"))
        self.assertTrue(marker.exists(), "named capture did not run the exact command after genuine reapproval")
        self.assertIsNotNone(osr.Ledger().latest("fixture_capture"))

    def test_raw_capture_rejects_changed_approved_command_until_reapproval(self):
        changed_cmd, marker = self._changed_approved_project()
        args = argparse.Namespace(path="fixtures/raw.txt", seam="s1", cmd=changed_cmd)

        with self.assertRaises(SystemExit) as caught:
            self.quiet(osr.cmd_fixture_capture, args)

        self.assertEqual(caught.exception.code, osr.EXIT_INTEGRITY)
        self.assertFalse(marker.exists(), "raw capture executed the reconfirmed command before reapproval")
        self.assertNoFixtureEvidence("fixtures/raw.txt")

        self.run_approve()
        self.quiet(osr.cmd_fixture_capture, args)

        self.assertIn("changed-ok", (osr.ROOT / "fixtures/raw.txt").read_text(encoding="utf-8"))
        self.assertTrue(marker.exists(), "raw capture did not run the exact command after genuine reapproval")
        self.assertIsNotNone(osr.Ledger().latest("fixture_capture"))


if __name__ == "__main__":
    unittest.main()
