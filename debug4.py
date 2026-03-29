import sys
import unittest
import os
print("CWD:", os.getcwd())
print("PYTHONPATH:", os.environ.get("PYTHONPATH"))
import test_quickstart
print("importing kernel.organizations")
import kernel.organizations
print("Success")
