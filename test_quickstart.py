import unittest
from unittest.mock import patch
import io
import sys

import quickstart

class TestQuickstart(unittest.TestCase):
    @patch('quickstart.check_python_version')
    @patch('quickstart.init_economy')
    @patch('quickstart.init_kernel')
    @patch('quickstart.show_status')
    @patch('quickstart.start_workspace')
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_main_default_behavior(self, mock_stdout, mock_start, mock_show, mock_init_k, mock_init_e, mock_check):
        with patch('sys.argv', ['quickstart.py']):
            quickstart.main()

        mock_check.assert_called_once()
        mock_init_e.assert_called_once()
        mock_init_k.assert_called_once()
        mock_show.assert_called_once()
        mock_start.assert_called_once_with(18901)

        output = mock_stdout.getvalue()
        self.assertIn("Checking Python version... OK", output)
        self.assertIn("Meridian Constitutional Kernel — Quickstart", output)

    @patch('quickstart.check_python_version')
    @patch('quickstart.init_economy')
    @patch('quickstart.init_kernel')
    @patch('quickstart.show_status')
    @patch('quickstart.start_workspace')
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_main_init_only(self, mock_stdout, mock_start, mock_show, mock_init_k, mock_init_e, mock_check):
        with patch('sys.argv', ['quickstart.py', '--init-only']):
            quickstart.main()

        mock_check.assert_called_once()
        mock_init_e.assert_called_once()
        mock_init_k.assert_called_once()
        mock_show.assert_called_once()
        mock_start.assert_not_called()

        output = mock_stdout.getvalue()
        self.assertIn("Initialization complete.", output)
        self.assertIn("Run 'python3 kernel/workspace.py' to start the dashboard.", output)

    @patch('quickstart.check_python_version')
    @patch('quickstart.init_economy')
    @patch('quickstart.init_kernel')
    @patch('quickstart.show_status')
    @patch('quickstart.start_workspace')
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_main_custom_port(self, mock_stdout, mock_start, mock_show, mock_init_k, mock_init_e, mock_check):
        with patch('sys.argv', ['quickstart.py', '--port', '8080']):
            quickstart.main()

        mock_check.assert_called_once()
        mock_init_e.assert_called_once()
        mock_init_k.assert_called_once()
        mock_show.assert_called_once()
        mock_start.assert_called_once_with(8080)

if __name__ == '__main__':
    unittest.main()
