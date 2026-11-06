"""Regression tests for production dispatch scope and repeatable read-only audits."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PINNED_ACTIONS = {
    'actions/checkout': '3d3c42e5aac5ba805825da76410c181273ba90b1',
    'actions/setup-python': '6d4fd22b20465ccc0f7354476588e8df7c9ca0e0',
    'actions/upload-pages-artifact': 'fc324d3547104276b827a68afc52ff2a11cc49c9',
    'actions/deploy-pages': '368f82528645a54fb793d4d04e342629a3f51346',
}


def workflow(name):
    # BaseLoader follows GitHub's literal "on" key without YAML 1.1 boolean coercion.
    return yaml.load((ROOT / '.github/workflows' / name).read_text(), Loader=yaml.BaseLoader)


class WorkflowSafetyTests(unittest.TestCase):
    def test_production_jobs_only_run_on_main(self):
        doc = workflow('publish.yml')
        self.assertEqual(doc['on']['push']['branches'], ['main'])
        for name in ('publish', 'deploy'):
            condition = doc['jobs'][name]['if']
            self.assertIn("github.ref == 'refs/heads/main'", condition)
            self.assertIn("github.event_name != 'pull_request'", condition)
        self.assertEqual(doc['jobs']['review']['permissions'], {'contents': 'read'})

    def test_one_non_cancelling_production_deployment(self):
        job = workflow('publish.yml')['jobs']['deploy']
        self.assertEqual(job['needs'], 'publish')
        self.assertEqual(job['concurrency'], {'group': 'eternal-cycle-pages-production', 'cancel-in-progress': 'false'})
        self.assertEqual(job['permissions'], {'pages': 'write', 'id-token': 'write'})
        self.assertEqual(job['environment']['name'], 'github-pages')

    def test_epub_audit_never_repeats_a_completed_repair_or_writes_books(self):
        doc = workflow('audit-public-epubs.yml')
        self.assertEqual(doc['permissions'], {'contents': 'read'})
        job = doc['jobs']['epub-audit']
        self.assertNotIn('permissions', job)
        scripts = '\n'.join(step.get('run', '') for step in job['steps'])
        self.assertIn('python scripts/build_catalog.py --check', scripts)
        self.assertIn('python scripts/audit_epub_contents.py', scripts)
        self.assertNotIn('repair_fishing_epub_links.py', scripts)
        self.assertNotIn('git push', scripts)
        self.assertNotIn('git commit', scripts)
        self.assertNotRegex(scripts, r'build_catalog\.py\s*\n')
        checkout = next(step for step in job['steps'] if step.get('uses', '').startswith('actions/checkout@'))
        self.assertEqual(checkout['with']['persist-credentials'], 'false')

    def test_hidden_public_marker_still_uploaded(self):
        job = workflow('publish.yml')['jobs']['publish']
        step = next(step for step in job['steps'] if step.get('uses', '').startswith('actions/upload-pages-artifact@'))
        self.assertEqual(step['with'], {'path': '_site', 'include-hidden-files': 'true'})

    def test_every_external_action_has_the_reviewed_node24_pin(self):
        seen = set()
        for file in (ROOT / '.github/workflows').glob('*.yml'):
            for job in workflow(file.name)['jobs'].values():
                for step in job['steps']:
                    if 'uses' not in step:
                        continue
                    action, sha = step['uses'].split('@')
                    self.assertRegex(sha, r'^[0-9a-f]{40}$')
                    self.assertEqual(sha, PINNED_ACTIONS[action])
                    self.assertNotIn('allow-unsafe-pr-checkout', step.get('with', {}))
                    seen.add(action)
        self.assertEqual(seen, set(PINNED_ACTIONS))

    def test_branch_writer_is_serial_and_scoped(self):
        doc = workflow('build-unconscious.yml')
        self.assertEqual(doc['concurrency']['cancel-in-progress'], 'false')
        self.assertIn('github.ref', doc['concurrency']['group'])
        self.assertIn("github.ref == 'refs/heads/publish-unconscious-programming'", doc['jobs']['build']['if'])
        self.assertNotIn('workflow_dispatch', doc['on'])

    def test_unchanged_book_build_succeeds_without_commit_or_push(self):
        steps = workflow('build-unconscious.yml')['jobs']['build']['steps']
        script = next(step['run'] for step in steps if step.get('name', '').startswith('Commit approved'))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fake_git = root / 'git'
            fake_git.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$GIT_TEST_LOG"\n'
                                'if [ "$1" = diff ]; then exit "$GIT_DIFF_STATUS"; fi\nexit 0\n')
            fake_git.chmod(0o755)
            for changed in (False, True):
                log = root / ('changed' if changed else 'unchanged')
                env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'],
                       'GIT_TEST_LOG': str(log), 'GIT_DIFF_STATUS': '1' if changed else '0',
                       'GITHUB_REF_NAME': 'publish-unconscious-programming'}
                result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', script], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = log.read_text().splitlines()
                self.assertEqual(any(line.startswith('commit ') for line in lines), changed)
                self.assertEqual(any(line.startswith('push ') for line in lines), changed)

    def test_all_workflow_shell_blocks_parse(self):
        for file in (ROOT / '.github/workflows').glob('*.yml'):
            for job in workflow(file.name)['jobs'].values():
                for step in job['steps']:
                    if 'run' in step:
                        result = subprocess.run(['bash', '-n'], input=step['run'], text=True, capture_output=True)
                        self.assertEqual(result.returncode, 0, file.name + ': ' + result.stderr)

    def test_no_unsupported_deployment_sha_or_timeout_override(self):
        steps = workflow('publish.yml')['jobs']['deploy']['steps']
        step = next(step for step in steps if step.get('uses', '').startswith('actions/deploy-pages@'))
        self.assertNotIn('with', step)
        self.assertNotIn('env', step)


if __name__ == '__main__':
    unittest.main()
