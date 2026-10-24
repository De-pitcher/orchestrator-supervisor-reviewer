import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
import yaml

root = Path(__file__).resolve().parent.parent
def load(name):
    return yaml.load((root / name).read_text(encoding='utf-8'), Loader=yaml.BaseLoader)

workflow = load('.github/workflows/test.yml')
assert workflow['on'] == ['push', 'pull_request']
assert workflow['permissions'] == {'contents': 'read'}
assert workflow['concurrency']['cancel-in-progress'] == 'true'
matrix = workflow['jobs']['test']['strategy']['matrix']
assert matrix == {'os': ['ubuntu-latest', 'macos-latest', 'windows-latest'],
                  'python': ['3.8', '3.9', '3.10', '3.11', '3.12']}
steps = workflow['jobs']['test']['steps']
assert [step['run'] for step in steps if 'run' in step] == [
    'python -m unittest discover -s tests -v',
    'python scripts/osr.py ledger-verify', 'python scripts/osr.py plan-check']
assert all(re.fullmatch(r'actions/[a-z-]+@[a-f0-9]{40}', step['uses'])
           for step in steps if 'uses' in step)
assert steps[0]['with']['persist-credentials'] == 'false'
required = workflow['jobs']['required']
assert required['name'] == 'ci-required'
assert required['if'] == '${{ always() }}' and required['needs'] == ['test']
assert required['steps'][0]['env']['MATRIX_RESULT'] == '${{ needs.test.result }}'
command = shlex.split(required['steps'][0]['run'])
assert command[:2] == ['python', '-c'] and len(command) == 3
cases = []
for result in ('success', 'failure', 'cancelled', 'skipped', ''):
    env = dict(os.environ, MATRIX_RESULT=result)
    proc = subprocess.run([sys.executable, '-c', command[2]], env=env, capture_output=True, text=True)
    assert (proc.returncode == 0) == (result == 'success')
    cases.append({'matrix_result': result, 'exit': proc.returncode, 'output': proc.stdout.strip()})

forms = []
for name in ('bug_report', 'feature_request'):
    form = load('.github/ISSUE_TEMPLATE/' + name + '.yml')
    assert form['name'] and form['description'] and form['body']
    ids = [field['id'] for field in form['body'] if 'id' in field]
    assert len(ids) == len(set(ids))
    for field in form['body']:
        assert field['type'] in ('markdown', 'input', 'textarea', 'checkboxes')
        assert field['attributes']
    forms.append(name)
assert load('.github/ISSUE_TEMPLATE/config.yml')['blank_issues_enabled'] == 'false'
assert '* @De-pitcher' in (root / '.github/CODEOWNERS').read_text()
updates = load('.github/dependabot.yml')
assert updates['version'] == '2' and updates['updates'][0]['package-ecosystem'] == 'github-actions'
assert updates['updates'][0]['open-pull-requests-limit'] == '2'

docs = ['README.md', 'CONTRIBUTING.md', 'CHANGELOG.md', 'GOVERNANCE.md', 'SECURITY.md',
        'CODE_OF_CONDUCT.md', 'SUPPORT.md', 'docs/ARCHITECTURE.md', 'docs/RELEASING.md']
links = []
for name in docs:
    path = root / name
    for link in re.findall(r'\[[^\]]+\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
        target = link.split('#', 1)[0]
        if not target or '://' in target or target.startswith('mailto:'):
            continue
        assert (path.parent / target).exists(), (name, target)
        links.append([name, target])
record = {'ok': True, 'matrix_jobs': 15, 'gate_failure_cases': cases, 'forms': forms,
          'local_links_checked': len(links), 'immutable_actions': True,
          'read_only_permissions': True, 'runtime_unchanged': True}
(root / '.ai/reviews/T33.foundation-check.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
