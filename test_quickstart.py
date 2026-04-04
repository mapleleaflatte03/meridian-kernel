import unittest
from unittest.mock import patch, mock_open, call, MagicMock
import os
import json

import quickstart

class TestInitEconomy(unittest.TestCase):

    @patch('quickstart.os.path.exists')
    @patch('quickstart.step')
    def test_init_economy_ledger_exists(self, mock_step, mock_exists):
        # Setup: ledger.json exists
        mock_exists.side_effect = lambda path: path.endswith('ledger.json')

        with patch('builtins.open', mock_open()) as mocked_file:
            quickstart.init_economy()

            # Since ledger exists, it should skip creating ledger and revenue
            mock_step.assert_called_with("Economy ledger exists, skipping")
            mocked_file.assert_not_called()

    @patch('quickstart.os.path.exists')
    @patch('quickstart.step')
    @patch('quickstart.now_ts')
    @patch('quickstart.json.dump')
    def test_init_economy_neither_exists(self, mock_json_dump, mock_now_ts, mock_step, mock_exists):
        # Setup: neither ledger.json nor revenue.json exists
        mock_exists.return_value = False
        mock_now_ts.return_value = '2023-01-01T00:00:00Z'

        with patch('builtins.open', mock_open()) as mocked_file:
            quickstart.init_economy()

            # Assert calls to open
            self.assertEqual(mocked_file.call_count, 2)
            calls = [
                call(os.path.join(quickstart.ECONOMY_DIR, 'ledger.json'), 'w'),
                call(os.path.join(quickstart.ECONOMY_DIR, 'revenue.json'), 'w')
            ]
            mocked_file.assert_has_calls(calls, any_order=True)

            # Assert calls to json.dump
            self.assertEqual(mock_json_dump.call_count, 2)

            # Check the content of the first dump (ledger.json)
            ledger_call_args = mock_json_dump.call_args_list[0][0]
            ledger_data = ledger_call_args[0]
            self.assertEqual(ledger_data['version'], 1)
            self.assertEqual(ledger_data['schema'], "meridian-kernel-economy-v1")
            self.assertEqual(ledger_data['updatedAt'], '2023-01-01T00:00:00Z')
            self.assertIn('main', ledger_data['agents'])
            self.assertIn('atlas', ledger_data['agents'])
            self.assertEqual(ledger_data['treasury']['cash_usd'], 0.0)

            # Check the content of the second dump (revenue.json)
            revenue_call_args = mock_json_dump.call_args_list[1][0]
            revenue_data = revenue_call_args[0]
            self.assertEqual(revenue_data, {"clients": {}, "orders": {}, "receivables_usd": 0.0})

    @patch('quickstart.os.path.exists')
    @patch('quickstart.step')
    @patch('quickstart.now_ts')
    @patch('quickstart.json.dump')
    def test_init_economy_ledger_missing_revenue_exists(self, mock_json_dump, mock_now_ts, mock_step, mock_exists):
        # Setup: ledger.json missing, revenue.json exists
        mock_exists.side_effect = lambda path: path.endswith('revenue.json')
        mock_now_ts.return_value = '2023-01-01T00:00:00Z'

        with patch('builtins.open', mock_open()) as mocked_file:
            quickstart.init_economy()

            # Assert call to open (only for ledger.json)
            self.assertEqual(mocked_file.call_count, 1)
            mocked_file.assert_called_with(os.path.join(quickstart.ECONOMY_DIR, 'ledger.json'), 'w')

            # Assert call to json.dump (only for ledger.json)
            self.assertEqual(mock_json_dump.call_count, 1)
            ledger_call_args = mock_json_dump.call_args_list[0][0]
            ledger_data = ledger_call_args[0]
            self.assertEqual(ledger_data['version'], 1)

if __name__ == '__main__':
    unittest.main()
