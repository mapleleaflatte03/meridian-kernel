#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / 'kernel' / 'agent_registry.py'


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent_registry = _load_module('kernel_agent_registry_test', MODULE_PATH)


class AgentRegistryLookupTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.registry_file = pathlib.Path(self.tmpdir.name) / 'agent_registry.json'
        self.registry_file.write_text(json.dumps({
            'agents': {
                'agent_atlas_a': {
                    'id': 'agent_atlas_a',
                    'org_id': 'org_a',
                    'name': 'Atlas',
                    'economy_key': 'atlas',
                    'rollout_state': 'active',
                    'reputation_units': 100,
                    'authority_units': 100,
                    'last_active_at': '2026-03-21T00:00:00Z',
                    'risk_state': 'nominal',
                    'budget': {'max_per_run_usd': 1.0},
                    'scopes': ['execute'],
                },
                'agent_atlas_b': {
                    'id': 'agent_atlas_b',
                    'org_id': 'org_b',
                    'name': 'Atlas',
                    'economy_key': 'atlas',
                    'rollout_state': 'active',
                    'reputation_units': 100,
                    'authority_units': 100,
                    'last_active_at': '2026-03-21T00:00:00Z',
                    'risk_state': 'nominal',
                    'budget': {'max_per_run_usd': 2.0},
                    'scopes': ['review'],
                },
                'agent_quill_a': {
                    'id': 'agent_quill_a',
                    'org_id': 'org_a',
                    'name': 'Quill',
                    'economy_key': 'quill',
                    'rollout_state': 'quarantined',
                    'reputation_units': 100,
                    'authority_units': 100,
                    'last_active_at': '2026-03-21T00:00:00Z',
                    'risk_state': 'nominal',
                    'budget': {'max_per_run_usd': 1.0},
                    'scopes': ['write'],
                },
            },
            'updatedAt': '2026-03-21T00:00:00Z',
        }, indent=2))

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_unscoped_economy_key_lookup_is_none_when_ambiguous(self):
        with mock.patch.object(agent_registry, 'REGISTRY_FILE', str(self.registry_file)):
            self.assertIsNone(agent_registry.get_agent_by_economy_key('atlas'))
            self.assertIsNone(agent_registry.resolve_agent('atlas'))

    def test_org_scoped_economy_key_lookup_returns_correct_agent(self):
        with mock.patch.object(agent_registry, 'REGISTRY_FILE', str(self.registry_file)):
            agent = agent_registry.get_agent_by_economy_key('atlas', org_id='org_b')
            self.assertEqual(agent['id'], 'agent_atlas_b')

            resolved = agent_registry.resolve_agent('atlas', org_id='org_a')
            self.assertEqual(resolved['id'], 'agent_atlas_a')

    def test_check_budget_and_scope_use_resolved_agent(self):
        with mock.patch.object(agent_registry, 'REGISTRY_FILE', str(self.registry_file)):
            allowed, reason = agent_registry.check_budget('agent_atlas_a', 0.5)
            self.assertTrue(allowed, reason)

            allowed, reason = agent_registry.check_scope('atlas', 'execute')
            self.assertFalse(allowed)
            self.assertEqual(reason, 'Agent not found')

            allowed, reason = agent_registry.check_scope('agent_atlas_a', 'execute')
            self.assertTrue(allowed, reason)

    def test_sync_from_economy_only_updates_scoped_org(self):
        ledger_file = pathlib.Path(self.tmpdir.name) / 'ledger.json'
        ledger_file.write_text(json.dumps({
            'agents': {
                'atlas': {
                    'name': 'Atlas',
                    'reputation_units': 77,
                    'authority_units': 66,
                    'last_scored_at': '2026-03-21T01:00:00Z',
                    'probation': False,
                    'zero_authority': False,
                }
            }
        }, indent=2))

        with mock.patch.object(agent_registry, 'REGISTRY_FILE', str(self.registry_file)), \
             mock.patch.object(agent_registry, 'capsule_path', side_effect=lambda org_id, filename: str(ledger_file)):
            agent_registry.sync_from_economy(org_id='org_a')

            data = agent_registry.load_registry()
            self.assertEqual(data['agents']['agent_atlas_a']['reputation_units'], 77)
            self.assertEqual(data['agents']['agent_atlas_a']['authority_units'], 66)
            self.assertEqual(data['agents']['agent_atlas_b']['reputation_units'], 100)
            self.assertEqual(data['agents']['agent_atlas_b']['authority_units'], 100)


if __name__ == '__main__':
    unittest.main()
