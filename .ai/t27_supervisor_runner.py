"""T27 corrected final evidence runner (builder-side tool under ignored .ai/).

Runs the approved S1-S8 supplementary batches plus one formal `osr verify T27`
on a frozen governed tree, recording the ACTUAL argv, working directory,
import paths, per-batch digests and log hashes. The S4 batch is delegated to
.ai/t27_s4_runner.py which captures the real benchmark report in-process.

Usage (sequential, one batch at a time):
  python .ai/t27_evidence_runner.py freeze
  python .ai/t27_evidence_runner.py batch S1
  ...
  python .ai/t27_evidence_runner.py summary
  python .ai/t27_evidence_runner.py pack --out <path>
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVIDENCE = Path(os.environ.get(
    "T27_EVIDENCE_DIR",
    str(REPO / ".ai" / "reviews" / "T27.final-evidence.supervisor"),
))
SCHEDULE = REPO / ".ai" / "reviews" / "T27.schedule.json"
INVENTORY = REPO / ".ai" / "reviews" / "T27.inventory-before.json"
S4_RUNNER = ".ai/t27_s4_runner.py"
FORMAL_LOG_RE = re.compile(r"log (\.ai/logs/\S+?\.log)")
ID_LINE_RE = re.compile(r"^(\w+) \(([A-Za-z0-9_.]+)\)")
STATUS_RE = re.compile(r"\.\.\. (ok|FAIL|ERROR|skipped|expected failure|unexpected success)")


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_schedule():
    return json.loads(SCHEDULE.read_text(encoding="utf-8"))


def tree_digest():
    os.chdir(str(REPO))
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import scripts.osr as osr

    cfg, _st, _led = osr.ctx()
    return osr.manifest_digest(osr.manifest_from_tree(osr.walk_tree(cfg)))


def parse_ids(text):
    observed = []
    pending = None
    for line in text.splitlines():
        m = ID_LINE_RE.match(line)
        if m:
            tid = m.group(2)
            if STATUS_RE.search(line):
                observed.append(tid)
                pending = None
            else:
                pending = tid
            continue
        if pending and STATUS_RE.search(line):
            observed.append(pending)
            pending = None
    return observed


def run_batch(batch):
    bid = batch["id"]
    before = tree_digest()
    started = time.time()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO), str(REPO / "tests")])
    if bid == "S4":
        argv = [sys.executable, S4_RUNNER]
        cwd = str(REPO)
        pythonpath = env["PYTHONPATH"]
    else:
        argv = [sys.executable] + [
            a for a in batch["argv"][1:]
        ]
        cwd = batch["cwd"]
        pythonpath = batch.get("pythonpath") or env["PYTHONPATH"]
    proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=True)
    elapsed = round(time.time() - started, 3)
    raw = proc.stdout + proc.stderr
    text = raw.decode("utf-8", "replace")
    log_path = EVIDENCE / ("%s.log" % bid)
    log_path.write_bytes(raw)
    after = tree_digest()

    observed = parse_ids(text)
    scheduled = batch["test_ids"]
    missing = [t for t in scheduled if t not in observed]
    extra = [t for t in observed if t not in scheduled]
    record = {
        "id": bid,
        "kind": batch["kind"],
        "scheduled_count": batch["count"],
        "observed_count": len(observed),
        "observed_ids": observed,
        "missing_ids": missing,
        "unexpected_ids": extra,
        "argv": argv,
        "cwd": cwd,
        "pythonpath": pythonpath,
        "exit": proc.returncode,
        "elapsed_seconds": elapsed,
        "tree_digest_before": before,
        "tree_digest_after": after,
        "tree_unchanged": before == after,
        "log": ".ai/reviews/T27.final-evidence.supervisor/%s.log" % bid,
        "log_sha256": hashlib.sha256(raw).hexdigest(),
        "ok": proc.returncode == 0 and not missing and not extra and before == after,
    }
    if bid == "S4":
        meta_path = EVIDENCE / "S4.runner.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        record["runner_meta"] = meta
        record["benchmark_report_file"] = meta["benchmark_report_file"]
        record["benchmark_report_sha256"] = meta["benchmark_report_sha256"]
        record["benchmark_report_invocations"] = meta["benchmark_report_invocations"]
        record["ok"] = record["ok"] and bool(meta.get("ok"))
    (EVIDENCE / ("%s.json" % bid)).write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("%s: exit=%d observed=%d/%d missing=%d unexpected=%d tree_unchanged=%s ok=%s" % (
        bid, proc.returncode, len(observed), batch["count"], len(missing), len(extra),
        before == after, record["ok"]))
    if not record["ok"]:
        print(text[-4000:])
    return record


def run_formal(batch):
    before = tree_digest()
    started = time.time()
    argv = list(batch["argv"])
    proc = subprocess.run(argv, cwd=batch["cwd"], capture_output=True)
    elapsed = round(time.time() - started, 3)
    raw = proc.stdout + proc.stderr
    text = raw.decode("utf-8", "replace")
    log_path = EVIDENCE / "FORMAL.log"
    log_path.write_bytes(raw)
    after = tree_digest()

    logs = []
    seen = set()
    for rel in FORMAL_LOG_RE.findall(text):
        if rel in seen:
            continue
        seen.add(rel)
        p = REPO / rel
        if not p.exists():
            logs.append({"path": rel, "exists": False, "observed_count": 0, "observed_ids": []})
            continue
        content = p.read_bytes()
        ids = parse_ids(content.decode("utf-8", "replace"))
        logs.append({
            "path": rel,
            "exists": True,
            "sha256": hashlib.sha256(content).hexdigest(),
            "observed_count": len(ids),
            "observed_ids": ids,
        })
    observed = []
    for entry in logs:
        observed.extend(entry.get("observed_ids", []))
    missing = [t for t in batch["test_ids"] if t not in observed]
    extra = [t for t in observed if t not in batch["test_ids"]]
    record = {
        "id": "FORMAL",
        "kind": batch["kind"],
        "scheduled_count": batch["count"],
        "observed_count": len(observed),
        "observed_ids": observed,
        "missing_ids": missing,
        "unexpected_ids": extra,
        "duplicate_ids": sorted({t for t in observed if observed.count(t) > 1}),
        "argv": argv,
        "cwd": batch["cwd"],
        "exit": proc.returncode,
        "elapsed_seconds": elapsed,
        "tree_digest_before": before,
        "tree_digest_after": after,
        "tree_unchanged": before == after,
        "log": ".ai/reviews/T27.final-evidence.supervisor/FORMAL.log",
        "log_sha256": hashlib.sha256(raw).hexdigest(),
        "formal_logs": logs,
        "ok": proc.returncode == 0 and not missing and not extra and before == after,
    }
    (EVIDENCE / "FORMAL.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("FORMAL: exit=%d observed=%d/%d missing=%d unexpected=%d logs=%d tree_unchanged=%s ok=%s" % (
        proc.returncode, len(observed), batch["count"], len(missing), len(extra),
        len(logs), before == after, record["ok"]))
    if not record["ok"]:
        print(text[-4000:])
    return record


def freeze():
    digest = tree_digest()
    os.chdir(str(REPO))
    import scripts.osr as osr

    cfg, _st, _led = osr.ctx()
    manifest = osr.manifest_from_tree(osr.walk_tree(cfg))
    payload = {
        "schema": "osr.t27.freeze.v1",
        "freeze_digest": digest,
        "governed_file_count": len(manifest),
        "ignore_sha": osr.ignore_digest(cfg),
        "schedule": ".ai/reviews/T27.schedule.json",
        "evidence_dir": ".ai/reviews/T27.final-evidence.supervisor",
        "note": "Computed after all T27 corrections were written; every batch must keep this digest.",
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "freeze.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (EVIDENCE / "freeze.manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("freeze: %s (%d governed files)" % (digest, len(manifest)))
    return payload


def summary():
    freeze_data = json.loads((EVIDENCE / "freeze.json").read_text(encoding="utf-8"))
    schedule = load_schedule()
    records = []
    for batch in schedule["batches"]:
        if batch["id"] == "FORMAL":
            continue
        records.append(json.loads((EVIDENCE / ("%s.json" % batch["id"])).read_text(encoding="utf-8")))
    formal = json.loads((EVIDENCE / "FORMAL.json").read_text(encoding="utf-8"))
    supplementary = []
    for rec in records:
        supplementary.extend(rec["observed_ids"])
    formal_ids = formal["observed_ids"]
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))["ids"]
    union = set(supplementary) | set(formal_ids)
    overlap = sorted(set(supplementary) & set(formal_ids))
    s4 = next(r for r in records if r["id"] == "S4")
    payload = {
        "schema": "osr.t27.final-evidence.v3",
        "freeze_digest": freeze_data["freeze_digest"],
        "governed_file_count": freeze_data["governed_file_count"],
        "schedule": freeze_data["schedule"],
        "inventory": ".ai/reviews/T27.inventory-before.json",
        "inventory_count": len(inventory),
        "counts": {
            "supplementary": len(supplementary),
            "formal": len(formal_ids),
            "total": len(union),
        },
        "supplementary_formal_overlap": overlap,
        "disjoint_supplementary_ids": not overlap,
        "union_matches_inventory": union == set(inventory),
        "missing_from_union": sorted(set(inventory) - union),
        "unexpected_in_union": sorted(union - set(inventory)),
        "batches": records,
        "formal": formal,
        "benchmark_report": {
            "file": s4.get("benchmark_report_file"),
            "sha256": s4.get("benchmark_report_sha256"),
            "invocations": s4.get("benchmark_report_invocations"),
        },
        "all_tree_unchanged": all(r["tree_unchanged"] for r in records) and formal["tree_unchanged"],
        "all_batches_ok": all(r["ok"] for r in records) and formal["ok"],
    }
    payload["ok"] = (
        payload["all_tree_unchanged"]
        and payload["all_batches_ok"]
        and payload["counts"]["total"] == 249
        and payload["union_matches_inventory"]
        and payload["disjoint_supplementary_ids"]
    )
    (EVIDENCE / "run-summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("summary: %s" % json.dumps({
        "freeze_digest": payload["freeze_digest"],
        "counts": payload["counts"],
        "union_matches_inventory": payload["union_matches_inventory"],
        "all_tree_unchanged": payload["all_tree_unchanged"],
        "ok": payload["ok"],
    }, sort_keys=True))
    return payload


def pack(out):
    before = tree_digest()
    started = time.time()
    argv = [sys.executable, "scripts/osr.py", "review-pack", "T27", "--out", out]
    proc = subprocess.run(argv, cwd=str(REPO), capture_output=True)
    elapsed = round(time.time() - started, 3)
    raw = proc.stdout + proc.stderr
    (EVIDENCE / "REVIEW-PACK.log").write_bytes(raw)
    after = tree_digest()
    out_path = Path(out)
    if not out_path.is_absolute():
        out_path = REPO / out_path
    record = {
        "argv": argv,
        "exit": proc.returncode,
        "elapsed_seconds": elapsed,
        "tree_digest_before": before,
        "tree_digest_after": after,
        "tree_unchanged": before == after,
        "log": ".ai/reviews/T27.final-evidence.supervisor/REVIEW-PACK.log",
        "log_sha256": hashlib.sha256(raw).hexdigest(),
        "pack_file": out,
        "pack_exists": out_path.exists(),
        "pack_sha256": sha_file(out_path) if out_path.exists() else None,
    }
    (EVIDENCE / "REVIEW-PACK.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("pack: exit=%d exists=%s tree_unchanged=%s sha256=%s" % (
        proc.returncode, record["pack_exists"], record["tree_unchanged"], record["pack_sha256"]))
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["freeze", "batch", "formal", "summary", "pack"])
    ap.add_argument("value", nargs="?")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    os.chdir(str(REPO))
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    schedule = load_schedule()
    by_id = {b["id"]: b for b in schedule["batches"]}
    if args.action == "freeze":
        freeze()
        return
    if args.action == "batch":
        run_batch(by_id[args.value])
        return
    if args.action == "formal":
        run_formal(by_id["FORMAL"])
        return
    if args.action == "summary":
        payload = summary()
        sys.exit(0 if payload["ok"] else 1)
    if args.action == "pack":
        if not args.out:
            raise SystemExit("pack requires --out <path>")
        record = pack(args.out)
        sys.exit(0 if record["exit"] == 0 and record["pack_exists"] and record["tree_unchanged"] else 1)


if __name__ == "__main__":
    main()
