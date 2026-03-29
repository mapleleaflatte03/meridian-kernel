#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import shutil
import unittest
import uuid
import io
import sys
from unittest.mock import MagicMock

ROOT = pathlib.Path(__file__).resolve().parents[2]
ECONOMY_DIR = ROOT / 'economy'
CAPSULES_DIR = ROOT / 'capsules'

class TestSanctionsRestrictions(unittest.TestCase):
    def setUp(self):
        self.org_id = f'org_sanc_test_{uuid.uuid4().hex[:8]}'
        self.capsule_dir = CAPSULES_DIR / self.org_id
        self.spec = importlib.util.spec_from_file_location('kernel_capsule_test', ROOT / 'kernel' / 'capsule.py')
        self.capsule = importlib.util.module_from_spec(self.spec)
        self.spec.loader.exec_module(self.capsule)
        self.capsule.init_capsule(self.org_id)

        self.ledger_path = self.capsule_dir / 'ledger.json'

        ledger = json.loads(self.ledger_path.read_text())
        ledger['agents']['testagent'] = {
            'name': 'Test Agent',
            'role': 'analyst',
            'reputation_units': 50,
            'authority_units': 50,
            'probation': False,
            'zero_authority': False,
            'status': 'active'
        }
        ledger['agents']['restrictedagent'] = {
            'name': 'Restricted Agent',
            'role': 'analyst',
            'reputation_units': 50,
            'authority_units': 50,
            'probation': True,
            'zero_authority': False,
            'status': 'active'
        }
        self.ledger_path.write_text(json.dumps(ledger, indent=2))

        # We need to import cmd_restrictions dynamically or simply add KERNEL_DIR to sys.path
        import sys
        import os
        kernel_dir = str(ROOT / 'kernel')
        if kernel_dir not in sys.path:
            sys.path.insert(0, kernel_dir)

        from economy.sanctions import cmd_restrictions
        self.cmd_restrictions = cmd_restrictions

    def tearDown(self):
        shutil.rmtree(self.capsule_dir, ignore_errors=True)

    def test_cmd_restrictions_no_restrictions(self):
        args = MagicMock()
        args.org_id = self.org_id
        args.agent = 'testagent'

        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            self.cmd_restrictions(args)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue().strip()
        self.assertEqual(output, "testagent: no active restrictions")

    def test_cmd_restrictions_with_restrictions(self):
        args = MagicMock()
        args.org_id = self.org_id
        args.agent = 'restrictedagent'

        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            self.cmd_restrictions(args)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue().strip()
        self.assertEqual(output, "restrictedagent restricted from: assign, lead")

if __name__ == '__main__':
    unittest.main()
