#!/usr/bin/env python3
"""
Unit tests for the economy/sanctions.py module.
"""
import unittest
from unittest.mock import patch
from economy.sanctions import lift_sanction

class TestSanctions(unittest.TestCase):
    def setUp(self):
        self.data = {
            'epoch': {'auth_decay_per_epoch': 5},
            'agents': {
                'agent1': {
                    'probation': True,
                    'zero_authority': True,
                    'authority_units': 0,
                    'lead_ban': True,
                    'remediation_only': True
                },
                'agent2': {
                    'probation': True,
                    'zero_authority': True,
                    'authority_units': 10,
                }
            }
        }

    @patch('economy.sanctions.append_tx')
    @patch('builtins.print')
    def test_lift_sanction_unknown_agent(self, mock_print, mock_append_tx):
        """Test lifting sanction for an unknown agent returns False."""
        result = lift_sanction(self.data, 'unknown_agent', 'all', 'test')
        self.assertFalse(result)
        mock_append_tx.assert_not_called()
        mock_print.assert_called_with("ERROR: unknown agent 'unknown_agent'")

    @patch('economy.sanctions.append_tx')
    @patch('builtins.print')
    def test_lift_sanction_probation(self, mock_print, mock_append_tx):
        """Test lifting 'probation' sanction."""
        result = lift_sanction(self.data, 'agent1', 'probation', 'test lift probation')
        self.assertTrue(result)
        self.assertFalse(self.data['agents']['agent1']['probation'])
        self.assertTrue(self.data['agents']['agent1']['zero_authority']) # Check other flags remain

        mock_append_tx.assert_called_once_with({
            'type': 'sanction_lifted',
            'agent': 'agent1',
            'sanction': 'probation',
            'reason': 'test lift probation'
        }, None)

    @patch('economy.sanctions.append_tx')
    @patch('builtins.print')
    def test_lift_sanction_zero_authority_with_zero_auth(self, mock_print, mock_append_tx):
        """Test lifting 'zero_authority' when agent has 0 authority."""
        result = lift_sanction(self.data, 'agent1', 'zero_authority', 'test lift zero_authority')
        self.assertTrue(result)
        self.assertFalse(self.data['agents']['agent1']['zero_authority'])
        # auth_decay_per_epoch (5) + 1 = 6
        self.assertEqual(self.data['agents']['agent1']['authority_units'], 6)

    @patch('economy.sanctions.append_tx')
    @patch('builtins.print')
    def test_lift_sanction_zero_authority_with_non_zero_auth(self, mock_print, mock_append_tx):
        """Test lifting 'zero_authority' when agent has >0 authority."""
        result = lift_sanction(self.data, 'agent2', 'zero_authority', 'test lift zero_authority')
        self.assertTrue(result)
        self.assertFalse(self.data['agents']['agent2']['zero_authority'])
        # should remain unchanged
        self.assertEqual(self.data['agents']['agent2']['authority_units'], 10)

    @patch('economy.sanctions.append_tx')
    @patch('builtins.print')
    def test_lift_sanction_lead_ban(self, mock_print, mock_append_tx):
        """Test lifting 'lead_ban' sanction."""
        result = lift_sanction(self.data, 'agent1', 'lead_ban', 'test lift lead_ban')
        self.assertTrue(result)
        self.assertNotIn('lead_ban', self.data['agents']['agent1'])

    @patch('economy.sanctions.append_tx')
    @patch('builtins.print')
    def test_lift_sanction_remediation_only(self, mock_print, mock_append_tx):
        """Test lifting 'remediation_only' sanction."""
        result = lift_sanction(self.data, 'agent1', 'remediation_only', 'test lift remediation_only')
        self.assertTrue(result)
        self.assertNotIn('remediation_only', self.data['agents']['agent1'])

    @patch('economy.sanctions.append_tx')
    @patch('builtins.print')
    def test_lift_sanction_all(self, mock_print, mock_append_tx):
        """Test lifting 'all' sanctions."""
        result = lift_sanction(self.data, 'agent1', 'all', 'test lift all')
        self.assertTrue(result)

        agent1 = self.data['agents']['agent1']
        self.assertFalse(agent1['probation'])
        self.assertFalse(agent1['zero_authority'])
        self.assertEqual(agent1['authority_units'], 6)
        self.assertNotIn('lead_ban', agent1)
        self.assertNotIn('remediation_only', agent1)

if __name__ == '__main__':
    unittest.main()
