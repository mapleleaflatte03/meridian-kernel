#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

WORKSPACE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from economy.sanctions import append_tx

class TestSanctions(unittest.TestCase):
    def test_append_tx_success(self):
        """Test append_tx successfully writes to the correct file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            tx_file = os.path.join(temp_dir, 'transactions.jsonl')

            with patch('economy.sanctions._tx_path', return_value=tx_file), \
                 patch('economy.sanctions.now_ts', return_value='2023-10-01T12:00:00Z'):

                entry1 = {'action': 'test1', 'value': 1}
                append_tx(entry1)

                entry2 = {'action': 'test2', 'value': 2}
                append_tx(entry2)

                # Verify file contents
                with open(tx_file, 'r') as f:
                    lines = f.readlines()

                self.assertEqual(len(lines), 2)

                written_entry1 = json.loads(lines[0])
                self.assertEqual(written_entry1['action'], 'test1')
                self.assertEqual(written_entry1['value'], 1)
                self.assertEqual(written_entry1['ts'], '2023-10-01T12:00:00Z')

                written_entry2 = json.loads(lines[1])
                self.assertEqual(written_entry2['action'], 'test2')
                self.assertEqual(written_entry2['value'], 2)
                self.assertEqual(written_entry2['ts'], '2023-10-01T12:00:00Z')

    def test_append_tx_missing_org(self):
        """Test append_tx raises SystemExit when org dir is missing."""
        # Provide a path where the parent directory does not exist
        missing_dir_path = os.path.join(tempfile.gettempdir(), 'non_existent_dir_12345', 'transactions.jsonl')

        with patch('economy.sanctions._tx_path', return_value=missing_dir_path):
            entry = {'action': 'test'}
            # append_tx checks for org_id and if os.path.isdir(os.path.dirname(path))
            with self.assertRaises(SystemExit) as cm:
                append_tx(entry, org_id='test_org')

            self.assertIn("institution 'test_org' is not initialized", str(cm.exception))

if __name__ == "__main__":
    unittest.main()
