#!/usr/bin/env python3
"""
Unit tests for the economy.sanctions module.
"""
import unittest
from unittest.mock import patch
from economy import sanctions

class TestApplySanction(unittest.TestCase):
    def setUp(self):
        self.data = {
            'agents': {
                'agent1': {
                    'authority_units': 50,
                    'reputation_units': 50,
                }
            }
        }

    @patch('economy.sanctions.append_tx')
    def test_apply_sanction_unknown_agent(self, mock_append):
        """Should return False and not append a transaction for an unknown agent."""
        result = sanctions.apply_sanction(self.data, 'unknown_agent', 'probation', 'test unknown')
        self.assertFalse(result)
        mock_append.assert_not_called()

    @patch('economy.sanctions.append_tx')
    def test_apply_sanction_probation(self, mock_append):
        """Should apply probation flag and append a transaction."""
        result = sanctions.apply_sanction(self.data, 'agent1', 'probation', 'test probation')
        self.assertTrue(result)
        self.assertTrue(self.data['agents']['agent1']['probation'])
        self.assertIn('SANCTION:probation | test probation', self.data['agents']['agent1']['last_score_reason'])
        mock_append.assert_called_once()

        args, kwargs = mock_append.call_args
        self.assertEqual(args[0]['sanction'], 'probation')

    @patch('economy.sanctions.append_tx')
    def test_apply_sanction_zero_authority(self, mock_append):
        """Should apply zero_authority flag, set authority to 0, and append a transaction."""
        result = sanctions.apply_sanction(self.data, 'agent1', 'zero_authority', 'test zero auth')
        self.assertTrue(result)
        self.assertTrue(self.data['agents']['agent1']['zero_authority'])
        self.assertEqual(self.data['agents']['agent1']['authority_units'], 0)
        mock_append.assert_called_once()

        args, kwargs = mock_append.call_args
        self.assertEqual(args[0]['sanction'], 'zero_authority')

    @patch('economy.sanctions.append_tx')
    def test_apply_sanction_lead_ban(self, mock_append):
        """Should apply lead_ban flag and append a transaction."""
        result = sanctions.apply_sanction(self.data, 'agent1', 'lead_ban', 'test lead ban')
        self.assertTrue(result)
        self.assertTrue(self.data['agents']['agent1']['lead_ban'])
        mock_append.assert_called_once()

        args, kwargs = mock_append.call_args
        self.assertEqual(args[0]['sanction'], 'lead_ban')

    @patch('economy.sanctions.append_tx')
    def test_apply_sanction_remediation_only(self, mock_append):
        """Should apply zero_authority, probation, remediation_only flags, set authority to 0, and append a transaction."""
        result = sanctions.apply_sanction(self.data, 'agent1', 'remediation_only', 'test remediation')
        self.assertTrue(result)
        self.assertTrue(self.data['agents']['agent1']['remediation_only'])
        self.assertTrue(self.data['agents']['agent1']['zero_authority'])
        self.assertTrue(self.data['agents']['agent1']['probation'])
        self.assertEqual(self.data['agents']['agent1']['authority_units'], 0)
        mock_append.assert_called_once()

        args, kwargs = mock_append.call_args
        self.assertEqual(args[0]['sanction'], 'remediation_only')

if __name__ == '__main__':
    unittest.main()
