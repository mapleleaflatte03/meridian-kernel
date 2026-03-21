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

    def test_missing_org_fails_cleanly(self):
        with self.assertRaises(SystemExit) as ctx:
            treasury.load_wallets(f'org_missing_{uuid.uuid4().hex[:8]}')
        self.assertIn('is not initialized', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
