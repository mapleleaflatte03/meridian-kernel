#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest
import uuid
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
TREASURY_PATH = ROOT / 'kernel' / 'treasury.py'
CAPSULE_PATH = ROOT / 'kernel' / 'capsule.py'
ECONOMY_DIR = ROOT / 'economy'
CAPSULES_DIR = ROOT / 'capsules'


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


treasury = _load_module('kernel_treasury_test', TREASURY_PATH)
capsule = _load_module('kernel_capsule_test_for_treasury', CAPSULE_PATH)


class TreasuryCapsuleTests(unittest.TestCase):
    def setUp(self):
        self.org_id = f'org_treasury_test_{uuid.uuid4().hex[:8]}'
        self.capsule_dir = CAPSULES_DIR / self.org_id
        capsule.init_capsule(self.org_id)

        ledger_path = pathlib.Path(capsule.capsule_path(self.org_id, 'ledger.json'))
        ledger = json.loads(ledger_path.read_text())
        ledger['updatedAt'] = '2026-03-21T00:00:00Z'
        ledger['epoch']['started_at'] = '2026-03-21T00:00:00Z'
        ledger['agents'] = {
            'atlas': {
                'name': 'Atlas',
                'role': 'analyst',
                'reputation_units': 50,
                'authority_units': 50,
                'probation': False,
                'zero_authority': False,
                'status': 'active',
            }
        }
        ledger_path.write_text(json.dumps(ledger, indent=2))
        self.default_ledger_before = json.loads((ECONOMY_DIR / 'ledger.json').read_text())

    def tearDown(self):
        shutil.rmtree(self.capsule_dir, ignore_errors=True)

    def test_contribute_owner_capital_writes_only_to_capsule(self):
        result = treasury.contribute_owner_capital(
            7.5,
            note='capsule top-up',
            by='owner',
            org_id=self.org_id,
        )

        self.assertEqual(result['amount_usd'], 7.5)
        ledger = json.loads((self.capsule_dir / 'ledger.json').read_text())
        self.assertAlmostEqual(ledger['treasury']['cash_usd'], 7.5, places=2)
        self.assertAlmostEqual(ledger['treasury']['owner_capital_contributed_usd'], 7.5, places=2)

        tx_lines = [json.loads(line) for line in (self.capsule_dir / 'transactions.jsonl').read_text().splitlines() if line.strip()]
        self.assertEqual(len(tx_lines), 1)
        self.assertEqual(tx_lines[0]['type'], 'treasury_deposit')
        self.assertEqual(tx_lines[0]['deposit_type'], 'owner_capital')

        default_ledger = json.loads((ECONOMY_DIR / 'ledger.json').read_text())
        self.assertEqual(default_ledger['treasury']['cash_usd'], self.default_ledger_before['treasury']['cash_usd'])

    def test_load_funding_sources_backfills_owner_capital_from_ledger(self):
        ledger_path = self.capsule_dir / 'ledger.json'
        ledger = json.loads(ledger_path.read_text())
        ledger['treasury']['owner_capital_contributed_usd'] = 4.25
        ledger_path.write_text(json.dumps(ledger, indent=2))

        funding = treasury.load_funding_sources(self.org_id)

        self.assertIn('src_derived_owner_capital', funding['sources'])
        derived = funding['sources']['src_derived_owner_capital']
        self.assertEqual(derived['type'], 'owner_capital')
        self.assertEqual(derived['currency'], 'USD')
        self.assertTrue(derived['metadata']['derived_from_ledger'])
        self.assertAlmostEqual(derived['amount_usd'], 4.25, places=2)

    def test_treasury_snapshot_reads_capsule_protocol_state(self):
        revenue_path = self.capsule_dir / 'revenue.json'
        revenue = json.loads(revenue_path.read_text())
        revenue['clients'] = {'client_a': {'name': 'Capsule Client', 'contact': 'capsule@test'}}
        revenue['orders'] = {
            'order_a': {
                'client': 'client_a',
                'product': 'capsule-substrate',
                'amount_usd': 3.5,
                'status': 'paid',
                'history': [],
                'created_at': '2026-03-21T00:00:00Z',
            }
        }
        revenue['receivables_usd'] = 0.0
        revenue_path.write_text(json.dumps(revenue, indent=2))

        ledger_path = self.capsule_dir / 'ledger.json'
        ledger = json.loads(ledger_path.read_text())
        ledger['treasury']['cash_usd'] = 11.0
        ledger['treasury']['total_revenue_usd'] = 3.5
        ledger['treasury']['reserve_floor_usd'] = 5.0
        ledger_path.write_text(json.dumps(ledger, indent=2))

        (self.capsule_dir / 'wallets.json').write_text(json.dumps({
            'wallets': {
                'wallet_capsule': {
                    'id': 'wallet_capsule',
                    'verification_level': 3,
                    'verification_label': 'self_custody_verified',
                    'payout_eligible': True,
                    'status': 'active',
                }
            },
            'verification_levels': {},
        }, indent=2))
        (self.capsule_dir / 'maintainers.json').write_text(json.dumps({
            'maintainers': {'m1': {'name': 'Maintainer'}},
            'roles': {},
        }, indent=2))
        (self.capsule_dir / 'contributors.json').write_text(json.dumps({
            'contributors': {'c1': {'name': 'Contributor'}},
            'contribution_types': [],
            'registration_requirements': {},
        }, indent=2))
        (self.capsule_dir / 'payout_proposals.json').write_text(json.dumps({
            'proposals': {'p1': {'status': 'submitted'}},
            'state_machine': {},
            'proposal_schema': {},
        }, indent=2))
        (self.capsule_dir / 'funding_sources.json').write_text(json.dumps({
            'sources': {'s1': {'type': 'owner_capital'}},
            'source_types': {},
        }, indent=2))

        snapshot = treasury.treasury_snapshot(self.org_id)

        self.assertEqual(snapshot['balance_usd'], 11.0)
        self.assertEqual(snapshot['total_revenue_usd'], 3.5)
        self.assertEqual(snapshot['clients'], 1)
        self.assertEqual(snapshot['paid_orders'], 1)
        self.assertEqual(snapshot['protocol']['wallet_count'], 1)
        self.assertEqual(snapshot['protocol']['payout_eligible_wallets'], 1)
        self.assertEqual(snapshot['protocol']['maintainer_count'], 1)
        self.assertEqual(snapshot['protocol']['contributor_count'], 1)
        self.assertEqual(snapshot['protocol']['pending_proposals'], 1)
        self.assertEqual(snapshot['protocol']['funding_sources'], 1)

    def test_load_wallets_migrates_legacy_registry_for_founding_alias(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            economy_dir = tmpdir / 'economy'
            economy_dir.mkdir()
            legacy_treasury = tmpdir / 'treasury'
            legacy_treasury.mkdir()
            legacy_wallets = legacy_treasury / 'wallets.json'
            legacy_payload = {
                'wallets': {'legacy_wallet': {'id': 'legacy_wallet', 'status': 'active'}},
                'verification_levels': {},
            }
            legacy_wallets.write_text(json.dumps(legacy_payload, indent=2))

            def fake_capsule_path(org_id, filename):
                return str(economy_dir / filename)

            with mock.patch.object(treasury, 'ECONOMY_DIR', str(economy_dir)), \
                 mock.patch.object(treasury, 'LEGACY_TREASURY_DIR', str(legacy_treasury)), \
                 mock.patch.object(treasury, 'capsule_path', side_effect=fake_capsule_path):
                wallets = treasury.load_wallets('org_b7d95bae')

            migrated_path = economy_dir / 'wallets.json'
            self.assertTrue(migrated_path.exists())
            self.assertIn('legacy_wallet', wallets['wallets'])

    def test_payout_proposal_lifecycle_executes_against_capsule_state(self):
        ledger_path = self.capsule_dir / 'ledger.json'
        ledger = json.loads(ledger_path.read_text())
        ledger['treasury']['cash_usd'] = 120.0
        ledger['treasury']['reserve_floor_usd'] = 50.0
        ledger_path.write_text(json.dumps(ledger, indent=2))

        (self.capsule_dir / 'wallets.json').write_text(json.dumps({
            'wallets': {
                'wallet_exec': {
                    'id': 'wallet_exec',
                    'verification_level': 3,
                    'verification_label': 'self_custody_verified',
                    'payout_eligible': True,
                    'status': 'active',
                }
            },
            'verification_levels': {},
        }, indent=2))
        (self.capsule_dir / 'contributors.json').write_text(json.dumps({
            'contributors': {
                'contrib_exec': {
                    'id': 'contrib_exec',
                    'name': 'Contributor Exec',
                    'payout_wallet_id': 'wallet_exec',
                }
            },
            'contribution_types': ['code'],
            'registration_requirements': {},
        }, indent=2))

        proposal = treasury.create_payout_proposal(
            'contrib_exec',
            12.0,
            'code',
            proposed_by='user:proposer',
            org_id=self.org_id,
            evidence={'pr_urls': ['https://example.test/pr/1']},
        )
        proposal = treasury.submit_payout_proposal(
            proposal['proposal_id'],
            'user:proposer',
            org_id=self.org_id,
        )
        proposal = treasury.review_payout_proposal(
            proposal['proposal_id'],
            'user:reviewer',
            org_id=self.org_id,
        )
        proposal = treasury.approve_payout_proposal(
            proposal['proposal_id'],
            'user:owner',
            org_id=self.org_id,
        )
        proposal = treasury.open_payout_dispute_window(
            proposal['proposal_id'],
            'user:owner',
            org_id=self.org_id,
            dispute_window_hours=0,
        )
        proposal = treasury.execute_payout_proposal(
            proposal['proposal_id'],
            'user:owner',
            org_id=self.org_id,
            warrant_id='war_exec_123',
            tx_hash='tx_demo_hash',
        )

        self.assertEqual(proposal['status'], 'executed')
        self.assertEqual(proposal['warrant_id'], 'war_exec_123')
        self.assertEqual(proposal['tx_hash'], 'tx_demo_hash')
        self.assertTrue(proposal['execution_refs']['tx_ref'].startswith('ptx_'))
        self.assertEqual(proposal['execution_refs']['proof_type'], 'ledger_transaction')
        self.assertEqual(proposal['execution_refs']['verification_state'], 'host_ledger_final')
        self.assertEqual(proposal['execution_refs']['finality_state'], 'host_local_final')
        self.assertEqual(proposal['execution_refs']['proof']['mode'], 'institution_transactions_journal')

        summary = treasury.payout_proposal_summary(self.org_id)
        self.assertEqual(summary['executed'], 1)
        self.assertEqual(summary['requested_usd'], 12.0)
        self.assertEqual(summary['executed_usd'], 12.0)

        ledger = json.loads(ledger_path.read_text())
        self.assertAlmostEqual(ledger['treasury']['cash_usd'], 108.0, places=2)
        self.assertAlmostEqual(ledger['treasury']['expenses_recorded_usd'], 12.0, places=2)

        tx_lines = [json.loads(line) for line in (self.capsule_dir / 'transactions.jsonl').read_text().splitlines() if line.strip()]
        self.assertEqual(tx_lines[-1]['type'], 'payout_execution')
        self.assertEqual(tx_lines[-1]['proposal_id'], proposal['proposal_id'])
        self.assertEqual(tx_lines[-1]['warrant_id'], 'war_exec_123')
        self.assertEqual(tx_lines[-1]['verification_state'], 'host_ledger_final')

    def test_create_payout_proposal_blocks_ineligible_wallet(self):
        (self.capsule_dir / 'wallets.json').write_text(json.dumps({
            'wallets': {
                'wallet_blocked': {
                    'id': 'wallet_blocked',
                    'verification_level': 2,
                    'verification_label': 'exchange_linked',
                    'payout_eligible': False,
                    'status': 'active',
                }
            },
            'verification_levels': {},
        }, indent=2))
        (self.capsule_dir / 'contributors.json').write_text(json.dumps({
            'contributors': {
                'contrib_blocked': {
                    'id': 'contrib_blocked',
                    'name': 'Contributor Blocked',
                    'payout_wallet_id': 'wallet_blocked',
                }
            },
            'contribution_types': ['code'],
            'registration_requirements': {},
        }, indent=2))

        with self.assertRaises(PermissionError):
            treasury.create_payout_proposal(
                'contrib_blocked',
                5.0,
                'code',
                proposed_by='user:proposer',
                org_id=self.org_id,
                evidence={'description': 'bad wallet should fail'},
            )

    def test_execute_payout_proposal_rejects_disabled_settlement_adapter(self):
        (self.capsule_dir / 'wallets.json').write_text(json.dumps({
            'wallets': {
                'wallet_exec': {
                    'id': 'wallet_exec',
                    'verification_level': 3,
                    'verification_label': 'self_custody_verified',
                    'payout_eligible': True,
                    'status': 'active',
                }
            },
            'verification_levels': {},
        }, indent=2))
        (self.capsule_dir / 'contributors.json').write_text(json.dumps({
            'contributors': {
                'contrib_exec': {
                    'id': 'contrib_exec',
                    'name': 'Contributor Exec',
                    'payout_wallet_id': 'wallet_exec',
                }
            },
            'contribution_types': ['code'],
            'registration_requirements': {},
        }, indent=2))
        proposal = treasury.create_payout_proposal(
            'contrib_exec',
            2.0,
            'code',
            proposed_by='user:proposer',
            org_id=self.org_id,
            evidence={'description': 'adapter gate'},
            settlement_adapter='base_usdc_x402',
        )
        proposal = treasury.submit_payout_proposal(
            proposal['proposal_id'],
            'user:proposer',
            org_id=self.org_id,
        )
        proposal = treasury.review_payout_proposal(
            proposal['proposal_id'],
            'user:reviewer',
            org_id=self.org_id,
        )
        proposal = treasury.approve_payout_proposal(
            proposal['proposal_id'],
            'user:owner',
            org_id=self.org_id,
        )
        proposal = treasury.open_payout_dispute_window(
            proposal['proposal_id'],
            'user:owner',
            org_id=self.org_id,
            dispute_window_hours=0,
        )
        with self.assertRaises(PermissionError):
            treasury.execute_payout_proposal(
                proposal['proposal_id'],
                'user:owner',
                org_id=self.org_id,
                warrant_id='war_disabled_adapter',
                settlement_adapter='base_usdc_x402',
                tx_hash='0xdeadbeef',
                settlement_proof={'reference': 'demo-proof'},
            )

    def test_execute_payout_proposal_disabled_adapter_is_atomic(self):
        (self.capsule_dir / 'wallets.json').write_text(json.dumps({
            'wallets': {
                'wallet_exec': {
                    'id': 'wallet_exec',
                    'verification_level': 3,
                    'verification_label': 'self_custody_verified',
                    'payout_eligible': True,
                    'status': 'active',
                }
            },
            'verification_levels': {},
        }, indent=2))
        (self.capsule_dir / 'contributors.json').write_text(json.dumps({
            'contributors': {
                'contrib_exec': {
                    'id': 'contrib_exec',
                    'name': 'Contributor Exec',
                    'payout_wallet_id': 'wallet_exec',
                }
            },
            'contribution_types': ['code'],
            'registration_requirements': {},
        }, indent=2))
        proposal = treasury.create_payout_proposal(
            'contrib_exec',
            2.0,
            'code',
            proposed_by='user:proposer',
            org_id=self.org_id,
            evidence={'description': 'adapter atomicity gate'},
            settlement_adapter='base_usdc_x402',
        )
        proposal = treasury.submit_payout_proposal(
            proposal['proposal_id'],
            'user:proposer',
            org_id=self.org_id,
        )
        proposal = treasury.review_payout_proposal(
            proposal['proposal_id'],
            'user:reviewer',
            org_id=self.org_id,
        )
        proposal = treasury.approve_payout_proposal(
            proposal['proposal_id'],
            'user:owner',
            org_id=self.org_id,
        )
        proposal = treasury.open_payout_dispute_window(
            proposal['proposal_id'],
            'user:owner',
            org_id=self.org_id,
            dispute_window_hours=0,
        )
        ledger_path = self.capsule_dir / 'ledger.json'
        tx_path = self.capsule_dir / 'transactions.jsonl'
        ledger_before = json.loads(ledger_path.read_text())
        tx_lines_before = [line for line in tx_path.read_text().splitlines() if line.strip()]

        with self.assertRaises(PermissionError):
            treasury.execute_payout_proposal(
                proposal['proposal_id'],
                'user:owner',
                org_id=self.org_id,
                warrant_id='war_disabled_adapter_atomic',
                settlement_adapter='base_usdc_x402',
                tx_hash='0xdeadbeef',
                settlement_proof={'reference': 'demo-proof'},
            )

        ledger_after = json.loads(ledger_path.read_text())
        tx_lines_after = [line for line in tx_path.read_text().splitlines() if line.strip()]
        self.assertEqual(
            ledger_after['treasury']['cash_usd'],
            ledger_before['treasury']['cash_usd'],
        )
        self.assertEqual(
            ledger_after['treasury'].get('expenses_recorded_usd', 0.0),
            ledger_before['treasury'].get('expenses_recorded_usd', 0.0),
        )
        self.assertEqual(tx_lines_after, tx_lines_before)
        proposal_after = treasury.get_payout_proposal(proposal['proposal_id'], org_id=self.org_id)
        self.assertEqual(proposal_after['status'], 'dispute_window')

    def test_preflight_settlement_adapter_accepts_internal_ledger(self):
        result = treasury.preflight_settlement_adapter(
            'internal_ledger',
            org_id=self.org_id,
            host_supported_adapters=['internal_ledger'],
        )
        self.assertTrue(result['known'])
        self.assertTrue(result['preflight_ok'])
        self.assertTrue(result['can_execute_now'])
        self.assertTrue(result['execution_enabled'])
        self.assertTrue(result['host_supported'])
        self.assertEqual(result['normalized_proof']['proof']['mode'], 'institution_transactions_journal')

    def test_preflight_settlement_adapter_reports_disabled_adapter(self):
        result = treasury.preflight_settlement_adapter(
            'base_usdc_x402',
            org_id=self.org_id,
            currency='USDC',
            tx_hash='0xdeadbeef',
            settlement_proof={'reference': 'demo-proof'},
            host_supported_adapters=['internal_ledger'],
        )
        self.assertTrue(result['known'])
        self.assertFalse(result['preflight_ok'])
        self.assertFalse(result['can_execute_now'])
        self.assertEqual(result['error_type'], 'permission_error')
        self.assertIn('not enabled', result['error'])

    def test_missing_org_fails_cleanly(self):
        with self.assertRaises(SystemExit) as ctx:
            treasury.load_wallets(f'org_missing_{uuid.uuid4().hex[:8]}')
        self.assertIn('is not initialized', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
