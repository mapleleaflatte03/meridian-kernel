#!/usr/bin/env python3
import json
import os
import unittest
from unittest.mock import patch, mock_open, MagicMock

# Make sure we can import from economy.sanctions
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from economy.sanctions import save_ledger, _missing_org_error

class TestSanctionsSaveLedger(unittest.TestCase):

    @patch('economy.sanctions.now_ts', return_value='2023-10-27T12:34:56Z')
    @patch('economy.sanctions._ledger_path', return_value='/fake/ledger.json')
    @patch('economy.sanctions.open', new_callable=mock_open)
    def test_save_ledger_happy_path(self, mock_file, mock_ledger_path, mock_now_ts):
        """Test save_ledger writes data correctly and updates updatedAt."""
        data = {'agents': {}}

        save_ledger(data)

        # Check updatedAt was added
        self.assertEqual(data['updatedAt'], '2023-10-27T12:34:56Z')

        # Check that it opened the correct file
        mock_file.assert_called_once_with('/fake/ledger.json', 'w')

        # Check json.dump was called with the correct data
        # mock_file().write gets called by json.dump
        written_content = "".join(call.args[0] for call in mock_file().write.call_args_list)
        written_data = json.loads(written_content)
        self.assertEqual(written_data, data)

    @patch('economy.sanctions.now_ts', return_value='2023-10-27T12:34:56Z')
    @patch('economy.sanctions._ledger_path', return_value='/fake/org_123/ledger.json')
    @patch('os.path.isdir', return_value=True)
    @patch('economy.sanctions.open', new_callable=mock_open)
    def test_save_ledger_with_org_id(self, mock_file, mock_isdir, mock_ledger_path, mock_now_ts):
        """Test save_ledger with an org_id, directory exists."""
        data = {'agents': {}}
        org_id = 'org_123'

        save_ledger(data, org_id)

        mock_isdir.assert_called_once_with('/fake/org_123')
        mock_file.assert_called_once_with('/fake/org_123/ledger.json', 'w')

    @patch('economy.sanctions.now_ts', return_value='2023-10-27T12:34:56Z')
    @patch('economy.sanctions._ledger_path', return_value='/fake/org_123/ledger.json')
    @patch('os.path.isdir', return_value=False)
    @patch('economy.sanctions._missing_org_error')
    def test_save_ledger_missing_org_dir(self, mock_missing_org_error, mock_isdir, mock_ledger_path, mock_now_ts):
        """Test save_ledger calls _missing_org_error when org_id directory doesn't exist."""
        # _missing_org_error is expected to raise SystemExit or an Exception
        mock_missing_org_error.side_effect = SystemExit("Missing org")

        data = {'agents': {}}
        org_id = 'org_123'

        with self.assertRaises(SystemExit):
            save_ledger(data, org_id)

        mock_isdir.assert_called_once_with('/fake/org_123')
        mock_missing_org_error.assert_called_once_with(org_id)

if __name__ == '__main__':
    unittest.main()
