import unittest
from unittest.mock import patch, MagicMock
from collections import namedtuple

import economy.sanctions as sanctions

Args = namedtuple('Args', ['org_id', 'agent', 'type', 'note'])

class TestSanctionsCLI(unittest.TestCase):
    @patch('economy.sanctions.save_ledger')
    @patch('economy.sanctions.apply_sanction')
    @patch('economy.sanctions.load_ledger')
    def test_cmd_apply_success(self, mock_load, mock_apply, mock_save):
        """When apply_sanction returns True, save_ledger should be called."""
        mock_load.return_value = {'agents': {}}
        mock_apply.return_value = True

        args = Args(org_id='org_123', agent='agent_1', type='probation', note='test')
        sanctions.cmd_apply(args)

        mock_load.assert_called_once_with('org_123')
        mock_apply.assert_called_once_with(
            {'agents': {}}, 'agent_1', 'probation', 'test', org_id='org_123'
        )
        mock_save.assert_called_once_with({'agents': {}}, 'org_123')

    @patch('economy.sanctions.save_ledger')
    @patch('economy.sanctions.apply_sanction')
    @patch('economy.sanctions.load_ledger')
    def test_cmd_apply_failure(self, mock_load, mock_apply, mock_save):
        """When apply_sanction returns False, save_ledger should not be called."""
        mock_load.return_value = {'agents': {}}
        mock_apply.return_value = False

        args = Args(org_id='org_123', agent='agent_1', type='probation', note='test')
        sanctions.cmd_apply(args)

        mock_load.assert_called_once_with('org_123')
        mock_apply.assert_called_once_with(
            {'agents': {}}, 'agent_1', 'probation', 'test', org_id='org_123'
        )
        mock_save.assert_not_called()

    @patch('economy.sanctions.save_ledger')
    @patch('economy.sanctions.lift_sanction')
    @patch('economy.sanctions.load_ledger')
    def test_cmd_lift_success(self, mock_load, mock_lift, mock_save):
        """When lift_sanction returns True, save_ledger should be called."""
        mock_load.return_value = {'agents': {}}
        mock_lift.return_value = True

        args = Args(org_id='org_123', agent='agent_1', type='probation', note='test')
        sanctions.cmd_lift(args)

        mock_load.assert_called_once_with('org_123')
        mock_lift.assert_called_once_with(
            {'agents': {}}, 'agent_1', 'probation', 'test', org_id='org_123'
        )
        mock_save.assert_called_once_with({'agents': {}}, 'org_123')

    @patch('economy.sanctions.save_ledger')
    @patch('economy.sanctions.lift_sanction')
    @patch('economy.sanctions.load_ledger')
    def test_cmd_lift_failure(self, mock_load, mock_lift, mock_save):
        """When lift_sanction returns False, save_ledger should not be called."""
        mock_load.return_value = {'agents': {}}
        mock_lift.return_value = False

        args = Args(org_id='org_123', agent='agent_1', type='probation', note='test')
        sanctions.cmd_lift(args)

        mock_load.assert_called_once_with('org_123')
        mock_lift.assert_called_once_with(
            {'agents': {}}, 'agent_1', 'probation', 'test', org_id='org_123'
        )
        mock_save.assert_not_called()

if __name__ == '__main__':
    unittest.main()
