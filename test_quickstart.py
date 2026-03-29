import unittest
from unittest.mock import patch
from io import StringIO
from quickstart import step

class TestQuickstart(unittest.TestCase):
    @patch('sys.stdout', new_callable=StringIO)
    def test_step(self, mock_stdout):
        step("test message")
        self.assertEqual(mock_stdout.getvalue(), "\n  → test message\n")

if __name__ == '__main__':
    unittest.main()
