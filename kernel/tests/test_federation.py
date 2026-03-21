#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)


class FederationTests(unittest.TestCase):
    def test_issue_and_validate_self_signed_envelope(self):
        from federation import FederationAuthority
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            role='control_host',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(host, signing_secret='alpha-secret')
        envelope = authority.issue(
            'org_alpha',
            'host_alpha',
            'org_alpha',
            'execution_request',
            payload={'task': 'demo'},
        )
        claims = authority.validate(
            envelope,
            payload={'task': 'demo'},
            expected_target_host_id='host_alpha',
            expected_target_org_id='org_alpha',
            expected_boundary_name='federation_gateway',
        )
        self.assertEqual(claims.source_host_id, 'host_alpha')
        self.assertEqual(claims.target_institution_id, 'org_alpha')

    def test_validate_rejects_wrong_target_host(self):
        from federation import FederationAuthority, FederationValidationError
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(host, signing_secret='alpha-secret')
        envelope = authority.issue(
            'org_alpha',
            'host_beta',
            'org_beta',
            'execution_request',
            payload={'task': 'demo'},
        )
        with self.assertRaises(FederationValidationError):
            authority.validate(
                envelope,
                payload={'task': 'demo'},
                expected_target_host_id='host_alpha',
            )

    def test_accept_rejects_replay_across_restart(self):
        from federation import FederationAuthority, ReplayStore, FederationReplayError
        from runtime_host import default_host_identity

        with tempfile.TemporaryDirectory() as tmp:
            replay_path = os.path.join(tmp, 'federation_replay.log')
            host = default_host_identity(
                host_id='host_alpha',
                federation_enabled=True,
                peer_transport='https',
            )
            issuer = FederationAuthority(host, signing_secret='alpha-secret')
            envelope = issuer.issue(
                'org_alpha',
                'host_alpha',
                'org_alpha',
                'execution_request',
                payload={'task': 'demo'},
            )

            receiver1 = FederationAuthority(
                host,
                signing_secret='alpha-secret',
                replay_store=ReplayStore(replay_path),
            )
            claims = receiver1.accept(
                envelope,
                payload={'task': 'demo'},
                expected_target_host_id='host_alpha',
                expected_target_org_id='org_alpha',
            )
            self.assertTrue(claims.envelope_id.startswith('fed_'))

            receiver2 = FederationAuthority(
                host,
                signing_secret='alpha-secret',
                replay_store=ReplayStore(replay_path),
            )
            with self.assertRaises(FederationReplayError):
                receiver2.accept(
                    envelope,
                    payload={'task': 'demo'},
                    expected_target_host_id='host_alpha',
                    expected_target_org_id='org_alpha',
                )

    def test_validate_uses_trusted_peer_registry(self):
        from federation import FederationAuthority, load_peer_registry
        from runtime_host import default_host_identity

        with tempfile.TemporaryDirectory() as tmp:
            peers_path = os.path.join(tmp, 'federation_peers.json')
            with open(peers_path, 'w') as f:
                json.dump({
                    'host_id': 'host_beta',
                    'peers': {
                        'host_alpha': {
                            'label': 'Alpha Host',
                            'transport': 'https',
                            'endpoint_url': 'http://127.0.0.1:19011',
                            'trust_state': 'trusted',
                            'shared_secret': 'alpha-secret',
                            'admitted_org_ids': ['org_alpha'],
                        }
                    },
                }, f)

            source_host = default_host_identity(
                host_id='host_alpha',
                federation_enabled=True,
                peer_transport='https',
            )
            target_host = default_host_identity(
                host_id='host_beta',
                role='witness_host',
                federation_enabled=True,
                peer_transport='https',
            )
            sender = FederationAuthority(source_host, signing_secret='alpha-secret')
            receiver = FederationAuthority(
                target_host,
                signing_secret='beta-secret',
                peer_registry=load_peer_registry(peers_path, host_identity=target_host),
            )
            envelope = sender.issue(
                'org_alpha',
                'host_beta',
                'org_beta',
                'settlement_notice',
                payload={'tx_ref': '0xabc'},
            )
            claims = receiver.validate(
                envelope,
                payload={'tx_ref': '0xabc'},
                expected_target_host_id='host_beta',
                expected_target_org_id='org_beta',
            )
            self.assertEqual(claims.source_host_id, 'host_alpha')
            self.assertEqual(claims.message_type, 'settlement_notice')

    def test_load_peer_registry_includes_endpoint_url(self):
        from federation import load_peer_registry
        from runtime_host import default_host_identity

        with tempfile.TemporaryDirectory() as tmp:
            peers_path = os.path.join(tmp, 'federation_peers.json')
            with open(peers_path, 'w') as f:
                json.dump({
                    'host_id': 'host_alpha',
                    'peers': {
                        'host_beta': {
                            'label': 'Beta Host',
                            'transport': 'https',
                            'base_url': 'http://127.0.0.1:19012',
                            'trust_state': 'trusted',
                            'shared_secret': 'beta-secret',
                        }
                    },
                }, f)

            registry = load_peer_registry(
                peers_path,
                host_identity=default_host_identity(host_id='host_alpha'),
            )
            peer = registry['peers']['host_beta']
            self.assertEqual(peer.endpoint_url, 'http://127.0.0.1:19012')
            self.assertEqual(peer.receive_url, 'http://127.0.0.1:19012/api/federation/receive')

    def test_deliver_posts_to_trusted_peer_endpoint(self):
        from federation import FederationAuthority, FederationPeer
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(
            host,
            signing_secret='alpha-secret',
            peer_registry={
                'source': 'test',
                'host_id': 'host_alpha',
                'trusted_peer_ids': ['host_beta'],
                'peers': {
                    'host_beta': FederationPeer(
                        'host_beta',
                        transport='https',
                        endpoint_url='http://127.0.0.1:19013',
                        trust_state='trusted',
                        shared_secret='beta-secret',
                        admitted_org_ids=['org_beta'],
                    ),
                },
            },
        )

        calls = {}

        def fake_post(url, data):
            calls['url'] = url
            calls['data'] = data
            return {'accepted': True}

        result = authority.deliver(
            'host_beta',
            'org_alpha',
            'org_beta',
            'execution_request',
            payload={'task': 'demo'},
            http_post=fake_post,
            http_get=lambda _url: {
                'host_identity': {'host_id': 'host_beta'},
                'admission': {'admitted_org_ids': ['org_beta']},
                'service_registry': {
                    'federation_gateway': {
                        'identity_model': 'signed_host_service',
                        'supports_institution_routing': True,
                    },
                },
                'federation': {
                    'enabled': True,
                    'boundary_name': 'federation_gateway',
                    'identity_model': 'signed_host_service',
                },
            },
        )
        self.assertEqual(calls['url'], 'http://127.0.0.1:19013/api/federation/receive')
        self.assertIn('envelope', calls['data'])
        self.assertEqual(calls['data']['payload'], {'task': 'demo'})
        self.assertEqual(result['response'], {'accepted': True})
        self.assertEqual(result['peer']['host_id'], 'host_beta')
        self.assertEqual(result['claims']['target_host_id'], 'host_beta')
        self.assertEqual(result['claims']['target_institution_id'], 'org_beta')
        self.assertEqual(result['claims']['message_type'], 'execution_request')

    def test_deliver_rejects_peer_without_endpoint_url(self):
        from federation import FederationAuthority, FederationDeliveryError, FederationPeer
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(
            host,
            signing_secret='alpha-secret',
            peer_registry={
                'source': 'test',
                'host_id': 'host_alpha',
                'trusted_peer_ids': ['host_beta'],
                'peers': {
                    'host_beta': FederationPeer(
                        'host_beta',
                        transport='https',
                        trust_state='trusted',
                        shared_secret='beta-secret',
                    ),
                },
            },
        )

        with self.assertRaises(FederationDeliveryError) as ctx:
            authority.deliver(
                'host_beta',
                'org_alpha',
                'org_beta',
                'execution_request',
                payload={'task': 'demo'},
            )
        self.assertEqual(ctx.exception.peer_host_id, '')
        self.assertEqual(ctx.exception.response, None)

    def test_deliver_failure_carries_claims(self):
        from federation import FederationAuthority, FederationDeliveryError, FederationPeer
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(
            host,
            signing_secret='alpha-secret',
            peer_registry={
                'source': 'test',
                'host_id': 'host_alpha',
                'trusted_peer_ids': ['host_beta'],
                'peers': {
                    'host_beta': FederationPeer(
                        'host_beta',
                        transport='https',
                        endpoint_url='http://127.0.0.1:19013',
                        trust_state='trusted',
                        shared_secret='beta-secret',
                        admitted_org_ids=['org_beta'],
                    ),
                },
            },
        )

        def fake_post(_url, _data):
            raise RuntimeError('network down')

        with self.assertRaises(FederationDeliveryError) as ctx:
            authority.deliver(
                'host_beta',
                'org_alpha',
                'org_beta',
                'execution_request',
                payload={'task': 'demo'},
                http_post=fake_post,
                http_get=lambda _url: {
                    'host_identity': {'host_id': 'host_beta'},
                    'admission': {'admitted_org_ids': ['org_beta']},
                    'service_registry': {
                        'federation_gateway': {
                            'identity_model': 'signed_host_service',
                            'supports_institution_routing': True,
                        },
                    },
                    'federation': {
                        'enabled': True,
                        'boundary_name': 'federation_gateway',
                        'identity_model': 'signed_host_service',
                    },
                },
            )

        self.assertEqual(ctx.exception.peer_host_id, 'host_beta')
        self.assertTrue(ctx.exception.envelope)
        self.assertEqual(ctx.exception.claims.target_host_id, 'host_beta')
        self.assertEqual(ctx.exception.claims.target_institution_id, 'org_beta')
        self.assertEqual(ctx.exception.claims.message_type, 'execution_request')

    def test_upsert_peer_registry_entry_round_trips_file_backed_registry(self):
        from federation import load_peer_registry, upsert_peer_registry_entry
        from runtime_host import default_host_identity

        with tempfile.TemporaryDirectory() as tmp:
            peers_path = os.path.join(tmp, 'federation_peers.json')
            host = default_host_identity(host_id='host_alpha')
            registry = upsert_peer_registry_entry(
                peers_path,
                'host_beta',
                host_identity=host,
                label='Beta Host',
                endpoint_url='http://127.0.0.1:19014',
                shared_secret='beta-secret',
                admitted_org_ids=['org_beta', 'org_beta'],
            )
            self.assertEqual(registry['host_id'], 'host_alpha')
            self.assertEqual(registry['trusted_peer_ids'], ['host_beta'])

            reloaded = load_peer_registry(peers_path, host_identity=host)
            peer = reloaded['peers']['host_beta']
            self.assertEqual(peer.label, 'Beta Host')
            self.assertEqual(peer.receive_url, 'http://127.0.0.1:19014/api/federation/receive')
            self.assertEqual(peer.admitted_org_ids, ['org_beta'])

    def test_set_peer_trust_state_updates_snapshot_and_send_enabled(self):
        from federation import (
            FederationAuthority,
            set_peer_trust_state,
            upsert_peer_registry_entry,
        )
        from runtime_host import default_host_identity

        with tempfile.TemporaryDirectory() as tmp:
            peers_path = os.path.join(tmp, 'federation_peers.json')
            host = default_host_identity(
                host_id='host_alpha',
                federation_enabled=True,
                peer_transport='https',
            )
            registry = upsert_peer_registry_entry(
                peers_path,
                'host_beta',
                host_identity=host,
                endpoint_url='http://127.0.0.1:19015',
                shared_secret='beta-secret',
                admitted_org_ids=['org_beta'],
            )
            authority = FederationAuthority(host, signing_secret='alpha-secret', peer_registry=registry)
            self.assertTrue(authority.snapshot(bound_org_id='org_alpha')['send_enabled'])

            suspended = set_peer_trust_state(
                peers_path,
                'host_beta',
                'suspended',
                host_identity=host,
            )
            suspended_snapshot = FederationAuthority(
                host,
                signing_secret='alpha-secret',
                peer_registry=suspended,
            ).snapshot(bound_org_id='org_alpha')
            self.assertEqual(suspended_snapshot['trusted_peer_ids'], [])
            self.assertEqual(suspended_snapshot['all_peer_count'], 1)
            self.assertFalse(suspended_snapshot['send_enabled'])

    def test_preflight_delivery_validates_peer_manifest(self):
        from federation import FederationAuthority, FederationPeer
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(
            host,
            signing_secret='alpha-secret',
            peer_registry={
                'source': 'test',
                'host_id': 'host_alpha',
                'trusted_peer_ids': ['host_beta'],
                'peers': {
                    'host_beta': FederationPeer(
                        'host_beta',
                        transport='https',
                        endpoint_url='http://127.0.0.1:19017',
                        trust_state='trusted',
                        shared_secret='beta-secret',
                        admitted_org_ids=['org_beta'],
                    ),
                },
            },
        )

        manifest = authority.preflight_delivery(
            'host_beta',
            'org_beta',
            http_get=lambda _url: {
                'host_identity': {
                    'host_id': 'host_beta',
                    'role': 'institution_host',
                },
                'admission': {
                    'admitted_org_ids': ['org_beta'],
                },
                'service_registry': {
                    'federation_gateway': {
                        'identity_model': 'signed_host_service',
                        'supports_institution_routing': True,
                    },
                },
                'federation': {
                    'enabled': True,
                    'boundary_name': 'federation_gateway',
                    'identity_model': 'signed_host_service',
                },
            },
        )
        self.assertEqual(manifest['host_identity']['host_id'], 'host_beta')

    def test_preflight_delivery_rejects_manifest_without_target_org(self):
        from federation import FederationAuthority, FederationDeliveryError, FederationPeer
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(
            host,
            signing_secret='alpha-secret',
            peer_registry={
                'source': 'test',
                'host_id': 'host_alpha',
                'trusted_peer_ids': ['host_beta'],
                'peers': {
                    'host_beta': FederationPeer(
                        'host_beta',
                        transport='https',
                        endpoint_url='http://127.0.0.1:19018',
                        trust_state='trusted',
                        shared_secret='beta-secret',
                        admitted_org_ids=['org_beta'],
                    ),
                },
            },
        )

        with self.assertRaises(FederationDeliveryError):
            authority.preflight_delivery(
                'host_beta',
                'org_gamma',
                http_get=lambda _url: {
                    'host_identity': {
                        'host_id': 'host_beta',
                        'role': 'institution_host',
                    },
                    'admission': {
                        'admitted_org_ids': ['org_beta'],
                    },
                    'service_registry': {
                        'federation_gateway': {
                            'identity_model': 'signed_host_service',
                            'supports_institution_routing': True,
                        },
                    },
                    'federation': {
                        'enabled': True,
                        'boundary_name': 'federation_gateway',
                        'identity_model': 'signed_host_service',
                    },
                },
            )

    def test_snapshot_reports_disabled_without_signing_secret(self):
        from federation import FederationAuthority
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        snapshot = FederationAuthority(host, signing_secret=None).snapshot(bound_org_id='org_alpha')
        self.assertFalse(snapshot['enabled'])
        self.assertEqual(snapshot['disabled_reason'], 'signing_secret_missing')

    def test_load_peer_registry_rejects_trusted_peer_without_secret(self):
        from federation import load_peer_registry
        from runtime_host import default_host_identity

        with tempfile.TemporaryDirectory() as tmp:
            peers_path = os.path.join(tmp, 'federation_peers.json')
            with open(peers_path, 'w') as f:
                json.dump({
                    'host_id': 'host_alpha',
                    'peers': {
                        'host_beta': {
                            'trust_state': 'trusted',
                            'transport': 'https',
                        }
                    },
                }, f)
            with self.assertRaises(RuntimeError):
                load_peer_registry(peers_path, host_identity=default_host_identity(host_id='host_alpha'))


if __name__ == '__main__':
    unittest.main()
