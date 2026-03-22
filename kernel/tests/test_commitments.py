#!/usr/bin/env python3
import importlib.util
import pathlib
import shutil
import unittest
import uuid


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMITMENTS_PATH = ROOT / 'kernel' / 'commitments.py'
CAPSULE_PATH = ROOT / 'kernel' / 'capsule.py'
CAPSULES_DIR = ROOT / 'capsules'


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


commitments = _load_module('kernel_commitments_test', COMMITMENTS_PATH)
capsule = _load_module('kernel_capsule_test_for_commitments', CAPSULE_PATH)


class CommitmentCapsuleTests(unittest.TestCase):
    def setUp(self):
        self.org_id = f'org_commitment_test_{uuid.uuid4().hex[:8]}'
        self.capsule_dir = CAPSULES_DIR / self.org_id
        capsule.init_capsule(self.org_id)

    def tearDown(self):
        shutil.rmtree(self.capsule_dir, ignore_errors=True)

    def test_capsule_initializes_commitments_file(self):
        path = pathlib.Path(capsule.capsule_path(self.org_id, 'commitments.json'))
        self.assertTrue(path.exists())
        payload = commitments._load_store(self.org_id)
        self.assertEqual(payload['commitments'], {})
        self.assertIn('accepted', payload['states'])

    def test_propose_accept_validate_and_mark_delivery(self):
        record = commitments.propose_commitment(
            self.org_id,
            'host_beta',
            'org_beta',
            'delivery_execution',
            'user_owner',
            terms_payload={'scope': 'demo'},
            warrant_id='war_demo',
        )
        self.assertEqual(record['state'], 'proposed')
        accepted = commitments.review_commitment(
            record['commitment_id'],
            'accept',
            'user_owner',
            org_id=self.org_id,
        )
        self.assertEqual(accepted['state'], 'accepted')
        validated = commitments.validate_commitment_for_federation(
            record['commitment_id'],
            org_id=self.org_id,
            target_host_id='host_beta',
            target_org_id='org_beta',
            warrant_id='war_demo',
        )
        self.assertEqual(validated['commitment_id'], record['commitment_id'])
        updated = commitments.mark_commitment_delivery(
            record['commitment_id'],
            org_id=self.org_id,
            delivery_ref={'receipt_id': 'fedrcpt_demo'},
        )
        self.assertEqual(updated['delivery_refs'][0]['receipt_id'], 'fedrcpt_demo')

    def test_validate_rejects_unaccepted_commitment(self):
        record = commitments.propose_commitment(
            self.org_id,
            'host_beta',
            'org_beta',
            'delivery_execution',
            'user_owner',
        )
        with self.assertRaises(PermissionError):
            commitments.validate_commitment_for_federation(
                record['commitment_id'],
                org_id=self.org_id,
                target_host_id='host_beta',
                target_org_id='org_beta',
            )

    def test_validate_rejects_target_mismatch(self):
        record = commitments.propose_commitment(
            self.org_id,
            'host_beta',
            'org_beta',
            'delivery_execution',
            'user_owner',
        )
        commitments.review_commitment(record['commitment_id'], 'accept', 'user_owner', org_id=self.org_id)
        with self.assertRaises(PermissionError):
            commitments.validate_commitment_for_federation(
                record['commitment_id'],
                org_id=self.org_id,
                target_host_id='host_gamma',
                target_org_id='org_beta',
            )

    def test_review_transitions_to_breach_and_settle(self):
        record = commitments.propose_commitment(
            self.org_id,
            'host_beta',
            'org_beta',
            'delivery_execution',
            'user_owner',
        )
        breached = commitments.review_commitment(
            record['commitment_id'],
            'breach',
            'user_owner',
            org_id=self.org_id,
        )
        self.assertEqual(breached['state'], 'breached')
        settled = commitments.review_commitment(
            record['commitment_id'],
            'settle',
            'user_owner',
            org_id=self.org_id,
        )
        self.assertEqual(settled['state'], 'settled')


if __name__ == '__main__':
    unittest.main()
