#!/usr/bin/env python3
"""
Unit tests for the sanctions module in the Meridian kernel economy.
"""

import unittest
from economy.sanctions import get_restrictions

class TestSanctions(unittest.TestCase):
    def setUp(self):
        self.mock_data = {
            'agents': {
                'active_agent': {
                    'name': 'Active Agent',
                    'probation': False,
                    'zero_authority': False,
                    'lead_ban': False,
                    'remediation_only': False
                },
                'probation_agent': {
                    'name': 'Probation Agent',
                    'probation': True,
                    'zero_authority': False,
                    'lead_ban': False,
                    'remediation_only': False
                },
                'zero_authority_agent': {
                    'name': 'Zero Authority Agent',
                    'probation': False,
                    'zero_authority': True,
                    'lead_ban': False,
                    'remediation_only': False
                },
                'lead_ban_agent': {
                    'name': 'Lead Ban Agent',
                    'probation': False,
                    'zero_authority': False,
                    'lead_ban': True,
                    'remediation_only': False
                },
                'remediation_only_agent': {
                    'name': 'Remediation Only Agent',
                    'probation': False,
                    'zero_authority': False,
                    'lead_ban': False,
                    'remediation_only': True
                },
                'multiple_sanctions_agent': {
                    'name': 'Multiple Sanctions Agent',
                    'probation': True,
                    'zero_authority': False,
                    'lead_ban': True,
                    'remediation_only': False
                }
            }
        }

    def test_get_restrictions_unknown_agent(self):
        """Should return empty list for unknown agent."""
        restrictions = get_restrictions(self.mock_data, 'unknown_agent')
        self.assertEqual(restrictions, [])

    def test_get_restrictions_no_active_sanctions(self):
        """Should return empty list for agent with no sanctions."""
        restrictions = get_restrictions(self.mock_data, 'active_agent')
        self.assertEqual(restrictions, [])

    def test_get_restrictions_probation(self):
        """Should return correct restrictions for probation."""
        restrictions = get_restrictions(self.mock_data, 'probation_agent')
        self.assertEqual(restrictions, ['assign', 'lead'])

    def test_get_restrictions_zero_authority(self):
        """Should return correct restrictions for zero_authority."""
        restrictions = get_restrictions(self.mock_data, 'zero_authority_agent')
        self.assertEqual(restrictions, ['assign', 'execute', 'lead'])

    def test_get_restrictions_lead_ban(self):
        """Should return correct restrictions for lead_ban."""
        restrictions = get_restrictions(self.mock_data, 'lead_ban_agent')
        self.assertEqual(restrictions, ['lead'])

    def test_get_restrictions_remediation_only(self):
        """Should return correct restrictions for remediation_only."""
        restrictions = get_restrictions(self.mock_data, 'remediation_only_agent')
        self.assertEqual(restrictions, ['assign', 'execute', 'lead'])

    def test_get_restrictions_multiple_sanctions(self):
        """Should return distinct and sorted restrictions for overlapping sanctions."""
        restrictions = get_restrictions(self.mock_data, 'multiple_sanctions_agent')
        # probation: assign, lead
        # lead_ban: lead
        # combined: assign, lead
        self.assertEqual(restrictions, ['assign', 'lead'])

if __name__ == '__main__':
    unittest.main()
