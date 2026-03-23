#!/usr/bin/env python3
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / 'kernel' / 'audit.py'


def _load_audit_module(module_name):
    spec = importlib.util.spec_from_file_location(module_name, AUDIT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AuditEnvOverrideTests(unittest.TestCase):
    def test_meridian_audit_file_env_redirects_log_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            preview_path = pathlib.Path(tmpdir) / 'audit-preview.jsonl'
            os.environ['MERIDIAN_AUDIT_FILE'] = str(preview_path)
            try:
                audit = _load_audit_module('kernel_audit_env_override_test')
                event_id = audit.log_event(
                    'org_demo',
                    'agent_atlas',
                    'shadow_preview',
                    resource='web_search',
                    outcome='simulated_success',
                    details={'source': 'unit_test'},
                    policy_ref='experimental_preflight_preview',
                )
            finally:
                os.environ.pop('MERIDIAN_AUDIT_FILE', None)

            self.assertTrue(preview_path.exists())
            rows = preview_path.read_text().strip().splitlines()
            self.assertEqual(len(rows), 1)
            event = json.loads(rows[0])
            self.assertEqual(event['id'], event_id)
            self.assertEqual(event['org_id'], 'org_demo')
            self.assertEqual(event['agent_id'], 'agent_atlas')
            self.assertEqual(event['action'], 'shadow_preview')
            self.assertEqual(event['outcome'], 'simulated_success')
            self.assertEqual(event['policy_ref'], 'experimental_preflight_preview')

    def test_log_runtime_cli_respects_env_override_and_shapes_details(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_path = pathlib.Path(tmpdir) / 'audit-runtime.jsonl'
            env = os.environ.copy()
            env['MERIDIAN_AUDIT_FILE'] = str(runtime_path)
            subprocess.run(
                [
                    sys.executable,
                    str(AUDIT_PATH),
                    'log-runtime',
                    '--org_id', 'org_demo',
                    '--agent_id', 'agent_atlas',
                    '--action', 'research',
                    '--resource', 'web_search',
                    '--outcome', 'success',
                    '--input_hash', 'abc123',
                    '--estimated_cost_usd', '0.05',
                    '--effective_source', 'worker_supervisor',
                    '--effective_stage', 'governed_local_worker',
                    '--reference_stage', 'ok',
                    '--runtime_outcome', 'worker_executed',
                    '--worker_status', 'completed',
                    '--worker_kind', 'python_reference_worker',
                    '--parity_status', 'match',
                    '--session_id', 'sess_demo',
                ],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertTrue(runtime_path.exists())
            rows = runtime_path.read_text().strip().splitlines()
            self.assertEqual(len(rows), 1)
            event = json.loads(rows[0])
            self.assertEqual(event['org_id'], 'org_demo')
            self.assertEqual(event['agent_id'], 'agent_atlas')
            self.assertEqual(event['action'], 'research')
            self.assertEqual(event['resource'], 'web_search')
            self.assertEqual(event['outcome'], 'success')
            self.assertEqual(event['policy_ref'], 'experimental_runtime_rehearsal')
            self.assertEqual(event['session_id'], 'sess_demo')
            self.assertEqual(event['details']['source'], 'loom_runtime_execute')
            self.assertEqual(event['details']['runtime_outcome'], 'worker_executed')
            self.assertEqual(event['details']['worker_status'], 'completed')
            self.assertEqual(event['details']['worker_kind'], 'python_reference_worker')
            self.assertEqual(event['details']['parity_status'], 'match')

    def test_log_runtime_cli_defaults_to_kernel_runtime_audit_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            kernel_dir = root / 'kernel'
            kernel_dir.mkdir()
            audit_copy = kernel_dir / 'audit.py'
            audit_copy.write_text(AUDIT_PATH.read_text())
            expected = kernel_dir / 'runtime_audit' / 'loom_runtime_events.jsonl'
            env = os.environ.copy()
            env.pop('MERIDIAN_AUDIT_FILE', None)
            env.pop('MERIDIAN_RUNTIME_AUDIT_FILE', None)
            subprocess.run(
                [
                    sys.executable,
                    str(audit_copy),
                    'log-runtime',
                    '--org_id', 'org_demo',
                    '--agent_id', 'agent_atlas',
                    '--action', 'research',
                    '--resource', 'web_search',
                    '--outcome', 'success',
                    '--input_hash', 'def456',
                    '--estimated_cost_usd', '0.05',
                    '--effective_source', 'reference_gate',
                    '--effective_stage', 'ok',
                    '--reference_stage', 'ok',
                    '--runtime_outcome', 'worker_executed',
                    '--worker_status', 'completed',
                    '--worker_kind', 'python_reference_worker',
                    '--parity_status', 'match',
                ],
                cwd=root,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertTrue(expected.exists())
            rows = expected.read_text().strip().splitlines()
            self.assertEqual(len(rows), 1)
            event = json.loads(rows[0])
            self.assertEqual(event['org_id'], 'org_demo')
            self.assertEqual(event['details']['source'], 'loom_runtime_execute')


if __name__ == '__main__':
    unittest.main()
