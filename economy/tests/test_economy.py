#!/usr/bin/env python3
"""
Control tests for the Meridian enforced economy.
Tests:
  1. Accepted output raises score
  2. Weak output triggers sanction
  3. Zero-authority agent cannot lead

Run: python3 economy/tests/test_economy.py
Exit 0 = all passed. Exit 1 = failures.
"""
import json, os, sys, subprocess, shutil, datetime

WORKSPACE    = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
ECONOMY_DIR  = os.path.join(WORKSPACE, 'economy')
LEDGER_PATH  = os.path.join(ECONOMY_DIR, 'ledger.json')
TX_PATH      = os.path.join(ECONOMY_DIR, 'transactions.jsonl')

# -- test runner --------------------------------------------------------------

class T:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name, detail=''):
        print(f"  PASS  {name}")
        self.passed += 1

    def fail(self, name, detail=''):
        msg = f"FAIL  {name}" + (f": {detail}" if detail else '')
        print(f"  {msg}")
        self.failed += 1
        self.errors.append(msg)

    def check(self, cond, name, detail=''):
        (self.ok if cond else self.fail)(name, detail)

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*50}")
        print(f"Results: {self.passed}/{total} passed, {self.failed} failed")
        for e in self.errors:
            print(f"  x {e}")
        return self.failed == 0

def run(cmd, check_rc=False):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=WORKSPACE)
    return r.stdout.strip(), r.returncode, r.stderr.strip()

def load_ledger():
    with open(LEDGER_PATH) as f:
        return json.load(f)

def load_txs():
    with open(TX_PATH) as f:
        return [json.loads(l) for l in f if l.strip()]

# -- snapshot helpers ---------------------------------------------------------

def snap(agent_id):
    d = load_ledger()['agents'][agent_id]
    return d['reputation_units'], d['authority_units']

def restore_score(agent_id, rep, auth):
    current = snap(agent_id)
    rep_d   = rep  - current[0]
    auth_d  = auth - current[1]
    if rep_d != 0 or auth_d != 0:
        run(['python3', 'economy/score.py', 'record',
             '--agent', agent_id, '--event', 'test_restore',
             '--rep', str(rep_d), '--auth', str(auth_d), '--note', 'test cleanup'])

# -- tests --------------------------------------------------------------------

def test_1_accepted_output_raises_score(t):
    print("\n=== TEST 1: accepted output raises score ===")
    rep0, auth0 = snap('atlas')
    out, rc, _ = run(['python3', 'economy/score.py', 'record',
                      '--agent', 'atlas', '--event', 'test_accepted',
                      '--rep', '10', '--auth', '8', '--note', 'ctrl-test accepted output'])
    t.check(rc == 0, "score.py record exits 0", out)
    rep1, auth1 = snap('atlas')
    t.check(rep1  > rep0,  "REP increased",  f"{rep0}->{rep1}")
    t.check(auth1 > auth0, "AUTH increased", f"{auth0}->{auth1}")
    restore_score('atlas', rep0, auth0)
    t.check(snap('atlas') == (rep0, auth0), "Atlas score restored after test")

def test_2_weak_output_sanction(t):
    print("\n=== TEST 2: weak output triggers sanction ===")
    tx_before = len(load_txs())
    out, rc, _ = run(['python3', 'economy/sanctions.py', 'apply',
                      '--agent', 'sentinel', '--type', 'lead_ban',
                      '--note', 'ctrl-test weak output'])
    t.check(rc == 0, "sanctions.py apply exits 0", out)
    t.check('SANCTION APPLIED' in out, "SANCTION APPLIED printed", out)

    txs_after = load_txs()
    sanction_txs = [tx for tx in txs_after[tx_before:]
                    if tx.get('type') == 'sanction_applied' and tx.get('agent') == 'sentinel']
    t.check(len(sanction_txs) > 0, "sanction_applied written to transactions.jsonl")

    # Cleanup
    run(['python3', 'economy/sanctions.py', 'lift',
         '--agent', 'sentinel', '--type', 'lead_ban', '--note', 'ctrl-test cleanup'])
    d = load_ledger()['agents']['sentinel']
    t.check(not d.get('lead_ban'), "lead_ban cleared after lift")

def test_3_zero_authority_cannot_lead(t):
    print("\n=== TEST 3: zero-authority agent cannot lead ===")
    rep0, auth0 = snap('forge')

    # Apply zero_authority
    run(['python3', 'economy/sanctions.py', 'apply',
         '--agent', 'forge', '--type', 'zero_authority', '--note', 'ctrl-test zero_auth'])

    out, rc, _ = run(['python3', 'economy/authority.py', 'check',
                      '--agent', 'forge', '--action', 'lead'])
    t.check(rc == 1,         "authority check exits 1 (blocked)",  out)
    t.check('BLOCKED' in out, "BLOCKED message printed",           out)

    out_lead, _, _ = run(['python3', 'economy/authority.py', 'sprint-lead'])
    t.check('forge' not in out_lead.lower() or 'NONE' in out_lead,
            "zero_authority forge not selected as sprint lead", out_lead)

    # AUTH gain blocked while zero_authority
    forge_auth_before = snap('forge')[1]
    run(['python3', 'economy/score.py', 'record',
         '--agent', 'forge', '--event', 'test_auth_block',
         '--auth', '10', '--note', 'ctrl-test should be blocked'])
    t.check(snap('forge')[1] == forge_auth_before, "AUTH gain blocked when zero_authority")

    # Cleanup
    run(['python3', 'economy/sanctions.py', 'lift',
         '--agent', 'forge', '--type', 'zero_authority', '--note', 'ctrl-test cleanup'])
    restore_score('forge', rep0, auth0)

# -- main ---------------------------------------------------------------------

def main():
    print(f"Meridian Economy -- Control Tests")
    print(f"Workspace: {WORKSPACE}")
    t = T()
    test_1_accepted_output_raises_score(t)
    test_2_weak_output_sanction(t)
    test_3_zero_authority_cannot_lead(t)
    ok = t.summary()
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
