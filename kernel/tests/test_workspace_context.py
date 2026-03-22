#!/usr/bin/env python3
import importlib.util
import os
import unittest
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
        self.assertTrue(permissions['/api/federation/send']['allowed'])
        self.assertFalse(permissions['/api/federation/peers/refresh']['allowed'])
        self.assertEqual(permissions['/api/federation/peers/refresh']['required_role'], 'owner')

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
        ctx = self.workspace._resolve_workspace_context()
        status = self.workspace.api_status(institution_context=ctx)
        self.assertEqual(status['runtime_core']['institution_context']['org_id'], 'org_a')
        self.assertTrue(status['runtime_core']['service_registry']['workspace']['supports_institution_routing'])
        self.assertTrue(status['runtime_core']['service_registry']['federation_gateway']['supports_institution_routing'])
        self.assertTrue(status['runtime_core']['admission']['additional_institutions_allowed'])
        self.assertEqual(status['runtime_core']['admission']['management_mode'], 'workspace_api_file_backed')
        self.assertTrue(status['runtime_core']['admission']['mutation_enabled'])
        self.assertEqual(status['runtime_core']['host_identity']['host_id'], 'host_alpha')
        self.assertEqual(status['runtime_core']['admission']['admitted_org_ids'], ['org_a', 'org_b'])
        self.assertIn('federation', status['runtime_core'])

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
                        'message_type': 'execution_request',
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
            'execution_request',
            payload={'task': 'demo'},
            actor_type='user',
            actor_id='user_owner',
            session_id='ses_demo',
        )

        self.assertEqual(delivery['claims']['envelope_id'], 'fed_demo')
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
                        message_type='execution_request',
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
                'execution_request',
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


if __name__ == '__main__':
    unittest.main()
