#!/usr/bin/env python3
import importlib.util
import json
import os
import pathlib
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


if __name__ == '__main__':
    unittest.main()
