#!/usr/bin/env python3
import importlib.util
import pathlib
import shutil
import sys
import tempfile
import unittest
import uuid
from types import SimpleNamespace


ROOT = pathlib.Path(__file__).resolve().parents[2]
CAPSULE_PATH = ROOT / 'kernel' / 'capsule.py'
DISPATCH_QUEUE_PATH = ROOT / 'kernel' / 'federation_handoff_dispatch_queue.py'
WORKSPACE_PATH = ROOT / 'kernel' / 'workspace.py'


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FederationDispatchRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(prefix='meridian-federation-dispatch-runner-test-')
        self.root = pathlib.Path(self.tmpdir.name)
        self.economy_dir = self.root / 'economy'
        self.capsules_dir = self.root / 'capsules'
        self.kernel_dir = self.root / 'kernel'
        self.economy_dir.mkdir()
        self.capsules_dir.mkdir()
        self.kernel_dir.mkdir()

        self.orig_capsule_module = sys.modules.get('capsule')
        self.orig_capsule_path = None
        self.orig_capsules_dir = None
        self.orig_economy_dir = None
        self.orig_orgs_file = None
        self.orig_aliases = None
        self.orig_workspace_module = sys.modules.get('workspace')
        self.orig_federation_handoff_dispatch_queue_module = sys.modules.get('federation_handoff_dispatch_queue')

        self.capsule = _load_module(f'kernel_capsule_dispatch_runner_{uuid.uuid4().hex}', CAPSULE_PATH)
        self.orig_capsule_path = self.capsule.capsule_path
        self.orig_capsules_dir = self.capsule.CAPSULES_DIR
        self.orig_economy_dir = self.capsule.ECONOMY_DIR
        self.orig_orgs_file = self.capsule.ORGS_FILE
        self.orig_aliases = dict(self.capsule._CAPSULE_ALIASES)

        sys.modules['capsule'] = self.capsule
        self.capsule.ECONOMY_DIR = str(self.economy_dir)
        self.capsule.CAPSULES_DIR = str(self.capsules_dir)
        self.capsule.ORGS_FILE = str(self.kernel_dir / 'organizations.json')
        self.capsule._CAPSULE_ALIASES.clear()

        self.dispatch_queue = _load_module(f'kernel_federation_handoff_dispatch_queue_runner_{uuid.uuid4().hex}', DISPATCH_QUEUE_PATH)
        sys.modules['federation_handoff_dispatch_queue'] = self.dispatch_queue
        self.workspace = _load_module(f'kernel_workspace_dispatch_runner_{uuid.uuid4().hex}', WORKSPACE_PATH)
        self.workspace._runtime_host_state = lambda bound_org_id: (
            SimpleNamespace(host_id='host_local', role='institution_host'),
            {'bound_org_id': bound_org_id},
        )

        self.org_id = f'org_dispatch_runner_{uuid.uuid4().hex[:8]}'
        self.capsule.init_capsule(self.org_id)

    def tearDown(self):
        self.capsule.ECONOMY_DIR = self.orig_economy_dir
        self.capsule.CAPSULES_DIR = self.orig_capsules_dir
        self.capsule.ORGS_FILE = self.orig_orgs_file
        self.capsule._CAPSULE_ALIASES.clear()
        self.capsule._CAPSULE_ALIASES.update(self.orig_aliases)
        if self.orig_capsule_module is None:
            sys.modules.pop('capsule', None)
        else:
            sys.modules['capsule'] = self.orig_capsule_module
        if self.orig_federation_handoff_dispatch_queue_module is None:
            sys.modules.pop('federation_handoff_dispatch_queue', None)
        else:
            sys.modules['federation_handoff_dispatch_queue'] = self.orig_federation_handoff_dispatch_queue_module
        if self.orig_workspace_module is None:
            sys.modules.pop('workspace', None)
        else:
            sys.modules['workspace'] = self.orig_workspace_module
        self.tmpdir.cleanup()

    def _dispatch_record(self, dispatch_id, *, target_institution_id=None, target_host_id='host_local'):
        target_institution_id = target_institution_id or self.org_id
        return {
            'dispatch_id': dispatch_id,
            'handoff_id': dispatch_id,
            'bound_org_id': self.org_id,
            'requested_org_id': target_institution_id,
            'route_kind': 'remote',
            'route_state': 'remote',
            'route_reason': 'trusted_peer_can_serve_requested_institution',
            'state': 'dispatchable',
            'dispatch_ready': True,
            'dispatch_blockers': [],
            'dispatch_truth_source': 'acknowledged_handoff_preview_and_local_policy_only',
            'dispatch_paths': {
                'send': '/api/federation/send',
                'receive': '/api/federation/receive',
                'receiver_jobs': '/api/federation/execution-jobs',
                'receiver_execute': '/api/federation/execution-jobs/execute',
            },
            'draft_execution_request': {
                'message_type': 'execution_request',
                'boundary_name': 'federation_gateway',
                'identity_model': 'signed_host_service',
                'source_host_id': 'host_remote',
                'source_institution_id': 'org_remote',
                'target_host_id': target_host_id,
                'target_institution_id': target_institution_id,
                'payload_hash': '',
                'warrant_id': '',
                'commitment_id': '',
            },
            'preview_snapshot': {
                'handoff_id': dispatch_id,
                'requested_org_id': target_institution_id,
                'route_kind': 'remote',
                'route_state': 'remote',
                'route_reason': 'trusted_peer_can_serve_requested_institution',
                'handoff_state': 'previewed',
                'dispatch_ready': True,
                'dispatch_blockers': [],
                'preview_truth_source': 'planner_and_peer_registry_only',
                'dispatch_paths': {
                    'send': '/api/federation/send',
                    'receive': '/api/federation/receive',
                    'receiver_jobs': '/api/federation/execution-jobs',
                    'receiver_execute': '/api/federation/execution-jobs/execute',
                },
                'draft_execution_request': {
                    'message_type': 'execution_request',
                    'boundary_name': 'federation_gateway',
                    'identity_model': 'signed_host_service',
                    'source_host_id': 'host_remote',
                    'source_institution_id': 'org_remote',
                    'target_host_id': target_host_id,
                    'target_institution_id': target_institution_id,
                    'payload_hash': '',
                    'warrant_id': '',
                    'commitment_id': '',
                },
                'generated_at': '2026-03-22T00:00:00Z',
                'previewed_at': '2026-03-22T00:00:00Z',
                'queued_at': '2026-03-22T00:00:00Z',
                'acknowledged': True,
                'acknowledged_by': 'user:owner',
                'acknowledged_at': '2026-03-22T00:00:00Z',
                'acknowledged_note': 'reviewed',
                'settlement_claimed': False,
                'external_settlement_observed': False,
            },
            'acknowledged_by': 'user:owner',
            'acknowledged_at': '2026-03-22T00:00:00Z',
            'acknowledged_note': 'reviewed',
            'generated_at': '2026-03-22T00:00:00Z',
            'queued_at': '2026-03-22T00:00:00Z',
            'dispatched_at': '',
            'dispatched_by': '',
            'dispatched_note': '',
            'execution_job_id': '',
            'execution_job_state': '',
            'settlement_claimed': False,
            'external_settlement_observed': False,
        }

    def test_local_dispatch_runner_materializes_receiver_job_and_marks_dispatch_dispatched(self):
        self.dispatch_queue.upsert_handoff_dispatch_record(self.org_id, self._dispatch_record('fhdp_local_1'))

        result = self.workspace._run_local_federation_dispatch(
            self.org_id,
            'fhdp_local_1',
            actor_id='user:owner',
            note='promoted locally',
            session_id='ses_local',
        )

        self.assertEqual(result['dispatch_state'], 'dispatched')
        self.assertEqual(result['dispatch_record']['state'], 'dispatched')
        self.assertEqual(result['dispatch_record']['execution_job_state'], result['execution_job']['state'])
        self.assertEqual(result['dispatch_record']['dispatch_runner'], 'local_receiver_execution_runner')
        self.assertEqual(result['execution_job']['state'], 'pending_local_warrant')
        self.assertEqual(result['execution_job']['request']['claims']['target_institution_id'], self.org_id)
        self.assertEqual(result['execution_job']['request']['claims']['target_host_id'], 'host_local')
        self.assertIsNotNone(result['receiver_warrant'])
        self.assertTrue(result['execution_job_created'])

        fetched_dispatch = self.dispatch_queue.get_handoff_dispatch_record('fhdp_local_1', self.org_id)
        self.assertEqual(fetched_dispatch['execution_job_id'], result['execution_job']['job_id'])
        self.assertEqual(fetched_dispatch['execution_job_state'], 'pending_local_warrant')

        fetched_job = self.workspace.get_execution_job('fhdp_local_1', self.org_id)
        self.assertEqual(fetched_job['job_id'], result['execution_job']['job_id'])
        self.assertEqual(self.workspace.execution_job_summary(self.org_id)['pending_local_warrant'], 1)

    def test_local_dispatch_runner_rejects_non_local_target(self):
        self.dispatch_queue.upsert_handoff_dispatch_record(self.org_id, self._dispatch_record('fhdp_remote_1', target_institution_id='org_other'))

        with self.assertRaises(PermissionError):
            self.workspace._run_local_federation_dispatch(
                self.org_id,
                'fhdp_remote_1',
                actor_id='user:owner',
                note='should not run',
            )


if __name__ == '__main__':
    unittest.main()
