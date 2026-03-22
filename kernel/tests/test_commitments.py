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
            'Deliver the approved brief',
            'user_owner',
            terms_payload={'scope': 'demo'},
            warrant_id='war_demo',
        )
        self.assertEqual(record['status'], 'proposed')
        self.assertEqual(record['summary'], 'Deliver the approved brief')
        self.assertEqual(record['institution_id'], self.org_id)
        self.assertEqual(record['target_institution_id'], 'org_beta')
        accepted = commitments.accept_commitment(
            record['commitment_id'],
            'user_owner',
            org_id=self.org_id,
        )
        self.assertEqual(accepted['status'], 'accepted')
        self.assertEqual(accepted['accepted_by'], 'user_owner')
        validated = commitments.validate_commitment_for_delivery(
            record['commitment_id'],
            org_id=self.org_id,
            target_host_id='host_beta',
            target_institution_id='org_beta',
            warrant_id='war_demo',
        )
        self.assertEqual(validated['commitment_id'], record['commitment_id'])
        updated = commitments.record_delivery_ref(
            record['commitment_id'],
            {'receipt_id': 'fedrcpt_demo'},
            org_id=self.org_id,
        )
        self.assertEqual(updated['delivery_refs'][0]['receipt_id'], 'fedrcpt_demo')
        self.assertIn('recorded_at', updated['delivery_refs'][0])
        summary = commitments.commitment_summary(self.org_id)
        self.assertEqual(summary['accepted'], 1)
        self.assertEqual(summary['delivery_refs_total'], 1)

    def test_validate_rejects_unaccepted_commitment(self):
        record = commitments.propose_commitment(
            self.org_id,
            'host_beta',
            'org_beta',
            'Deliver the approved brief',
            'user_owner',
        )
        with self.assertRaises(ValueError):
            commitments.validate_commitment_for_delivery(
                record['commitment_id'],
                org_id=self.org_id,
                target_host_id='host_beta',
                target_institution_id='org_beta',
            )

    def test_validate_rejects_target_mismatch(self):
        record = commitments.propose_commitment(
            self.org_id,
            'host_beta',
            'org_beta',
            'Deliver the approved brief',
            'user_owner',
        )
        commitments.accept_commitment(record['commitment_id'], 'user_owner', org_id=self.org_id)
        with self.assertRaises(ValueError):
            commitments.validate_commitment_for_delivery(
                record['commitment_id'],
                org_id=self.org_id,
                target_host_id='host_gamma',
                target_institution_id='org_beta',
            )

    def test_review_transitions_to_breach_and_settle(self):
        record = commitments.propose_commitment(
            self.org_id,
            'host_beta',
            'org_beta',
            'Deliver the approved brief',
            'user_owner',
        )
        breached = commitments.breach_commitment(
            record['commitment_id'],
            'user_owner',
            org_id=self.org_id,
        )
        self.assertEqual(breached['status'], 'breached')
        settled = commitments.settle_commitment(
            record['commitment_id'],
            'user_owner',
            org_id=self.org_id,
        )
        self.assertEqual(settled['status'], 'settled')


if __name__ == '__main__':
    unittest.main()
