import unittest
from unittest.mock import patch
from economy.sanctions import check_auto_sanctions

class TestSanctionsAutoCheck(unittest.TestCase):

    def setUp(self):
        # Baseline agent data
        self.agent_template = {
            'reputation_units': 50,
            'authority_units': 50,
            'probation': False,
            'zero_authority': False
        }

    def _create_data(self, agent_data=None):
        data = {
            'agents': {
                'agent1': dict(self.agent_template)
            },
            'epoch': {
                'auth_decay_per_epoch': 5
            }
        }
        if agent_data:
            data['agents']['agent1'].update(agent_data)
        return data

    @patch('economy.sanctions.append_tx')
    def test_no_changes(self, mock_append_tx):
        """Agents with normal metrics shouldn't trigger sanctions."""
        data = self._create_data()
        changes = check_auto_sanctions(data)

        self.assertEqual(len(changes), 0)
        self.assertFalse(data['agents']['agent1']['probation'])
        self.assertFalse(data['agents']['agent1']['zero_authority'])
        mock_append_tx.assert_not_called()

    @patch('economy.sanctions.append_tx')
    def test_apply_probation(self, mock_append_tx):
        """Agents with REP <= 20 should trigger auto-probation."""
        data = self._create_data({'reputation_units': 20})
        changes = check_auto_sanctions(data)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][:3], ('apply', 'agent1', 'probation'))
        self.assertTrue(data['agents']['agent1']['probation'])
        mock_append_tx.assert_called_once()
        args = mock_append_tx.call_args[0][0]
        self.assertEqual(args['type'], 'sanction_applied')
        self.assertEqual(args['sanction'], 'probation')

    @patch('economy.sanctions.append_tx')
    def test_apply_zero_auth_for_zero_auth_units(self, mock_append_tx):
        """Agents with AUTH = 0 should trigger zero_authority."""
        data = self._create_data({'authority_units': 0})
        changes = check_auto_sanctions(data)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][:3], ('apply', 'agent1', 'zero_authority'))
        self.assertTrue(data['agents']['agent1']['zero_authority'])
        self.assertEqual(data['agents']['agent1']['authority_units'], 0)
        mock_append_tx.assert_called_once()
        args = mock_append_tx.call_args[0][0]
        self.assertEqual(args['type'], 'sanction_applied')
        self.assertEqual(args['sanction'], 'zero_authority')

    @patch('economy.sanctions.append_tx')
    def test_apply_zero_auth_for_critical_rep(self, mock_append_tx):
        """Agents with REP <= 5 should trigger zero_authority."""
        data = self._create_data({'reputation_units': 5})
        changes = check_auto_sanctions(data)

        self.assertEqual(len(changes), 2)
        # It applies probation first, then zero_authority
        self.assertEqual(changes[0][:3], ('apply', 'agent1', 'probation'))
        self.assertEqual(changes[1][:3], ('apply', 'agent1', 'zero_authority'))
        self.assertTrue(data['agents']['agent1']['probation'])
        self.assertTrue(data['agents']['agent1']['zero_authority'])
        self.assertEqual(mock_append_tx.call_count, 2)

    @patch('economy.sanctions.append_tx')
    def test_lift_probation(self, mock_append_tx):
        """Agents on probation with REP > 30 should get probation lifted."""
        data = self._create_data({'reputation_units': 31, 'probation': True})
        changes = check_auto_sanctions(data)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][:3], ('lift', 'agent1', 'probation'))
        self.assertFalse(data['agents']['agent1']['probation'])
        mock_append_tx.assert_called_once()
        args = mock_append_tx.call_args[0][0]
        self.assertEqual(args['type'], 'sanction_lifted')
        self.assertEqual(args['sanction'], 'probation')

    @patch('economy.sanctions.append_tx')
    def test_lift_zero_auth(self, mock_append_tx):
        """Agents with zero_authority and AUTH > 15 should have it lifted."""
        data = self._create_data({'authority_units': 16, 'zero_authority': True, 'probation': True, 'reputation_units': 25})
        changes = check_auto_sanctions(data)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][:3], ('lift', 'agent1', 'zero_authority'))
        self.assertFalse(data['agents']['agent1']['zero_authority'])
        # When lifted, it gives a floor auth of 6 (if 0, but here we set to 16, so it's kept as 16)
        self.assertEqual(data['agents']['agent1']['authority_units'], 16)
        mock_append_tx.assert_called_once()
        args = mock_append_tx.call_args[0][0]
        self.assertEqual(args['type'], 'sanction_lifted')
        self.assertEqual(args['sanction'], 'zero_authority')

    @patch('economy.sanctions.append_tx')
    def test_dry_run(self, mock_append_tx):
        """Calling with dry_run=True should return expected changes without mutating."""
        data = self._create_data({'reputation_units': 20})
        changes = check_auto_sanctions(data, dry_run=True)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][:3], ('apply', 'agent1', 'probation'))
        # Should NOT mutate the actual agent dict during dry_run
        self.assertFalse(data['agents']['agent1']['probation'])
        mock_append_tx.assert_not_called()

if __name__ == '__main__':
    unittest.main()
