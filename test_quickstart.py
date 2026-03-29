import unittest
import sys
import os
from unittest.mock import patch

# Import the module to test
import quickstart

class TestQuickstart(unittest.TestCase):
    @patch('quickstart.subprocess.run')
    @patch('builtins.print')
    def test_start_workspace(self, mock_print, mock_subprocess_run):
        """Test that start_workspace runs the correct subprocess command."""
        port = 8080
        quickstart.start_workspace(port)

        expected_cmd = [
            sys.executable,
            os.path.join(quickstart.KERNEL_DIR, 'workspace.py'),
            '--port',
            str(port)
        ]

        # Verify that subprocess.run was called with the correct arguments
        mock_subprocess_run.assert_called_once_with(
            expected_cmd,
            cwd=quickstart.ROOT
        )

        # Verify that the correct startup messages were printed
        self.assertEqual(mock_print.call_count, 2)
        mock_print.assert_any_call(f"\n  Starting governed workspace on http://localhost:{port}")
        mock_print.assert_any_call("  Press Ctrl+C to stop.\n")

if __name__ == '__main__':
    unittest.main()
