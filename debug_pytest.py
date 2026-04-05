import sys
original_path = sys.path.copy()
import pytest
sys.exit(pytest.main(["kernel/tests/test_organizations.py"]))
