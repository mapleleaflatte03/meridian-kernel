#!/usr/bin/env python3
import importlib.util
import os
import unittest
from unittest import mock
from urllib.parse import urlparse


ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
WORKSPACE_PY = os.path.join(ROOT, 'workspace.py')


def _load_workspace(name):
    spec = importlib.util.spec_from_file_location(name, WORKSPACE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class WorkspaceContextTests(unittest.TestCase):
    def setUp(self):
        self.workspace = _load_workspace('kernel_workspace_context_test')
        self.orig_workspace_org_id = self.workspace.WORKSPACE_ORG_ID
        self.orig_runtime_host_identity_file = self.workspace.RUNTIME_HOST_IDENTITY_FILE
        self.orig_runtime_admission_file = self.workspace.RUNTIME_ADMISSION_FILE
        self.orig_federation_peers_file = self.workspace.FEDERATION_PEERS_FILE
        self.orig_federation_replay_file = self.workspace.FEDERATION_REPLAY_FILE
        self.orig_federation_signing_secret = self.workspace.FEDERATION_SIGNING_SECRET
        self.orig_load_orgs = self.workspace.load_orgs
        self.orig_load_workspace_credentials = self.workspace._load_workspace_credentials
        self.orig_load_host_identity = self.workspace.load_host_identity
        self.orig_load_admission_registry = self.workspace.load_admission_registry
        self.orig_runtime_host_state = self.workspace._runtime_host_state
        self.orig_federation_authority = self.workspace._federation_authority
        self.orig_refresh_peer_registry_entry = self.workspace.refresh_peer_registry_entry
        self.orig_log_event = self.workspace.log_event
        self.orig_list_warrants = self.workspace.list_warrants
        self.orig_get_warrant = self.workspace.get_warrant
        self.orig_issue_warrant = self.workspace.issue_warrant
        self.orig_review_warrant = self.workspace.review_warrant
        self.orig_commitment_summary = self.workspace.commitment_summary
        self.orig_list_commitments = self.workspace.list_commitments
        self.orig_validate_commitment_for_delivery = self.workspace.validate_commitment_for_delivery
        self.orig_validate_commitment_for_settlement = self.workspace.validate_commitment_for_settlement
        self.orig_record_delivery_ref = self.workspace.record_delivery_ref
        self.orig_record_settlement_ref = self.workspace.record_settlement_ref
        self.orig_settle_commitment = self.workspace.settle_commitment
        self.orig_case_summary = self.workspace.case_summary
        self.orig_list_cases = self.workspace.list_cases
        self.orig_blocking_commitment_ids = self.workspace.blocking_commitment_ids
        self.orig_blocked_peer_host_ids = self.workspace.blocked_peer_host_ids
        self.orig_blocking_commitment_case = self.workspace.blocking_commitment_case
        self.orig_blocking_peer_case = self.workspace.blocking_peer_case
        self.orig_maybe_block_commitment_settlement = self.workspace._maybe_block_commitment_settlement
        self.orig_set_peer_trust_state = self.workspace.set_peer_trust_state
        self.orig_ensure_case_for_delivery_failure = self.workspace.ensure_case_for_delivery_failure
        self.orig_summarize_inbox_entries = self.workspace.summarize_inbox_entries
        self.orig_get_execution_job = self.workspace.get_execution_job
        self.orig_get_execution_job_by_local_warrant = self.workspace.get_execution_job_by_local_warrant
        self.orig_list_execution_jobs = self.workspace.list_execution_jobs
        self.orig_execution_job_summary = self.workspace.execution_job_summary
        self.orig_sync_execution_job_for_local_warrant = self.workspace.sync_execution_job_for_local_warrant
        self.orig_upsert_execution_job = self.workspace.upsert_execution_job

    def tearDown(self):
        self.workspace.WORKSPACE_ORG_ID = self.orig_workspace_org_id
        self.workspace.RUNTIME_HOST_IDENTITY_FILE = self.orig_runtime_host_identity_file
        self.workspace.RUNTIME_ADMISSION_FILE = self.orig_runtime_admission_file
        self.workspace.FEDERATION_PEERS_FILE = self.orig_federation_peers_file
        self.workspace.FEDERATION_REPLAY_FILE = self.orig_federation_replay_file
        self.workspace.FEDERATION_SIGNING_SECRET = self.orig_federation_signing_secret
        self.workspace.load_orgs = self.orig_load_orgs
        self.workspace._load_workspace_credentials = self.orig_load_workspace_credentials
        self.workspace.load_host_identity = self.orig_load_host_identity
        self.workspace.load_admission_registry = self.orig_load_admission_registry
        self.workspace._runtime_host_state = self.orig_runtime_host_state
        self.workspace._federation_authority = self.orig_federation_authority
        self.workspace.refresh_peer_registry_entry = self.orig_refresh_peer_registry_entry
        self.workspace.log_event = self.orig_log_event
        self.workspace.list_warrants = self.orig_list_warrants
        self.workspace.get_warrant = self.orig_get_warrant
        self.workspace.issue_warrant = self.orig_issue_warrant
        self.workspace.review_warrant = self.orig_review_warrant
        self.workspace.commitment_summary = self.orig_commitment_summary
        self.workspace.list_commitments = self.orig_list_commitments
        self.workspace.validate_commitment_for_delivery = self.orig_validate_commitment_for_delivery
        self.workspace.validate_commitment_for_settlement = self.orig_validate_commitment_for_settlement
        self.workspace.record_delivery_ref = self.orig_record_delivery_ref
        self.workspace.record_settlement_ref = self.orig_record_settlement_ref
        self.workspace.settle_commitment = self.orig_settle_commitment
        self.workspace.case_summary = self.orig_case_summary
        self.workspace.list_cases = self.orig_list_cases
        self.workspace.blocking_commitment_ids = self.orig_blocking_commitment_ids
        self.workspace.blocked_peer_host_ids = self.orig_blocked_peer_host_ids
        self.workspace.blocking_commitment_case = self.orig_blocking_commitment_case
        self.workspace.blocking_peer_case = self.orig_blocking_peer_case
        self.workspace._maybe_block_commitment_settlement = self.orig_maybe_block_commitment_settlement
        self.workspace.set_peer_trust_state = self.orig_set_peer_trust_state
        self.workspace.ensure_case_for_delivery_failure = self.orig_ensure_case_for_delivery_failure
        self.workspace.summarize_inbox_entries = self.orig_summarize_inbox_entries
        self.workspace.get_execution_job = self.orig_get_execution_job
        self.workspace.get_execution_job_by_local_warrant = self.orig_get_execution_job_by_local_warrant
        self.workspace.list_execution_jobs = self.orig_list_execution_jobs
        self.workspace.execution_job_summary = self.orig_execution_job_summary
        self.workspace.sync_execution_job_for_local_warrant = self.orig_sync_execution_job_for_local_warrant
        self.workspace.upsert_execution_job = self.orig_upsert_execution_job

    def test_configured_org_binds_process_context(self):
        self.workspace._load_workspace_credentials = lambda: (None, None, None, None)
        self.workspace.WORKSPACE_ORG_ID = 'org_b'
        self.workspace.load_orgs = lambda: {
            'organizations': {
                'org_a': {'id': 'org_a', 'slug': 'a', 'name': 'A'},
                'org_b': {'id': 'org_b', 'slug': 'b', 'name': 'B'},
            }
        }
        ctx = self.workspace._resolve_workspace_context()
        self.assertEqual(ctx.org_id, 'org_b')
        self.assertEqual(ctx.org.get('slug'), 'b')
        self.assertEqual(ctx.context_source, 'configured_org')
        self.assertEqual(ctx.boundary.name, 'workspace')

    def test_credential_scoped_org_binds_process_context(self):
        self.workspace._load_workspace_credentials = lambda: ('owner', 'secret', 'org_b', None)
        self.workspace.load_orgs = lambda: {
            'organizations': {
                'org_a': {'id': 'org_a', 'slug': 'a', 'name': 'A'},
                'org_b': {'id': 'org_b', 'slug': 'b', 'name': 'B'},
            }
        }
        ctx = self.workspace._resolve_workspace_context()
        self.assertEqual(ctx.org_id, 'org_b')
        self.assertEqual(ctx.org.get('slug'), 'b')
        self.assertEqual(ctx.context_source, 'credentials_org')
        self.assertEqual(ctx.boundary.identity_model, 'session')

    def test_credential_scope_conflict_is_rejected(self):
        self.workspace._load_workspace_credentials = lambda: ('owner', 'secret', 'org_a', None)
        self.workspace.WORKSPACE_ORG_ID = 'org_b'
        with self.assertRaises(RuntimeError):
            self.workspace._resolve_workspace_context()

    def test_request_override_must_match_bound_org(self):
        with self.assertRaises(ValueError):
            self.workspace._enforce_request_context(
                urlparse('/api/status?org_id=org_other'),
                _Headers(),
                'org_a',
            )

        context = self.workspace._enforce_request_context(
            urlparse('/api/status?org_id=org_a'),
            _Headers({'X-Meridian-Org-Id': 'org_a'}),
            'org_a',
        )
        self.assertEqual(context['requested_org_id'], 'org_a')
        self.assertEqual(context['bound_org_id'], 'org_a')

    def test_auth_context_reports_credential_binding(self):
        self.workspace._load_workspace_credentials = lambda: ('owner', 'secret', 'org_a', None)
        auth = self.workspace._resolve_auth_context('org_a')
        self.assertEqual(auth['mode'], 'credential_bound')
        self.assertEqual(auth['org_id'], 'org_a')
        self.assertEqual(auth['actor_id'], 'workspace_user:owner')

    def test_auth_context_prefers_explicit_user_id(self):
        self.workspace._load_workspace_credentials = lambda: ('owner', 'secret', 'org_a', 'user_meridian_owner')
        self.workspace.load_orgs = lambda: {
            'organizations': {
                'org_a': {
                    'id': 'org_a',
                    'slug': 'a',
                    'name': 'A',
                    'owner_id': 'user_meridian_owner',
                    'members': [{'user_id': 'user_meridian_owner', 'role': 'owner'}],
                },
            }
        }
        auth = self.workspace._resolve_auth_context('org_a')
        self.assertEqual(auth['actor_id'], 'user_meridian_owner')
        self.assertEqual(auth['actor_source'], 'credentials')
        self.assertEqual(auth['role'], 'owner')

    def test_auth_context_resolves_owner_alias_role(self):
        self.workspace._load_workspace_credentials = lambda: ('owner', 'secret', 'org_a', None)
        self.workspace.load_orgs = lambda: {
            'organizations': {
                'org_a': {
                    'id': 'org_a',
                    'slug': 'a',
                    'name': 'A',
                    'owner_id': 'user_owner',
                    'members': [{'user_id': 'user_owner', 'role': 'owner'}],
                },
            }
        }
        auth = self.workspace._resolve_auth_context('org_a')
        self.assertEqual(auth['user_id'], 'user_owner')
        self.assertEqual(auth['role'], 'owner')
        self.assertEqual(auth['actor_source'], 'owner_alias')

    def test_mutation_authorization_requires_admin_for_kill_switch(self):
        auth = {'enabled': True, 'role': 'member'}
        with self.assertRaises(PermissionError):
            self.workspace._enforce_mutation_authorization(auth, 'org_a', '/api/authority/kill-switch')

    def test_mutation_authorization_allows_member_request(self):
        auth = {'enabled': True, 'role': 'member'}
        required = self.workspace._enforce_mutation_authorization(auth, 'org_a', '/api/authority/request')
        self.assertEqual(required, 'member')

    def test_permission_snapshot_tracks_allowed_paths(self):
        auth = {'enabled': True, 'role': 'admin'}
        permissions = self.workspace._permission_snapshot(auth)['mutation_paths']
        self.assertTrue(permissions['/api/authority/kill-switch']['allowed'])
        self.assertTrue(permissions['/api/institution/charter']['allowed'])
        self.assertFalse(permissions['/api/treasury/contribute']['allowed'])
        self.assertTrue(permissions['/api/warrants/issue']['allowed'])
        self.assertTrue(permissions['/api/warrants/approve']['allowed'])
        self.assertTrue(permissions['/api/payouts/propose']['allowed'])
        self.assertTrue(permissions['/api/payouts/submit']['allowed'])
        self.assertTrue(permissions['/api/payouts/review']['allowed'])
        self.assertFalse(permissions['/api/payouts/approve']['allowed'])
        self.assertTrue(permissions['/api/treasury/settlement-adapters/preflight']['allowed'])
        self.assertTrue(permissions['/api/subscriptions/add']['allowed'])
        self.assertTrue(permissions['/api/subscriptions/record-delivery']['allowed'])
        self.assertFalse(permissions['/api/accounting/draw']['allowed'])
        self.assertEqual(permissions['/api/accounting/draw']['required_role'], 'owner')
        self.assertEqual(
            permissions['/api/treasury/settlement-adapters/preflight']['required_role'],
            'member',
        )
        self.assertEqual(permissions['/api/payouts/execute']['required_role'], 'owner')
        self.assertTrue(permissions['/api/commitments/propose']['allowed'])
        self.assertTrue(permissions['/api/commitments/accept']['allowed'])
        self.assertTrue(permissions['/api/cases/open']['allowed'])
        self.assertTrue(permissions['/api/cases/resolve']['allowed'])
        self.assertTrue(permissions['/api/federation/send']['allowed'])
        self.assertTrue(permissions['/api/federation/execution-jobs/execute']['allowed'])
        self.assertEqual(permissions['/api/federation/execution-jobs/execute']['required_role'], 'admin')
        self.assertFalse(permissions['/api/federation/peers/refresh']['allowed'])
        self.assertEqual(permissions['/api/federation/peers/refresh']['required_role'], 'owner')

    def test_payout_snapshot_surfaces_settlement_adapters(self):
        self.workspace.payout_proposal_summary = lambda org_id=None: {'total': 0, 'executed': 0}
        self.workspace.list_payout_proposals = lambda org_id=None: []
        self.workspace.load_payout_proposals = lambda org_id=None: {'state_machine': {'states': []}}
        self.workspace.list_settlement_adapters = lambda org_id=None: [
            {'adapter_id': 'internal_ledger', 'payout_execution_enabled': True},
            {'adapter_id': 'base_usdc_x402', 'payout_execution_enabled': False},
        ]
        self.workspace.settlement_adapter_summary = lambda org_id=None, host_supported_adapters=None: {
            'default_payout_adapter': 'internal_ledger',
            'host_supported_adapters': list(host_supported_adapters or []),
        }
        snapshot = self.workspace._payout_snapshot(
            'org_a',
            host_supported_adapters=['internal_ledger'],
        )
        self.assertEqual(snapshot['settlement_adapter_summary']['default_payout_adapter'], 'internal_ledger')
        self.assertEqual(snapshot['settlement_adapter_summary']['host_supported_adapters'], ['internal_ledger'])
        self.assertEqual(len(snapshot['settlement_adapters']), 2)

    def test_api_status_exposes_runtime_core(self):
        from runtime_host import default_host_identity
        self.workspace._load_workspace_credentials = lambda: ('owner', 'secret', 'org_a', 'user_owner')
        self.workspace.load_orgs = lambda: {
            'organizations': {
                'org_a': {
                    'id': 'org_a',
                    'slug': 'a',
                    'name': 'A',
                    'owner_id': 'user_owner',
                    'members': [{'user_id': 'user_owner', 'role': 'owner'}],
                    'lifecycle_state': 'active',
                    'policy_defaults': {},
                },
            }
        }
        self.workspace.load_registry = lambda: {'agents': {}}
        self.workspace._load_queue = lambda org_id: {
            'kill_switch': False,
            'pending_approvals': {},
            'delegations': {},
        }
        self.workspace.treasury_snapshot = lambda org_id: {}
        self.workspace._load_records = lambda org_id: {'violations': {}, 'appeals': {}}
        self.workspace.list_warrants = lambda org_id=None, **_kwargs: [
            {
                'warrant_id': 'war_demo',
                'court_review_state': 'approved',
                'execution_state': 'ready',
            }
        ]
        self.workspace.list_commitments = lambda org_id=None, **_kwargs: [
            {
                'commitment_id': 'cmt_demo',
                'status': 'accepted',
            }
        ]
        self.workspace.commitment_summary = lambda org_id=None: {
            'total': 1,
            'proposed': 0,
            'accepted': 1,
            'rejected': 0,
            'breached': 0,
            'settled': 0,
            'delivery_refs_total': 0,
        }
        self.workspace.list_cases = lambda org_id=None, **_kwargs: [
            {
                'case_id': 'case_demo',
                'status': 'open',
                'claim_type': 'breach_of_commitment',
            }
        ]
        self.workspace.case_summary = lambda org_id=None: {
            'total': 1,
            'open': 1,
            'stayed': 0,
            'resolved': 0,
        }
        self.workspace.blocking_commitment_ids = lambda org_id=None: ['cmt_demo']
        self.workspace.blocked_peer_host_ids = lambda org_id=None: ['host_beta']
        self.workspace.get_sprint_lead = lambda org_id: ('', 0)
        self.workspace.get_pending_approvals = lambda org_id=None: []
        self.workspace._ci_vertical_status = lambda reg, lead_id, org_id=None: {}
        self.workspace.get_agent_remediation = lambda economy_key, reg: None
        self.workspace.load_host_identity = lambda *args, **kwargs: default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            supported_boundaries=['workspace', 'cli'],
        )
        self.workspace.load_admission_registry = lambda *args, **kwargs: {
            'source': 'file',
            'host_id': 'host_alpha',
            'institutions': {
                'org_a': {'status': 'admitted'},
                'org_b': {'status': 'admitted'},
            },
            'admitted_org_ids': ['org_a', 'org_b'],
        }
        self.workspace.load_subscriptions = lambda org_id=None: {
            'subscribers': {'111': []},
            'delivery_log': [],
            '_meta': {'storage_model': 'capsule_canonical'},
        }
        self.workspace.subscription_summary = lambda org_id=None: {'subscriber_count': 1}
        self.workspace.active_delivery_targets = lambda org_id=None, external_only=False: ['111']
        self.workspace.accounting_snapshot = lambda org_id=None: {
            'bound_org_id': org_id,
            'summary': {'entry_count': 0},
            'mutation_enabled': True,
        }
        ctx = self.workspace._resolve_workspace_context()
        status = self.workspace.api_status(institution_context=ctx)
        self.assertEqual(status['runtime_core']['institution_context']['org_id'], 'org_a')
        self.assertTrue(status['runtime_core']['service_registry']['workspace']['supports_institution_routing'])
        self.assertTrue(status['runtime_core']['service_registry']['federation_gateway']['supports_institution_routing'])
        self.assertTrue(status['runtime_core']['service_registry']['federation_gateway']['requires_warrant'])
        self.assertEqual(
            status['runtime_core']['service_registry']['federation_gateway']['required_warrant_actions']['execution_request'],
            'federated_execution',
        )
        self.assertTrue(status['runtime_core']['admission']['additional_institutions_allowed'])
        self.assertEqual(status['runtime_core']['admission']['management_mode'], 'workspace_api_file_backed')
        self.assertTrue(status['runtime_core']['admission']['mutation_enabled'])
        self.assertEqual(status['runtime_core']['host_identity']['host_id'], 'host_alpha')
        self.assertEqual(status['runtime_core']['admission']['admitted_org_ids'], ['org_a', 'org_b'])
        self.assertEqual(status['warrants']['total'], 1)
        self.assertEqual(status['warrants']['executable'], 1)
        self.assertEqual(status['commitments']['total'], 1)
        self.assertEqual(status['commitments']['accepted'], 1)
        self.assertEqual(status['commitments']['management_mode'], 'workspace_api_file_backed')
        self.assertTrue(status['commitments']['mutation_enabled'])
        self.assertEqual(status['cases']['total'], 1)
        self.assertEqual(status['cases']['open'], 1)
        self.assertEqual(status['cases']['management_mode'], 'workspace_api_file_backed')
        self.assertEqual(status['cases']['blocking_commitment_ids'], ['cmt_demo'])
        self.assertEqual(status['cases']['blocked_peer_host_ids'], ['host_beta'])
        self.assertIn('federation', status['runtime_core'])
        self.assertTrue(status['runtime_core']['service_registry']['subscriptions']['supports_institution_routing'])
        self.assertTrue(status['runtime_core']['service_registry']['accounting']['supports_institution_routing'])
        self.assertEqual(status['service_state']['subscriptions']['summary']['subscriber_count'], 1)
        self.assertEqual(status['service_state']['accounting']['summary']['entry_count'], 0)

    def test_workspace_get_surfaces_subscriptions_and_accounting(self):
        class FakeContext:
            def __init__(self, org_id='org_a'):
                self.org_id = org_id
                self.org = {'id': org_id, 'name': 'Org A'}
                self.context_source = 'configured_org'

        captured = {}
        handler = object.__new__(self.workspace.WorkspaceHandler)
        handler.path = '/api/subscriptions'
        handler.headers = _Headers()
        handler._require_auth = lambda _path: True
        handler._session_claims_from_request = lambda expected_org_id=None: None
        handler._json = lambda data, status=200: captured.update({'status': status, 'data': data})
        handler._html = lambda html: captured.update({'status': 200, 'html': html})

        with mock.patch.object(self.workspace, '_resolve_workspace_context', return_value=FakeContext()), \
             mock.patch.object(self.workspace, '_enforce_request_context', return_value={'mode': 'process_bound'}), \
             mock.patch.object(self.workspace, '_resolve_auth_context', return_value={'enabled': True, 'role': 'owner'}), \
             mock.patch.object(self.workspace, 'load_subscriptions', return_value={'subscribers': {'111': []}, 'delivery_log': [], '_meta': {'storage_model': 'capsule_canonical'}}), \
             mock.patch.object(self.workspace, 'subscription_summary', return_value={'subscriber_count': 1}), \
             mock.patch.object(self.workspace, 'active_delivery_targets', return_value=['111']), \
             mock.patch.object(self.workspace, 'accounting_snapshot', return_value={'bound_org_id': 'org_a', 'summary': {'entry_count': 0}}):
            handler.do_GET()
            self.assertEqual(captured['status'], 200)
            self.assertEqual(captured['data']['bound_org_id'], 'org_a')
            self.assertEqual(captured['data']['summary']['subscriber_count'], 1)
            self.assertEqual(captured['data']['state']['subscribers'], {'111': []})

            handler.path = '/api/subscriptions/delivery-targets'
            captured.clear()
            handler.do_GET()
            self.assertEqual(captured['status'], 200)
            self.assertEqual(captured['data']['targets'], ['111'])
            self.assertEqual(captured['data']['external_targets'], ['111'])

            handler.path = '/api/accounting'
            captured.clear()
            handler.do_GET()
            self.assertEqual(captured['status'], 200)
            self.assertEqual(captured['data']['bound_org_id'], 'org_a')
            self.assertEqual(captured['data']['summary']['entry_count'], 0)

    def test_federation_snapshot_surfaces_trusted_peers(self):
        from runtime_host import default_host_identity
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as tmp:
            peers_path = os.path.join(tmp, 'federation_peers.json')
            replay_path = os.path.join(tmp, 'federation_replay.log')
            with open(peers_path, 'w') as f:
                json.dump({
                    'host_id': 'host_alpha',
                    'peers': {
                        'host_beta': {
                            'label': 'Beta Host',
                            'transport': 'https',
                            'endpoint_url': 'http://127.0.0.1:19014',
                            'trust_state': 'trusted',
                            'shared_secret': 'beta-secret',
                            'admitted_org_ids': ['org_b'],
                        }
                    },
                }, f)
            self.workspace.FEDERATION_PEERS_FILE = peers_path
            self.workspace.FEDERATION_REPLAY_FILE = replay_path
            self.workspace.FEDERATION_SIGNING_SECRET = 'alpha-secret'
            host = default_host_identity(
                host_id='host_alpha',
                federation_enabled=True,
                peer_transport='https',
            )
            snap = self.workspace._federation_snapshot(
                'org_a',
                host_identity=host,
                admission_registry={'admitted_org_ids': ['org_a', 'org_b']},
            )
            self.assertTrue(snap['enabled'])
            self.assertTrue(snap['send_enabled'])
            self.assertEqual(snap['peer_count'], 1)
            self.assertEqual(snap['all_peer_count'], 1)
            self.assertEqual(snap['trusted_peer_ids'], ['host_beta'])
            self.assertEqual(snap['admitted_org_ids'], ['org_a', 'org_b'])
            self.assertEqual(snap['management_mode'], 'workspace_api_file_backed')
            self.assertTrue(snap['mutation_enabled'])

    def test_federation_execution_jobs_snapshot_surfaces_local_warrant(self):
        self.workspace.list_execution_jobs = lambda org_id, state=None: [
            {
                'job_id': 'fej_demo',
                'envelope_id': 'fed_exec_demo',
                'receipt_id': 'fedrcpt_demo',
                'state': 'pending_local_warrant',
                'local_warrant_id': 'war_local_demo',
                'message_type': 'execution_request',
                'received_at': '2026-03-22T00:00:00Z',
                'source_host_id': 'host_alpha',
                'source_institution_id': 'org_alpha',
                'target_host_id': 'host_beta',
                'target_institution_id': 'org_a',
                'boundary_name': 'federation_gateway',
                'identity_model': 'signed_host_service',
                'payload': {'task': 'demo'},
                'payload_hash': 'hash_demo',
            }
        ]
        self.workspace.execution_job_summary = lambda org_id: {
            'org_id': org_id,
            'total': 1,
            'pending_local_warrant': 1,
            'ready': 0,
            'executed': 0,
            'blocked': 0,
            'rejected': 0,
            'state_counts': {'pending_local_warrant': 1},
            'message_type_counts': {'execution_request': 1},
            'updatedAt': '2026-03-22T00:00:00Z',
        }
        self.workspace.get_warrant = lambda warrant_id, org_id=None: {
            'warrant_id': warrant_id,
            'court_review_state': 'pending_review',
            'execution_state': 'ready',
            'expires_at': '2026-03-22T01:00:00Z',
        }
        snapshot = self.workspace._federation_execution_jobs_snapshot('org_a')
        self.assertEqual(snapshot['summary']['total'], 1)
        self.assertEqual(snapshot['summary']['pending_local_warrant'], 1)
        self.assertEqual(snapshot['summary']['message_type_counts'], {'execution_request': 1})
        self.assertEqual(snapshot['jobs'][0]['envelope_id'], 'fed_exec_demo')
        self.assertEqual(snapshot['jobs'][0]['state'], 'pending_local_warrant')
        self.assertEqual(snapshot['jobs'][0]['local_warrant']['warrant_id'], 'war_local_demo')
        self.assertEqual(snapshot['jobs'][0]['local_warrant']['court_review_state'], 'pending_review')
        self.assertEqual(snapshot['jobs'][0]['local_warrant']['execution_state'], 'ready')

    def test_execute_federated_execution_job_records_settlement_notice_once(self):
        job = {
            'job_id': 'fej_demo',
            'envelope_id': 'fed_demo',
            'source_host_id': 'host_alpha',
            'source_institution_id': 'org_alpha',
            'target_host_id': 'host_beta',
            'target_institution_id': 'org_beta',
            'actor_type': 'service',
            'actor_id': 'peer:host_alpha',
            'session_id': 'ses_demo',
            'boundary_name': 'federation_gateway',
            'identity_model': 'signed_host_service',
            'message_type': 'execution_request',
            'receipt_id': 'fedrcpt_demo',
            'sender_warrant_id': 'war_sender',
            'local_warrant_id': 'war_local_demo',
            'commitment_id': 'cmt_demo',
            'payload': {'task': 'demo'},
            'payload_hash': 'hash_demo',
            'state': 'ready',
            'received_at': '2026-03-22T00:00:00Z',
            'note': 'Receiver-side execution request queued for local warrant review',
            'metadata': {},
            'execution_refs': {},
        }
        warrant = {
            'warrant_id': 'war_local_demo',
            'court_review_state': 'approved',
            'execution_state': 'ready',
            'execution_refs': {},
        }
        commitment = {
            'commitment_id': 'cmt_demo',
            'state': 'accepted',
            'status': 'accepted',
            'target_host_id': 'host_alpha',
            'target_institution_id': 'org_alpha',
            'delivery_refs': [],
        }
        stored_job = dict(job)
        stored_warrant = dict(warrant)
        delivery = {
            'claims': {
                'envelope_id': 'fed_notice_1',
                'target_host_id': 'host_alpha',
                'target_institution_id': 'org_alpha',
            },
            'receipt': {
                'receipt_id': 'fedrcpt_notice_1',
                'accepted_at': '2026-03-22T00:00:01Z',
            },
            'response': {'processing': {'applied': True}},
        }

        def fake_upsert(_org_id, **fields):
            stored_job.update(fields)
            if 'execution_refs' in fields:
                stored_job['execution_refs'] = dict(fields['execution_refs'] or {})
            if 'metadata' in fields:
                stored_job['metadata'] = dict(fields['metadata'] or {})
            return dict(stored_job)

        def fake_mark_warrant_executed(_warrant_id, *, org_id=None, execution_refs=None):
            stored_warrant['execution_state'] = 'executed'
            stored_warrant['executed_at'] = '2026-03-22T00:00:01Z'
            stored_warrant['execution_refs'] = dict(execution_refs or {})
            return dict(stored_warrant)

        with mock.patch.object(self.workspace, 'get_warrant', return_value=stored_warrant), \
             mock.patch.object(self.workspace, 'validate_warrant_for_execution') as validate, \
             mock.patch.object(self.workspace, 'mark_warrant_executed', side_effect=fake_mark_warrant_executed), \
             mock.patch.object(self.workspace, 'get_commitment', return_value=commitment), \
             mock.patch.object(self.workspace, 'upsert_execution_job', side_effect=fake_upsert), \
             mock.patch.object(self.workspace, '_deliver_federation_envelope', return_value=(delivery, {'host_id': 'host_beta'})) as deliver, \
             mock.patch.object(self.workspace, 'log_event'):
            executed = self.workspace._complete_federated_execution_job(
                'org_a',
                job,
                actor_id='user_owner',
                session_id='ses_demo',
                execution_refs={
                    'proof_type': 'local_execution',
                    'verification_state': 'host_local_final',
                    'finality_state': 'host_local_final',
                    'proof': {'job_id': 'fej_demo'},
                },
            )

            self.assertEqual(executed['execution_job']['state'], 'executed')
            self.assertEqual(executed['warrant']['execution_state'], 'executed')
            self.assertEqual(executed['settlement_notice']['message_type'], 'settlement_notice')
            self.assertEqual(executed['settlement_notice']['envelope_id'], 'fed_notice_1')
            self.assertEqual(deliver.call_count, 1)
            validate.assert_called_once()

            commitment['delivery_refs'] = [
                {
                    'message_type': 'settlement_notice',
                    'envelope_id': 'fed_notice_1',
                    'receipt_id': 'fedrcpt_notice_1',
                    'target_host_id': 'host_alpha',
                    'target_institution_id': 'org_alpha',
                    'recorded_at': '2026-03-22T00:00:01Z',
                },
            ]
            stored_job['execution_refs'] = {}

            replay = self.workspace._complete_federated_execution_job(
                'org_a',
                dict(stored_job, state='executed'),
                actor_id='user_owner',
                session_id='ses_demo',
            )

            self.assertEqual(replay['settlement_notice']['envelope_id'], 'fed_notice_1')
            self.assertEqual(deliver.call_count, 1)

    def test_federation_manifest_surfaces_host_admission_and_service_registry(self):
        from runtime_host import default_host_identity

        self.workspace._load_workspace_credentials = lambda: (None, None, None, None)
        self.workspace.WORKSPACE_ORG_ID = 'org_a'
        self.workspace.load_orgs = lambda: {
            'organizations': {
                'org_a': {'id': 'org_a', 'slug': 'a', 'name': 'A', 'lifecycle_state': 'active'},
            }
        }
        ctx = self.workspace._resolve_workspace_context()
        host = default_host_identity(
            host_id='host_alpha',
            role='control_host',
            federation_enabled=True,
            peer_transport='https',
            supported_boundaries=['workspace', 'cli', 'federation_gateway'],
        )
        manifest = self.workspace._federation_manifest(
            ctx,
            host_identity=host,
            admission_registry={
                'source': 'file',
                'host_id': 'host_alpha',
                'institutions': {'org_a': {'status': 'admitted'}},
                'admitted_org_ids': ['org_a'],
            },
        )
        self.assertEqual(manifest['host_identity']['host_id'], 'host_alpha')
        self.assertEqual(manifest['admission']['bound_org_id'], ctx.org_id)
        self.assertIn('federation_gateway', manifest['service_registry'])
        self.assertEqual(manifest['federation']['boundary_name'], 'federation_gateway')
        self.assertTrue(manifest['service_registry']['federation_gateway']['requires_warrant'])

    def test_federation_receipt_is_bound_to_receiver_host_and_org(self):
        from federation import FederationEnvelopeClaims

        receipt = self.workspace._federation_receipt(
            'org_a',
            'host_alpha',
            FederationEnvelopeClaims(
                envelope_id='fed_demo',
                message_type='execution_request',
                boundary_name='federation_gateway',
            ),
        )
        self.assertEqual(receipt['envelope_id'], 'fed_demo')
        self.assertEqual(receipt['receiver_host_id'], 'host_alpha')
        self.assertEqual(receipt['receiver_institution_id'], 'org_a')
        self.assertEqual(receipt['identity_model'], 'signed_host_service')
        self.assertTrue(receipt['receipt_id'].startswith('fedrcpt_'))

    def test_federation_snapshot_surfaces_inbox_summary(self):
        from runtime_host import default_host_identity
        self.workspace.summarize_inbox_entries = lambda org_id: {
            'org_id': org_id,
            'total': 1,
            'received': 1,
            'processed': 0,
            'message_type_counts': {'execution_request': 1},
            'state_counts': {'received': 1},
            'updatedAt': '2026-03-22T00:00:00Z',
        }
        snapshot = self.workspace._federation_snapshot(
            'org_a',
            host_identity=default_host_identity(
                host_id='host_alpha',
                role='control_host',
                federation_enabled=True,
                peer_transport='https',
                supported_boundaries=['workspace', 'cli', 'federation_gateway'],
            ),
            admission_registry={
                'source': 'file',
                'host_id': 'host_alpha',
                'institutions': {'org_a': {'status': 'admitted'}},
                'admitted_org_ids': ['org_a'],
            },
            peer_registry={
                'host_id': 'host_alpha',
                'peers': {},
                'trusted_peer_ids': [],
            },
        )
        self.assertEqual(snapshot['inbox_summary']['total'], 1)
        self.assertEqual(
            snapshot['inbox_summary']['message_type_counts']['execution_request'],
            1,
        )

    def test_process_received_settlement_notice_marks_inbox_processed(self):
        from federation import FederationEnvelopeClaims

        calls = {}
        self.workspace.validate_commitment_for_settlement = (
            lambda commitment_id, **kwargs: {'commitment_id': commitment_id, 'state': 'accepted'}
        )
        self.workspace._maybe_block_commitment_settlement = lambda *args, **kwargs: (None, None)
        self.workspace.record_settlement_ref = (
            lambda commitment_id, settlement_ref, org_id=None: calls.setdefault(
                'settlement_ref',
                (commitment_id, settlement_ref, org_id),
            )
        )
        self.workspace.settle_commitment = (
            lambda commitment_id, by, org_id=None, note='': {
                'commitment_id': commitment_id,
                'state': 'settled',
                'settled_by': by,
            }
        )
        self.workspace.log_event = lambda *args, **kwargs: calls.setdefault('audit', []).append((args, kwargs))

        original_inbox_entry = self.workspace._federation_inbox_entry
        self.workspace._federation_inbox_entry = lambda *args, **kwargs: {
            'envelope_id': 'fed_settle',
            'state': kwargs.get('state', 'received'),
            'processed_at': '2026-03-22T00:00:00Z' if kwargs.get('state') == 'processed' else '',
        }
        try:
            claims = FederationEnvelopeClaims(
                envelope_id='fed_settle',
                source_host_id='host_alpha',
                source_institution_id='org_alpha',
                target_host_id='host_beta',
                target_institution_id='org_a',
                actor_type='user',
                actor_id='user_alpha',
                session_id='ses_alpha',
                boundary_name='federation_gateway',
                identity_model='signed_host_service',
                message_type='settlement_notice',
                payload_hash='hash_demo',
                warrant_id='war_demo',
                commitment_id='cmt_demo',
            )
            receipt = {
                'receipt_id': 'fedrcpt_demo',
                'accepted_at': '2026-03-22T00:00:00Z',
            }
            processing = self.workspace._process_received_federation_message(
                'org_a',
                claims,
                receipt,
                payload={
                    'proposal_id': 'pay_demo',
                    'tx_ref': 'tx_demo',
                    'settlement_adapter': 'internal_ledger',
                    'proof_type': 'internal_ledger',
                    'verification_state': 'accepted',
                    'finality_state': 'final',
                    'proof': {'row': 1},
                },
            )
        finally:
            self.workspace._federation_inbox_entry = original_inbox_entry

        self.assertTrue(processing['applied'])
        self.assertEqual(processing['reason'], 'settlement_notice_applied')
        self.assertEqual(processing['state'], 'processed')
        self.assertEqual(processing['commitment']['state'], 'settled')
        self.assertEqual(processing['settlement_ref']['tx_ref'], 'tx_demo')
        self.assertEqual(processing['settlement_ref']['proposal_id'], 'pay_demo')
        self.assertEqual(processing['inbox_entry']['state'], 'processed')
        self.assertEqual(calls['settlement_ref'][0], 'cmt_demo')
        self.assertEqual(calls['settlement_ref'][2], 'org_a')

    def test_process_received_settlement_notice_respects_case_block(self):
        from federation import FederationEnvelopeClaims

        self.workspace.validate_commitment_for_settlement = (
            lambda commitment_id, **kwargs: {'commitment_id': commitment_id, 'state': 'accepted'}
        )
        self.workspace._maybe_block_commitment_settlement = lambda *args, **kwargs: (
            {'case_id': 'case_demo', 'status': 'open', 'linked_commitment_id': 'cmt_demo'},
            {'applied': True, 'warrant_id': 'war_demo', 'court_review_state': 'stayed'},
        )
        self.workspace.record_settlement_ref = lambda *args, **kwargs: self.fail('settlement ref should not be recorded')
        self.workspace.settle_commitment = lambda *args, **kwargs: self.fail('commitment should not settle')
        self.workspace.log_event = lambda *args, **kwargs: None

        claims = FederationEnvelopeClaims(
            envelope_id='fed_settle_blocked',
            source_host_id='host_alpha',
            source_institution_id='org_alpha',
            target_host_id='host_beta',
            target_institution_id='org_a',
            actor_type='service',
            actor_id='peer:host_alpha',
            session_id='',
            boundary_name='federation_gateway',
            identity_model='signed_host_service',
            message_type='settlement_notice',
            payload_hash='hash_demo',
            warrant_id='war_demo',
            commitment_id='cmt_demo',
        )
        processing = self.workspace._process_received_federation_message(
            'org_a',
            claims,
            {'receipt_id': 'fedrcpt_demo', 'accepted_at': '2026-03-22T00:00:00Z'},
            payload={'tx_ref': 'tx_demo'},
        )
        self.assertFalse(processing['applied'])
        self.assertEqual(processing['reason'], 'case_blocked')
        self.assertEqual(processing['state'], 'received')
        self.assertEqual(processing['case']['case_id'], 'case_demo')

    def test_process_received_execution_request_creates_local_warranted_job(self):
        from federation import FederationEnvelopeClaims

        calls = {}
        self.workspace.get_execution_job = lambda envelope_id, org_id=None: None
        self.workspace.issue_warrant = lambda *args, **kwargs: {
            'warrant_id': 'war_local_demo',
            'court_review_state': 'pending_review',
            'execution_state': 'ready',
            'expires_at': '2026-03-22T01:00:00Z',
        }
        self.workspace.get_warrant = lambda warrant_id, org_id=None: {
            'warrant_id': warrant_id,
            'court_review_state': 'pending_review',
            'execution_state': 'ready',
            'expires_at': '2026-03-22T01:00:00Z',
        }
        self.workspace.upsert_execution_job = lambda org_id, job: calls.setdefault(
            'job',
            dict(job, job_id='fej_demo'),
        )
        self.workspace.log_event = lambda *args, **kwargs: calls.setdefault('audit', []).append((args, kwargs))
        original_inbox_entry = self.workspace._federation_inbox_entry
        self.workspace._federation_inbox_entry = lambda *args, **kwargs: {
            'envelope_id': 'fed_exec_demo',
            'state': kwargs.get('state', 'received'),
        }
        try:
            claims = FederationEnvelopeClaims(
                envelope_id='fed_exec_demo',
                source_host_id='host_alpha',
                source_institution_id='org_alpha',
                target_host_id='host_beta',
                target_institution_id='org_a',
                actor_type='user',
                actor_id='user_alpha',
                session_id='ses_alpha',
                boundary_name='federation_gateway',
                identity_model='signed_host_service',
                message_type='execution_request',
                payload_hash='hash_demo',
                warrant_id='war_sender_demo',
                commitment_id='cmt_demo',
            )
            processing = self.workspace._process_received_federation_message(
                'org_a',
                claims,
                {'receipt_id': 'fedrcpt_demo', 'accepted_at': '2026-03-22T00:00:00Z'},
                payload={'task': 'demo'},
            )
        finally:
            self.workspace._federation_inbox_entry = original_inbox_entry

        self.assertTrue(processing['applied'])
        self.assertEqual(processing['reason'], 'execution_job_created')
        self.assertEqual(processing['state'], 'processed')
        self.assertEqual(processing['execution_job']['job_id'], 'fej_demo')
        self.assertEqual(processing['execution_job']['state'], 'pending_local_warrant')
        self.assertEqual(processing['receiver_warrant']['warrant_id'], 'war_local_demo')
        self.assertEqual(processing['inbox_entry']['state'], 'processed')
        self.assertEqual(calls['job']['local_warrant_id'], 'war_local_demo')
        self.assertEqual(calls['job']['sender_warrant_id'], 'war_sender_demo')
        self.assertEqual(calls['audit'][-1][0][2], 'federation_execution_job_created')

    def test_process_received_execution_request_reuses_existing_job(self):
        from federation import FederationEnvelopeClaims

        existing_job = {
            'job_id': 'fej_demo',
            'envelope_id': 'fed_exec_demo',
            'local_warrant_id': 'war_local_demo',
            'state': 'pending_local_warrant',
        }
        self.workspace.get_execution_job = lambda envelope_id, org_id=None: existing_job
        self.workspace.get_warrant = lambda warrant_id, org_id=None: {
            'warrant_id': warrant_id,
            'court_review_state': 'pending_review',
            'execution_state': 'ready',
            'expires_at': '2026-03-22T01:00:00Z',
        }
        self.workspace.issue_warrant = lambda *args, **kwargs: self.fail('should not issue duplicate warrant')
        self.workspace.upsert_execution_job = lambda *args, **kwargs: self.fail('should not upsert duplicate job')
        self.workspace.log_event = lambda *args, **kwargs: None
        original_inbox_entry = self.workspace._federation_inbox_entry
        self.workspace._federation_inbox_entry = lambda *args, **kwargs: {
            'envelope_id': 'fed_exec_demo',
            'state': kwargs.get('state', 'received'),
        }
        try:
            claims = FederationEnvelopeClaims(
                envelope_id='fed_exec_demo',
                source_host_id='host_alpha',
                source_institution_id='org_alpha',
                target_host_id='host_beta',
                target_institution_id='org_a',
                actor_type='user',
                actor_id='user_alpha',
                session_id='ses_alpha',
                boundary_name='federation_gateway',
                identity_model='signed_host_service',
                message_type='execution_request',
                payload_hash='hash_demo',
                warrant_id='war_sender_demo',
                commitment_id='cmt_demo',
            )
            processing = self.workspace._process_received_federation_message(
                'org_a',
                claims,
                {'receipt_id': 'fedrcpt_demo', 'accepted_at': '2026-03-22T00:00:00Z'},
                payload={'task': 'demo'},
            )
        finally:
            self.workspace._federation_inbox_entry = original_inbox_entry

        self.assertTrue(processing['applied'])
        self.assertEqual(processing['execution_job']['job_id'], 'fej_demo')
        self.assertEqual(processing['receiver_warrant']['warrant_id'], 'war_local_demo')

    def test_process_received_execution_request_blocks_on_case(self):
        from federation import FederationEnvelopeClaims

        self.workspace.get_execution_job = lambda envelope_id, org_id=None: None
        self.workspace.issue_warrant = lambda *args, **kwargs: self.fail('blocked execution should not issue warrant')
        original_blocking_case = self.workspace._blocking_case_for_delivery
        self.workspace._blocking_case_for_delivery = lambda **kwargs: {
            'case_id': 'case_demo',
            'claim_type': 'non_delivery',
            'status': 'open',
        }
        self.workspace.upsert_execution_job = lambda org_id, job: dict(job, job_id='fej_demo')
        self.workspace.log_event = lambda *args, **kwargs: None
        original_inbox_entry = self.workspace._federation_inbox_entry
        self.workspace._federation_inbox_entry = lambda *args, **kwargs: {
            'envelope_id': 'fed_exec_demo',
            'state': kwargs.get('state', 'received'),
        }
        try:
            claims = FederationEnvelopeClaims(
                envelope_id='fed_exec_demo',
                source_host_id='host_alpha',
                source_institution_id='org_alpha',
                target_host_id='host_beta',
                target_institution_id='org_a',
                actor_type='user',
                actor_id='user_alpha',
                session_id='ses_alpha',
                boundary_name='federation_gateway',
                identity_model='signed_host_service',
                message_type='execution_request',
                payload_hash='hash_demo',
                warrant_id='war_sender_demo',
                commitment_id='cmt_demo',
            )
            processing = self.workspace._process_received_federation_message(
                'org_a',
                claims,
                {'receipt_id': 'fedrcpt_demo', 'accepted_at': '2026-03-22T00:00:00Z'},
                payload={'task': 'demo'},
            )
        finally:
            self.workspace._blocking_case_for_delivery = original_blocking_case
            self.workspace._federation_inbox_entry = original_inbox_entry

        self.assertTrue(processing['applied'])
        self.assertEqual(processing['reason'], 'case_blocked')
        self.assertEqual(processing['execution_job']['state'], 'blocked')
        self.assertEqual(processing['case']['case_id'], 'case_demo')
        self.assertIsNone(processing['receiver_warrant'])

    def test_sync_execution_job_for_warrant_review_marks_ready(self):
        calls = {}
        self.workspace.get_execution_job_by_local_warrant = lambda warrant_id, org_id: {
            'job_id': 'fej_demo',
            'local_warrant_id': warrant_id,
            'state': 'pending_local_warrant',
            'note': 'Queued',
        }
        def _sync(org_id, warrant_id, **kwargs):
            calls['sync'] = {
                'org_id': org_id,
                'warrant_id': warrant_id,
                **kwargs,
            }
            return {
                'job_id': 'fej_demo',
                'local_warrant_id': warrant_id,
                'state': kwargs['state'],
                'note': kwargs['note'],
                'metadata': kwargs['metadata'],
            }
        self.workspace.sync_execution_job_for_local_warrant = _sync
        self.workspace.get_warrant = lambda warrant_id, org_id=None: {
            'warrant_id': warrant_id,
            'court_review_state': 'approved',
            'execution_state': 'ready',
            'expires_at': '2026-03-22T01:00:00Z',
        }

        job = self.workspace._sync_execution_job_for_warrant_review(
            'org_a',
            {
                'warrant_id': 'war_local_demo',
                'action_class': 'federated_execution',
                'boundary_name': 'federation_gateway',
                'court_review_state': 'approved',
                'execution_state': 'ready',
                'reviewed_by': 'user_owner',
                'reviewed_at': '2026-03-22T00:30:00Z',
            },
            decision='approve',
            note='Reviewed locally',
        )

        self.assertEqual(calls['sync']['state'], 'ready')
        self.assertEqual(calls['sync']['metadata']['review_decision'], 'approve')
        self.assertEqual(job['state'], 'ready')
        self.assertEqual(job['local_warrant']['court_review_state'], 'approved')

    def test_sync_execution_job_for_warrant_review_rejects_non_federated_warrant(self):
        self.workspace.get_execution_job_by_local_warrant = lambda warrant_id, org_id: self.fail('should not query job')
        self.workspace.sync_execution_job_for_local_warrant = lambda *args, **kwargs: self.fail('should not sync job')

        job = self.workspace._sync_execution_job_for_warrant_review(
            'org_a',
            {
                'warrant_id': 'war_demo',
                'action_class': 'payout_execution',
                'boundary_name': 'payouts',
                'court_review_state': 'approved',
                'execution_state': 'ready',
            },
            decision='approve',
        )

        self.assertIsNone(job)

    def test_sync_execution_job_for_warrant_review_blocks_or_rejects_local_warrant(self):
        cases = (
            ('stayed', 'stay', 'blocked'),
            ('revoked', 'revoke', 'rejected'),
        )

        for court_review_state, decision, expected_state in cases:
            with self.subTest(court_review_state=court_review_state, decision=decision):
                calls = {}
                self.workspace.get_execution_job_by_local_warrant = lambda warrant_id, org_id: {
                    'job_id': 'fej_demo',
                    'local_warrant_id': warrant_id,
                    'state': 'pending_local_warrant',
                    'note': 'Queued',
                }

                def _sync(org_id, warrant_id, **kwargs):
                    calls['sync'] = {
                        'org_id': org_id,
                        'warrant_id': warrant_id,
                        **kwargs,
                    }
                    return {
                        'job_id': 'fej_demo',
                        'local_warrant_id': warrant_id,
                        'state': kwargs['state'],
                        'note': kwargs['note'],
                        'metadata': kwargs['metadata'],
                    }

                self.workspace.sync_execution_job_for_local_warrant = _sync
                self.workspace.get_warrant = lambda warrant_id, org_id=None, state=court_review_state: {
                    'warrant_id': warrant_id,
                    'action_class': 'federated_execution',
                    'boundary_name': 'federation_gateway',
                    'court_review_state': state,
                    'execution_state': 'ready',
                    'reviewed_by': 'user_owner',
                    'reviewed_at': '2026-03-22T00:30:00Z',
                }

                job = self.workspace._sync_execution_job_for_warrant_review(
                    'org_a',
                    {
                        'warrant_id': 'war_local_demo',
                        'action_class': 'federated_execution',
                        'boundary_name': 'federation_gateway',
                        'court_review_state': court_review_state,
                        'execution_state': 'ready',
                        'reviewed_by': 'user_owner',
                        'reviewed_at': '2026-03-22T00:30:00Z',
                    },
                    decision=decision,
                    note='Reviewed locally',
                )

                self.assertEqual(calls['sync']['state'], expected_state)
                self.assertEqual(calls['sync']['metadata']['review_decision'], decision)
                self.assertEqual(job['state'], expected_state)
                self.assertEqual(job['local_warrant']['court_review_state'], court_review_state)

    def test_mutate_federation_peer_upserts_registry(self):
        from runtime_host import default_host_identity
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.workspace.FEDERATION_PEERS_FILE = os.path.join(tmp, 'federation_peers.json')
            self.workspace.load_host_identity = lambda *args, **kwargs: default_host_identity(
                host_id='host_alpha',
                role='control_host',
                federation_enabled=True,
                peer_transport='https',
                supported_boundaries=['workspace', 'cli', 'federation_gateway'],
            )
            self.workspace.load_admission_registry = lambda *args, **kwargs: {
                'source': 'file',
                'host_id': 'host_alpha',
                'institutions': {'org_a': {'status': 'admitted'}},
                'admitted_org_ids': ['org_a'],
            }
            snapshot = self.workspace._mutate_federation_peer('org_a', 'upsert', {
                'peer_host_id': 'host_beta',
                'label': 'Beta Host',
                'endpoint_url': 'http://127.0.0.1:19016',
                'shared_secret': 'beta-secret',
                'admitted_org_ids': ['org_b'],
            })
            self.assertEqual(snapshot['management_mode'], 'workspace_api_file_backed')
            self.assertEqual(snapshot['peer_count'], 1)
            self.assertEqual(snapshot['trusted_peer_ids'], ['host_beta'])
            self.assertTrue(any(peer['host_id'] == 'host_beta' for peer in snapshot['peers']))

    def test_mutate_federation_peer_refreshes_capability_snapshot(self):
        from federation import FederationPeer, upsert_peer_registry_entry
        from runtime_host import default_host_identity
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.workspace.FEDERATION_PEERS_FILE = os.path.join(tmp, 'federation_peers.json')
            host = default_host_identity(
                host_id='host_alpha',
                role='control_host',
                federation_enabled=True,
                peer_transport='https',
                supported_boundaries=['workspace', 'cli', 'federation_gateway'],
            )
            self.workspace.load_host_identity = lambda *args, **kwargs: host
            self.workspace.load_admission_registry = lambda *args, **kwargs: {
                'source': 'file',
                'host_id': 'host_alpha',
                'institutions': {'org_a': {'status': 'admitted'}},
                'admitted_org_ids': ['org_a'],
            }
            upsert_peer_registry_entry(
                self.workspace.FEDERATION_PEERS_FILE,
                'host_beta',
                host_identity=host,
                label='Beta Host',
                endpoint_url='http://127.0.0.1:19017',
                shared_secret='beta-secret',
                admitted_org_ids=['org_b'],
            )
            self.workspace.refresh_peer_registry_entry = lambda *args, **kwargs: {
                'source': 'file',
                'host_id': 'host_alpha',
                'trusted_peer_ids': ['host_beta'],
                'peers': {
                    'host_beta': FederationPeer(
                        'host_beta',
                        label='Beta Host',
                        endpoint_url='http://127.0.0.1:19017',
                        trust_state='trusted',
                        shared_secret='beta-secret',
                        admitted_org_ids=['org_b'],
                        capability_snapshot={
                            'manifest_version': 1,
                            'federation': {
                                'boundary_name': 'federation_gateway',
                            },
                        },
                        last_refreshed_at='2026-03-22T00:00:00Z',
                    ),
                },
            }
            snapshot = self.workspace._mutate_federation_peer('org_a', 'refresh', {
                'peer_host_id': 'host_beta',
                'target_org_id': 'org_b',
            })
            peer = next(peer for peer in snapshot['peers'] if peer['host_id'] == 'host_beta')
            self.assertTrue(peer['last_refreshed_at'])
            self.assertEqual(peer['capability_snapshot']['manifest_version'], 1)
            self.assertEqual(
                peer['capability_snapshot']['federation']['boundary_name'],
                'federation_gateway',
            )

    def test_mutate_federation_peer_rejects_self_host(self):
        from runtime_host import default_host_identity

        self.workspace.load_host_identity = lambda *args, **kwargs: default_host_identity(
            host_id='host_alpha',
            role='control_host',
            federation_enabled=True,
            peer_transport='https',
            supported_boundaries=['workspace', 'cli', 'federation_gateway'],
        )
        self.workspace.load_admission_registry = lambda *args, **kwargs: {
            'source': 'file',
            'host_id': 'host_alpha',
            'institutions': {'org_a': {'status': 'admitted'}},
            'admitted_org_ids': ['org_a'],
        }
        with self.assertRaises(PermissionError):
            self.workspace._mutate_federation_peer('org_a', 'upsert', {
                'peer_host_id': 'host_alpha',
                'shared_secret': 'alpha-secret',
            })

    def test_mutate_admission_adds_second_institution(self):
        from runtime_host import default_host_identity
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.workspace.RUNTIME_ADMISSION_FILE = os.path.join(tmp, 'institution_admissions.json')
            self.workspace.load_host_identity = lambda *args, **kwargs: default_host_identity(
                host_id='host_alpha',
                role='control_host',
                federation_enabled=True,
                peer_transport='https',
                supported_boundaries=['workspace', 'cli', 'federation_gateway'],
            )
            self.workspace.load_orgs = lambda: {
                'organizations': {
                    'org_a': {'id': 'org_a', 'name': 'A'},
                    'org_b': {'id': 'org_b', 'name': 'B'},
                }
            }
            snapshot = self.workspace._mutate_admission('org_a', 'admit', 'org_b')
            self.assertEqual(snapshot['management_mode'], 'workspace_api_file_backed')
            self.assertEqual(snapshot['admitted_org_ids'], ['org_a', 'org_b'])
            self.assertEqual(snapshot['institutions']['org_b']['status'], 'admitted')

    def test_mutate_admission_rejects_revoking_bound_org(self):
        from runtime_host import default_host_identity
        self.workspace.load_host_identity = lambda *args, **kwargs: default_host_identity(
            host_id='host_alpha',
            role='control_host',
            federation_enabled=True,
            peer_transport='https',
            supported_boundaries=['workspace', 'cli', 'federation_gateway'],
        )
        self.workspace.load_orgs = lambda: {
            'organizations': {
                'org_a': {'id': 'org_a', 'name': 'A'},
            }
        }
        with self.assertRaises(PermissionError):
            self.workspace._mutate_admission('org_a', 'revoke', 'org_a')

    def test_accept_federation_request_consumes_envelope(self):
        from federation import FederationAuthority
        from runtime_host import default_host_identity
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            replay_path = os.path.join(tmp, 'federation_replay.log')
            self.workspace.FEDERATION_REPLAY_FILE = replay_path
            self.workspace.FEDERATION_SIGNING_SECRET = 'alpha-secret'
            self.workspace.load_host_identity = lambda *args, **kwargs: default_host_identity(
                host_id='host_alpha',
                federation_enabled=True,
                peer_transport='https',
                supported_boundaries=['workspace', 'cli', 'federation_gateway'],
            )
            self.workspace.load_admission_registry = lambda *args, **kwargs: {
                'source': 'file',
                'host_id': 'host_alpha',
                'institutions': {'org_a': {'status': 'admitted'}},
                'admitted_org_ids': ['org_a'],
            }
            sender = FederationAuthority(
                default_host_identity(
                    host_id='host_alpha',
                    federation_enabled=True,
                    peer_transport='https',
                ),
                signing_secret='alpha-secret',
            )
            envelope = sender.issue(
                'org_a',
                'host_alpha',
                'org_a',
                'execution_request',
                payload={'task': 'demo'},
            )
            claims, snapshot = self.workspace._accept_federation_request(
                'org_a',
                envelope,
                payload={'task': 'demo'},
            )
            self.assertEqual(claims.source_host_id, 'host_alpha')
            self.assertTrue(snapshot['enabled'])
            self.assertEqual(snapshot['replay_protection']['entries'], 1)

    def test_deliver_federation_envelope_logs_sender_audit(self):
        from runtime_host import default_host_identity

        audit_events = []

        class FakeAuthority:
            def ensure_enabled(self):
                return True

            def deliver(self, *args, **kwargs):
                return {
                    'peer': {'host_id': 'host_beta', 'transport': 'https'},
                    'envelope': 'signed-envelope',
                    'claims': {
                        'envelope_id': 'fed_demo',
                        'source_host_id': 'host_alpha',
                        'source_institution_id': 'org_a',
                        'target_host_id': 'host_beta',
                        'target_institution_id': 'org_b',
                        'nonce': 'nonce_demo',
                        'boundary_name': 'federation_gateway',
                        'message_type': 'settlement_notice',
                    },
                    'receipt': {
                        'receipt_id': 'fedrcpt_demo',
                        'receiver_host_id': 'host_beta',
                        'receiver_institution_id': 'org_b',
                    },
                    'response': {
                        'accepted': True,
                        'receipt': {
                            'receipt_id': 'fedrcpt_demo',
                            'receiver_host_id': 'host_beta',
                            'receiver_institution_id': 'org_b',
                        },
                    },
                }

            def snapshot(self, *, bound_org_id='', admission_registry=None):
                return {
                    'enabled': True,
                    'bound_org_id': bound_org_id,
                    'admitted_org_ids': list((admission_registry or {}).get('admitted_org_ids', [])),
                }

        self.workspace._runtime_host_state = lambda _org_id: (
            default_host_identity(host_id='host_alpha', federation_enabled=True),
            {'admitted_org_ids': ['org_a', 'org_b']},
        )
        self.workspace._federation_authority = lambda _host: FakeAuthority()
        self.workspace.log_event = lambda *args, **kwargs: audit_events.append({
            'args': args,
            'kwargs': kwargs,
        })

        delivery, snapshot = self.workspace._deliver_federation_envelope(
            'org_a',
            'host_beta',
            'org_b',
            'settlement_notice',
            payload={'task': 'demo'},
            actor_type='user',
            actor_id='user_owner',
            session_id='ses_demo',
        )

        self.assertEqual(delivery['claims']['envelope_id'], 'fed_demo')
        self.assertEqual(delivery['receipt']['receipt_id'], 'fedrcpt_demo')
        self.assertEqual(snapshot['bound_org_id'], 'org_a')
        self.assertEqual(len(audit_events), 1)
        event = audit_events[0]
        self.assertEqual(event['args'][1], 'user_owner')
        self.assertEqual(event['args'][2], 'federation_envelope_sent')
        self.assertEqual(event['kwargs']['actor_type'], 'user')
        self.assertEqual(event['kwargs']['session_id'], 'ses_demo')
        self.assertEqual(event['kwargs']['details']['envelope_id'], 'fed_demo')
        self.assertEqual(event['kwargs']['details']['target_host_id'], 'host_beta')
        self.assertEqual(event['kwargs']['details']['receipt_id'], 'fedrcpt_demo')
        self.assertEqual(event['kwargs']['details']['receiver_host_id'], 'host_beta')

    def test_deliver_federation_envelope_logs_delivery_failure(self):
        from federation import FederationDeliveryError, FederationEnvelopeClaims
        from runtime_host import default_host_identity

        audit_events = []

        class FakeAuthority:
            def ensure_enabled(self):
                return True

            def deliver(self, *args, **kwargs):
                raise FederationDeliveryError(
                    'Peer returned HTTP 503',
                    peer_host_id='host_beta',
                    envelope='signed-envelope',
                    claims=FederationEnvelopeClaims(
                        envelope_id='fed_demo',
                        source_host_id='host_alpha',
                        source_institution_id='org_a',
                        target_host_id='host_beta',
                        target_institution_id='org_b',
                        boundary_name='federation_gateway',
                        message_type='settlement_notice',
                        nonce='nonce_demo',
                    ),
                )

        self.workspace._runtime_host_state = lambda _org_id: (
            default_host_identity(host_id='host_alpha', federation_enabled=True),
            {'admitted_org_ids': ['org_a', 'org_b']},
        )
        self.workspace._federation_authority = lambda _host: FakeAuthority()
        self.workspace.log_event = lambda *args, **kwargs: audit_events.append({
            'args': args,
            'kwargs': kwargs,
        })

        with self.assertRaises(FederationDeliveryError):
            self.workspace._deliver_federation_envelope(
                'org_a',
                'host_beta',
                'org_b',
                'settlement_notice',
                payload={'task': 'demo'},
                actor_type='user',
                actor_id='user_owner',
                session_id='ses_demo',
            )

        self.assertEqual(len(audit_events), 1)
        event = audit_events[0]
        self.assertEqual(event['args'][2], 'federation_envelope_delivery_failed')
        self.assertEqual(event['kwargs']['details']['envelope_id'], 'fed_demo')
        self.assertEqual(event['kwargs']['details']['error'], 'Peer returned HTTP 503')

    def test_deliver_federation_envelope_blocks_execution_without_warrant(self):
        from runtime_host import default_host_identity

        audit_events = []

        class FakeAuthority:
            def ensure_enabled(self):
                return True

        self.workspace._runtime_host_state = lambda _org_id: (
            default_host_identity(host_id='host_alpha', federation_enabled=True),
            {'admitted_org_ids': ['org_a', 'org_b']},
        )
        self.workspace._federation_authority = lambda _host: FakeAuthority()
        self.workspace.log_event = lambda *args, **kwargs: audit_events.append({
            'args': args,
            'kwargs': kwargs,
        })

        with self.assertRaises(PermissionError) as exc_info:
            self.workspace._deliver_federation_envelope(
                'org_a',
                'host_beta',
                'org_b',
                'execution_request',
                payload={'task': 'demo'},
                actor_type='user',
                actor_id='user_owner',
                session_id='ses_demo',
            )

        self.assertEqual(len(audit_events), 1)
        event = audit_events[0]
        self.assertEqual(event['args'][2], 'federation_warrant_blocked')
        self.assertEqual(event['kwargs']['details']['required_action_class'], 'federated_execution')
        self.assertEqual(event['kwargs']['details']['target_host_id'], 'host_beta')

    def test_deliver_federation_envelope_validates_and_marks_commitment(self):
        from runtime_host import default_host_identity

        audit_events = []
        marked = []

        class FakeAuthority:
            def ensure_enabled(self):
                return True

            def deliver(self, *args, **kwargs):
                return {
                    'peer': {'host_id': 'host_beta', 'transport': 'https'},
                    'claims': {
                        'envelope_id': 'fed_demo',
                        'source_host_id': 'host_alpha',
                        'source_institution_id': 'org_a',
                        'target_host_id': 'host_beta',
                        'target_institution_id': 'org_b',
                        'nonce': 'nonce_demo',
                        'boundary_name': 'federation_gateway',
                        'message_type': 'settlement_notice',
                        'commitment_id': 'cmt_demo',
                    },
                    'receipt': {
                        'receipt_id': 'fedrcpt_demo',
                        'receiver_host_id': 'host_beta',
                        'receiver_institution_id': 'org_b',
                    },
                    'response': {'accepted': True},
                }

            def snapshot(self, *, bound_org_id='', admission_registry=None):
                return {
                    'enabled': True,
                    'bound_org_id': bound_org_id,
                    'admitted_org_ids': list((admission_registry or {}).get('admitted_org_ids', [])),
                }

        self.workspace._runtime_host_state = lambda _org_id: (
            default_host_identity(host_id='host_alpha', federation_enabled=True),
            {'admitted_org_ids': ['org_a', 'org_b']},
        )
        self.workspace._federation_authority = lambda _host: FakeAuthority()
        self.workspace.validate_commitment_for_delivery = lambda commitment_id, **_kwargs: {
            'commitment_id': commitment_id,
            'status': 'accepted',
        }
        self.workspace.record_delivery_ref = lambda commitment_id, **kwargs: marked.append({
            'commitment_id': commitment_id,
            'kwargs': kwargs,
        })
        self.workspace.log_event = lambda *args, **kwargs: audit_events.append({
            'args': args,
            'kwargs': kwargs,
        })

        delivery, snapshot = self.workspace._deliver_federation_envelope(
            'org_a',
            'host_beta',
            'org_b',
            'settlement_notice',
            payload={'task': 'demo'},
            actor_type='user',
            actor_id='user_owner',
            session_id='ses_demo',
            commitment_id='cmt_demo',
        )

        self.assertEqual(delivery['claims']['commitment_id'], 'cmt_demo')
        self.assertEqual(snapshot['bound_org_id'], 'org_a')
        self.assertEqual(len(marked), 1)
        self.assertEqual(marked[0]['commitment_id'], 'cmt_demo')
        self.assertEqual(marked[0]['kwargs']['delivery_ref']['receipt_id'], 'fedrcpt_demo')
        self.assertEqual(audit_events[-1]['kwargs']['details']['commitment_id'], 'cmt_demo')

    def test_deliver_federation_envelope_blocks_invalid_commitment(self):
        from runtime_host import default_host_identity

        audit_events = []

        class FakeAuthority:
            def ensure_enabled(self):
                return True

        self.workspace._runtime_host_state = lambda _org_id: (
            default_host_identity(host_id='host_alpha', federation_enabled=True),
            {'admitted_org_ids': ['org_a', 'org_b']},
        )
        self.workspace._federation_authority = lambda _host: FakeAuthority()
        self.workspace.validate_commitment_for_delivery = lambda _commitment_id, **_kwargs: (_ for _ in ()).throw(
            ValueError("Commitment 'cmt_demo' is not active for federation (state=rejected)")
        )
        self.workspace.log_event = lambda *args, **kwargs: audit_events.append({
            'args': args,
            'kwargs': kwargs,
        })

        with self.assertRaises(ValueError):
            self.workspace._deliver_federation_envelope(
                'org_a',
                'host_beta',
                'org_b',
                'settlement_notice',
                payload={'task': 'demo'},
                actor_type='user',
                actor_id='user_owner',
                session_id='ses_demo',
                commitment_id='cmt_demo',
            )

        self.assertEqual(len(audit_events), 1)
        event = audit_events[0]
        self.assertEqual(event['args'][2], 'federation_commitment_blocked')
        self.assertEqual(event['kwargs']['details']['commitment_id'], 'cmt_demo')

    def test_deliver_federation_envelope_blocks_open_case(self):
        from runtime_host import default_host_identity

        audit_events = []

        class FakeAuthority:
            def ensure_enabled(self):
                return True

        self.workspace._runtime_host_state = lambda _org_id: (
            default_host_identity(host_id='host_alpha', federation_enabled=True),
            {'admitted_org_ids': ['org_a', 'org_b']},
        )
        self.workspace._federation_authority = lambda _host: FakeAuthority()
        self.workspace.validate_commitment_for_delivery = lambda commitment_id, **_kwargs: {
            'commitment_id': commitment_id,
            'status': 'accepted',
        }
        self.workspace.blocking_commitment_case = lambda commitment_id, **_kwargs: {
            'case_id': 'case_demo',
            'claim_type': 'breach_of_commitment',
            'status': 'open',
            'linked_commitment_id': commitment_id,
        }
        self.workspace.log_event = lambda *args, **kwargs: audit_events.append({
            'args': args,
            'kwargs': kwargs,
        })

        with self.assertRaises(PermissionError) as exc_info:
            self.workspace._deliver_federation_envelope(
                'org_a',
                'host_beta',
                'org_b',
                'settlement_notice',
                payload={'task': 'demo'},
                actor_type='user',
                actor_id='user_owner',
                session_id='ses_demo',
                commitment_id='cmt_demo',
            )

        self.assertEqual(exc_info.exception.case_record['case_id'], 'case_demo')
        self.assertEqual(exc_info.exception.federation_peer['peer_host_id'], 'host_beta')
        self.assertEqual(exc_info.exception.federation_peer['reason'], 'peer_not_registered')
        self.assertEqual(len(audit_events), 1)
        event = audit_events[0]
        self.assertEqual(event['args'][2], 'federation_case_blocked')
        self.assertEqual(event['kwargs']['details']['case_id'], 'case_demo')
        self.assertEqual(event['kwargs']['details']['commitment_id'], 'cmt_demo')

    def test_maybe_suspend_peer_for_case_updates_trust(self):
        from runtime_host import default_host_identity

        audit_events = []
        self.workspace._runtime_host_state = lambda _org_id: (
            default_host_identity(host_id='host_alpha', federation_enabled=True, peer_transport='https'),
            {'admitted_org_ids': ['org_a', 'org_b']},
        )
        self.workspace.ensure_case_for_delivery_failure = lambda claim_type, actor_id, **kwargs: ({
            'case_id': 'case_demo',
            'claim_type': claim_type,
            'status': 'open',
            'linked_commitment_id': kwargs.get('linked_commitment_id', ''),
            'target_host_id': kwargs.get('target_host_id', ''),
        }, True)
        self.workspace.set_peer_trust_state = lambda *_args, **_kwargs: {
            'source': 'file',
            'host_id': 'host_alpha',
            'trusted_peer_ids': [],
            'peers': {
                'host_beta': {
                    'host_id': 'host_beta',
                    'trust_state': 'suspended',
                },
            },
        }
        self.workspace.log_event = lambda *args, **kwargs: audit_events.append({
            'args': args,
            'kwargs': kwargs,
        })

        result = self.workspace._maybe_suspend_peer_for_case(
            {
                'case_id': 'case_demo',
                'claim_type': 'misrouted_execution',
                'status': 'open',
                'target_host_id': 'host_beta',
            },
            'user_owner',
            org_id='org_a',
            session_id='ses_demo',
        )

        self.assertTrue(result['applied'])
        self.assertEqual(result['peer_host_id'], 'host_beta')
        self.assertEqual(result['trust_state'], 'suspended')
        self.assertEqual(audit_events[0]['args'][2], 'federation_peer_auto_suspended')

    def test_maybe_stay_warrant_for_case_stays_ready_warrant(self):
        audit_events = []
        self.workspace.list_warrants = lambda org_id=None, **_kwargs: [
            {
                'warrant_id': 'war_demo',
                'court_review_state': 'approved',
                'execution_state': 'ready',
            }
        ]
        self.workspace.review_warrant = lambda warrant_id, decision, by, **_kwargs: {
            'warrant_id': warrant_id,
            'court_review_state': 'stayed',
            'execution_state': 'ready',
            'reviewed_by': by,
        }
        self.workspace.log_event = lambda *args, **kwargs: audit_events.append({
            'args': args,
            'kwargs': kwargs,
        })

        warrant = self.workspace._maybe_stay_warrant_for_case(
            {
                'case_id': 'case_demo',
                'claim_type': 'misrouted_execution',
                'linked_warrant_id': 'war_demo',
            },
            'user_owner',
            org_id='org_a',
            session_id='ses_demo',
            note='Receipt contradiction',
        )

        self.assertTrue(warrant['applied'])
        self.assertEqual(warrant['warrant_id'], 'war_demo')
        self.assertEqual(warrant['court_review_state'], 'stayed')
        self.assertEqual(audit_events[0]['args'][2], 'warrant_stayed_for_case')
        self.assertEqual(audit_events[0]['kwargs']['details']['case_id'], 'case_demo')

    def test_maybe_block_commitment_settlement_returns_case_and_warrant(self):
        audit_events = []
        self.workspace.blocking_commitment_case = lambda commitment_id, **_kwargs: {
            'case_id': 'case_demo',
            'claim_type': 'non_delivery',
            'status': 'open',
            'linked_commitment_id': commitment_id,
            'linked_warrant_id': 'war_demo',
        }
        self.workspace.list_warrants = lambda org_id=None, **_kwargs: [
            {
                'warrant_id': 'war_demo',
                'court_review_state': 'approved',
                'execution_state': 'ready',
            }
        ]
        self.workspace.review_warrant = lambda warrant_id, decision, by, **_kwargs: {
            'warrant_id': warrant_id,
            'court_review_state': 'stayed',
            'execution_state': 'ready',
            'reviewed_by': by,
        }
        self.workspace.log_event = lambda *args, **kwargs: audit_events.append({
            'args': args,
            'kwargs': kwargs,
        })

        case_record, warrant = self.workspace._maybe_block_commitment_settlement(
            'cmt_demo',
            'user_owner',
            org_id='org_a',
            session_id='ses_demo',
            note='Do not settle while case is open',
        )

        self.assertEqual(case_record['case_id'], 'case_demo')
        self.assertTrue(warrant['applied'])
        self.assertEqual(warrant['warrant_id'], 'war_demo')
        self.assertEqual(audit_events[-1]['args'][2], 'commitment_settlement_blocked')
        self.assertEqual(audit_events[-1]['kwargs']['resource'], 'cmt_demo')

    def test_maybe_open_case_for_delivery_failure_creates_case_and_suspends_peer(self):
        from federation import FederationDeliveryError, FederationEnvelopeClaims
        from runtime_host import default_host_identity

        audit_events = []
        self.workspace._runtime_host_state = lambda _org_id: (
            default_host_identity(host_id='host_alpha', federation_enabled=True, peer_transport='https'),
            {'admitted_org_ids': ['org_a', 'org_b']},
        )
        self.workspace.ensure_case_for_delivery_failure = lambda claim_type, actor_id, **kwargs: ({
            'case_id': 'case_demo',
            'claim_type': claim_type,
            'status': 'open',
            'linked_commitment_id': kwargs.get('linked_commitment_id', ''),
            'target_host_id': kwargs.get('target_host_id', ''),
        }, True)
        self.workspace.set_peer_trust_state = lambda *_args, **_kwargs: {
            'source': 'file',
            'host_id': 'host_alpha',
            'trusted_peer_ids': [],
            'peers': {
                'host_beta': {
                    'host_id': 'host_beta',
                    'trust_state': 'suspended',
                },
            },
        }
        self.workspace.log_event = lambda *args, **kwargs: audit_events.append({
            'args': args,
            'kwargs': kwargs,
        })
        error = FederationDeliveryError(
            "Peer host 'host_beta' returned receipt receiver_host_id 'host_wrong'",
            peer_host_id='host_beta',
            claims=FederationEnvelopeClaims(
                envelope_id='fed_demo',
                source_host_id='host_alpha',
                source_institution_id='org_a',
                target_host_id='host_beta',
                target_institution_id='org_b',
                message_type='execution_request',
            ),
        )

        case_record, federation_peer = self.workspace._maybe_open_case_for_delivery_failure(
            error,
            'user_owner',
            org_id='org_a',
            target_host_id='host_beta',
            target_institution_id='org_b',
            commitment_id='cmt_demo',
            warrant_id='war_demo',
            session_id='ses_demo',
        )

        self.assertEqual(case_record['claim_type'], 'misrouted_execution')
        self.assertEqual(case_record['linked_commitment_id'], 'cmt_demo')
        self.assertTrue(federation_peer['applied'])
        self.assertEqual(federation_peer['trust_state'], 'suspended')
        self.assertEqual(audit_events[0]['args'][2], 'case_opened')
        self.assertEqual(audit_events[1]['args'][2], 'federation_peer_auto_suspended')


if __name__ == '__main__':
    unittest.main()
