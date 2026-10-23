import collections
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location('evidence_runner', root / '.ai/t27_supervisor_runner.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
folder = root / '.ai/reviews' / sys.argv[1]
summary = json.loads((folder / 'run-summary.json').read_text())
ids = []
for item in summary['batches'] + [summary['formal']]:
    raw = (root / item['log']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == item['log_sha256'], item['id']
    assert item['exit'] == 0 and item['tree_unchanged'] and item['ok'], item['id']
    assert item['tree_digest_before'] == item['tree_digest_after'] == summary['freeze_digest']
    if item['id'] == 'FORMAL':
        observed = []
        for entry in item['formal_logs']:
            raw = (root / entry['path']).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == entry['sha256']
            observed.extend(runner.parse_ids(raw.decode('utf-8', 'replace')))
    else:
        observed = runner.parse_ids(raw.decode('utf-8', 'replace'))
    assert observed == item['observed_ids'], item['id']
    ids.extend(observed)
inventory = json.loads((root / '.ai/reviews/T27.inventory-before.json').read_text())['ids']
assert len(ids) == len(set(ids)) == 249
assert set(ids) == set(inventory)
def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item.id()
discovered = list(flatten(unittest.defaultTestLoader.discover(str(root / 'tests'))))
assert len(discovered) == 249 and set(discovered) == set(ids)
report = json.loads((folder / 'S4.benchmark-report.json').read_text())
assert report['cheats_caught'] == report['total_cheats_tested'] == 12
assert report['clean_runs_tested'] == 11 and report['false_positives'] == 0
assert hashlib.sha256((folder / 'S4.benchmark-report.json').read_bytes()).hexdigest() == summary['benchmark_report']['sha256']
entries = [json.loads(line) for line in (root / '.ai/ledger.jsonl').read_text().splitlines() if line.strip()]
expected_logs = {Path(entry['path']).name: entry['sha256'] for entry in summary['formal']['formal_logs']}
matching = []
for entry in entries:
    if entry['type'] != 'verify' or entry.get('task') != 'T27' or not entry['data'].get('ok'):
        continue
    results = entry['data'].get('results', [])
    actual = {item['log']: item['output_sha'] for item in results}
    if actual == expected_logs:
        assert all(item['exit'] == 0 and item['ok'] for item in results)
        matching.append(entry['seq'])
assert len(matching) == 1, matching
result = {'ok': True, 'ids': len(ids), 'unique_ids': len(set(ids)), 'loader_inventory_matches': True,
          'freeze_digest': summary['freeze_digest'], 'all_log_hashes_match': True,
          'formal_verify_seq': matching[0],
          'benchmark': {'caught': 12, 'canaries': 11, 'false_positives': 0}}
(folder / 'independent-audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
