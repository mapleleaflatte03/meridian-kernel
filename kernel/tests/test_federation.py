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
