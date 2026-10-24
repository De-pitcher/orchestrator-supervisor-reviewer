import argparse
import json
import subprocess
from pathlib import Path

repo = 'De-pitcher/orchestrator-supervisor-reviewer'
root = Path(__file__).resolve().parent.parent
out = root / '.ai/reviews/repository-governance'
out.mkdir(parents=True, exist_ok=True)

def api(path, method='GET', payload=None):
    args = ['gh', 'api', 'repos/' + repo + '/' + path, '--method', method]
    if payload is not None:
        body = out / 'protection-request.json'
        body.write_text(json.dumps(payload, indent=2) + '\n')
        args += ['--input', str(body)]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout) if result.stdout.strip() else None

parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true')
parser.add_argument('--stable-gate', action='store_true')
args = parser.parse_args()
contexts = ['ci-required'] if args.stable_gate else [
    'test (%s, %s)' % (os_name, python)
    for os_name in ['ubuntu-latest', 'macos-latest', 'windows-latest']
    for python in ['3.8', '3.9', '3.10', '3.11', '3.12']
]
payload = {
    'required_status_checks': {'strict': True, 'checks': [
        {'context': context, 'app_id': 15368} for context in contexts]},
    'enforce_admins': True,
    'required_pull_request_reviews': {
        'dismiss_stale_reviews': True, 'require_code_owner_reviews': False,
        'required_approving_review_count': 0, 'require_last_push_approval': False},
    'restrictions': None, 'required_linear_history': False,
    'allow_force_pushes': False, 'allow_deletions': False,
    'required_conversation_resolution': True,
}
if args.apply:
    if args.stable_gate:
        checks = api('commits/dev/check-runs')['check_runs']
        stable = [check for check in checks if check['name'] == 'ci-required']
        assert stable and all(check['conclusion'] == 'success' and check['app']['id'] == 15368
                              for check in stable), 'Stable gate must pass before protection changes'
    protection = api('branches/main/protection', 'PUT', payload)
    api('private-vulnerability-reporting', 'PUT')
else:
    protection = api('branches/main/protection')
security = api('private-vulnerability-reporting')
assert protection['required_status_checks']['strict']
assert protection['enforce_admins']['enabled']
assert not protection['allow_force_pushes']['enabled']
assert not protection['allow_deletions']['enabled']
assert protection['required_conversation_resolution']['enabled']
assert protection['required_pull_request_reviews']['required_approving_review_count'] == 0
assert {c['context'] for c in protection['required_status_checks']['checks']} == set(contexts)
assert all(c['app_id'] == 15368 for c in protection['required_status_checks']['checks'])
assert security['enabled']
record = {'repository': repo, 'protection': protection, 'private_vulnerability_reporting': security}
name = 'stable-gate' if args.stable_gate else 'matrix-gates'
(out / (name + '.json')).write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({'protected': True, 'admin_enforcement': True, 'strict_status_checks': len(contexts),
                  'pull_request_required': True, 'mandatory_approvals': 0,
                  'force_pushes': False, 'branch_deletion': False,
                  'conversations_must_be_resolved': True, 'private_vulnerability_reporting': True}))
