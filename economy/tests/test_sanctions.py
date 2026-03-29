import unittest
import datetime
from unittest.mock import patch
from economy.sanctions import now_ts

class TestSanctions(unittest.TestCase):
    @patch('economy.sanctions.datetime')
    def test_now_ts(self, mock_datetime):
        # Setup mock to return a specific fixed UTC time
        mock_now = datetime.datetime(2023, 10, 27, 14, 30, 45)
        mock_datetime.datetime.utcnow.return_value = mock_now

        # Call the function
        result = now_ts()

        # Assert the result matches the expected format
        self.assertEqual(result, '2023-10-27T14:30:45Z')

        # Also test with another date to make sure it's not hardcoded
        mock_now2 = datetime.datetime(2024, 1, 1, 0, 0, 0)
        mock_datetime.datetime.utcnow.return_value = mock_now2
        result2 = now_ts()
        self.assertEqual(result2, '2024-01-01T00:00:00Z')

if __name__ == '__main__':
    unittest.main()
