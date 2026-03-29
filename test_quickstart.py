import unittest
import datetime
from quickstart import now_ts

class QuickstartTests(unittest.TestCase):
    def test_now_ts_format(self):
        """Verify now_ts returns current time in %Y-%m-%dT%H:%M:%SZ format"""
        ts = now_ts()

        # Verify it's a string
        self.assertIsInstance(ts, str)

        # Verify it can be parsed using the exact expected format
        try:
            parsed = datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%SZ')
        except ValueError:
            self.fail(f"Timestamp '{ts}' does not match expected format '%Y-%m-%dT%H:%M:%SZ'")

        # Verify it's in UTC and reasonably close to the current time
        now = datetime.datetime.utcnow()
        diff = abs((now - parsed).total_seconds())
        # A 10-second window is more than enough for execution time difference
        self.assertLess(diff, 10, f"Timestamp '{ts}' is too far from current UTC time '{now}'")

if __name__ == '__main__':
    unittest.main()
