import unittest
import sys
from unittest.mock import patch
import quickstart

class TestQuickstart(unittest.TestCase):
    @patch('sys.exit')
    @patch('builtins.print')
    def test_check_python_version_pass(self, mock_print, mock_exit):
        with patch('sys.version_info', (3, 9)):
            quickstart.check_python_version()
        mock_print.assert_not_called()
        mock_exit.assert_not_called()

        with patch('sys.version_info', (3, 12)):
            quickstart.check_python_version()
        mock_print.assert_not_called()
        mock_exit.assert_not_called()

    @patch('sys.exit')
    @patch('builtins.print')
    def test_check_python_version_fail(self, mock_print, mock_exit):
        with patch('sys.version_info', (3, 8)):
            with patch('sys.version', '3.8.0'):
                quickstart.check_python_version()
        mock_print.assert_called_once_with('Error: Python 3.9+ required (found 3.8.0)')
        mock_exit.assert_called_once_with(1)

if __name__ == '__main__':
    unittest.main()
