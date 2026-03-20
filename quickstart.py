#!/usr/bin/env python3
"""
Meridian Constitutional Kernel — Quickstart

Initializes an example institution, registers agents, sets up the economy,
and starts the governed workspace dashboard.

Usage:
  python3 quickstart.py              # Initialize + start workspace
  python3 quickstart.py --init-only  # Initialize without starting server
  python3 quickstart.py --port 8080  # Use a different port
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
KERNEL_DIR = os.path.join(ROOT, 'kernel')
ECONOMY_DIR = os.path.join(ROOT, 'economy')

# Ensure kernel is importable
sys.path.insert(0, ROOT)
sys.path.insert(0, KERNEL_DIR)


def step(msg):
    print(f"\n  → {msg}")


def check_python_version():
    if sys.version_info < (3, 9):
        print(f"Error: Python 3.9+ required (found {sys.version})")
        sys.exit(1)


def init_economy():
    """Create initial economy ledger if not present."""
    ledger_path = os.path.join(ECONOMY_DIR, 'ledger.json')
    if os.path.exists(ledger_path):
        step("Economy ledger exists, skipping")
        return

    step("Creating economy ledger")
    ledger = {
        "agents": {
            "main":     {"name": "Leviathann", "reputation_units": 50, "authority_units": 50, "probation": False, "zero_authority": False},
            "atlas":    {"name": "Atlas",      "reputation_units": 50, "authority_units": 50, "probation": False, "zero_authority": False},
            "sentinel": {"name": "Sentinel",   "reputation_units": 50, "authority_units": 50, "probation": False, "zero_authority": False},
            "forge":    {"name": "Forge",      "reputation_units": 50, "authority_units": 50, "probation": False, "zero_authority": False},
            "quill":    {"name": "Quill",      "reputation_units": 50, "authority_units": 50, "probation": False, "zero_authority": False},
            "aegis":    {"name": "Aegis",      "reputation_units": 50, "authority_units": 50, "probation": False, "zero_authority": False},
            "pulse":    {"name": "Pulse",      "reputation_units": 50, "authority_units": 50, "probation": False, "zero_authority": False},
        },
        "treasury": {
            "cash_usd": 0.0,
            "reserve_floor_usd": 50.0,
            "total_revenue_usd": 0.0,
            "owner_capital_contributed_usd": 0.0,
            "owner_draws_usd": 0.0,
        },
        "epoch": 0,
        "transactions": [],
    }
    with open(ledger_path, 'w') as f:
        json.dump(ledger, f, indent=2)

    # Create revenue.json
    rev_path = os.path.join(ECONOMY_DIR, 'revenue.json')
    if not os.path.exists(rev_path):
        with open(rev_path, 'w') as f:
            json.dump({"clients": {}, "orders": {}, "receivables_usd": 0.0}, f, indent=2)


def init_kernel():
    """Run kernel bootstrap to initialize all primitives."""
    step("Running kernel bootstrap")
    try:
        from bootstrap import bootstrap
        bootstrap()
    except Exception as e:
        # Fallback: run bootstrap.py as script
        result = subprocess.run(
            [sys.executable, os.path.join(KERNEL_DIR, 'bootstrap.py')],
            capture_output=True, text=True, cwd=ROOT
        )
        if result.returncode != 0:
            print(f"  Bootstrap error: {result.stderr[:200]}")
            print("  Attempting manual initialization...")
            _manual_init()
        else:
            print(result.stdout)


def _manual_init():
    """Manual initialization if bootstrap fails."""
    from organizations import load_orgs, save_orgs, _now
    from agent_registry import load_registry, save_registry

    # Create org
    orgs = load_orgs()
    if not orgs.get('organizations'):
        orgs['organizations'] = {}
    if not any(o.get('slug') == 'meridian' for o in orgs.get('organizations', {}).values()):
        import uuid
        org_id = f'org_{uuid.uuid4().hex[:8]}'
        orgs['organizations'][org_id] = {
            'id': org_id,
            'name': 'Demo Org',
            'slug': 'demo-org',
            'plan': 'enterprise',
            'owner_id': 'user_owner',
            'members': [
                {'user_id': 'user_owner', 'role': 'owner', 'added_at': _now()}
            ],
            'charter': (
                'Reference demo institution for exercising Meridian governance locally '
                'across institution, agent, authority, treasury, and court.'
            ),
            'policy_defaults': {
                'max_budget_per_agent_usd': 10.0,
                'require_approval_above_usd': 5.0,
                'auto_sanctions_enabled': True,
                'auth_decay_per_epoch': 5,
            },
            'treasury_id': None,
            'lifecycle_state': 'active',
            'settings': {},
            'created_at': _now(),
            'updated_at': _now(),
        }
        save_orgs(orgs)
        step(f"Created institution: Demo Org ({org_id})")

    # Register agents
    AGENTS = [
        ('Leviathann', 'manager',    'main',     'Orchestrate pipeline, route work, close loops'),
        ('Atlas',      'analyst',    'atlas',    'Research, analysis, source extraction'),
        ('Sentinel',   'verifier',   'sentinel', 'Source verification, contradiction checking'),
        ('Forge',      'executor',   'forge',    'Implementation, execution, operational tasks'),
        ('Quill',      'writer',     'quill',    'Write intelligence briefs and deliverables'),
        ('Aegis',      'qa_gate',    'aegis',    'Quality acceptance gate — pass/fail decisions'),
        ('Pulse',      'compressor', 'pulse',    'Context compression, triage, delivery prep'),
    ]
    reg = load_registry()
    existing_names = {a['name'] for a in reg.get('agents', {}).values()}
    org_id = next((oid for oid, o in orgs['organizations'].items() if o.get('slug') == 'meridian'), '')

    for name, role, ekey, purpose in AGENTS:
        if name not in existing_names:
            import uuid
            agent_id = f'agent_{name.lower()}'
            reg['agents'][agent_id] = {
                'id': agent_id,
                'org_id': org_id,
                'name': name,
                'role': role,
                'purpose': purpose,
                'scopes': [],
                'budget': {'max_per_run_usd': 0.50, 'max_per_day_usd': 5.0},
                'model_policy': {},
                'rollout_state': 'active',
                'reputation_units': 50,
                'authority_units': 50,
                'last_active_at': _now(),
                'created_at': _now(),
                'sponsor_id': 'owner',
                'risk_state': 'nominal',
                'lifecycle_state': 'active',
                'economy_key': ekey,
                'incident_count': 0,
                'escalation_path': [],
            }
    save_registry(reg)
    step(f"Registered {len(AGENTS)} agents")


def show_status():
    """Print a quick summary of initialized state."""
    print(f"\n{'='*55}")
    print(f"  Meridian Constitutional Kernel — Ready")
    print(f"{'='*55}")

    try:
        from organizations import load_orgs
        orgs = load_orgs()
        for oid, org in orgs.get('organizations', {}).items():
            print(f"\n  Institution: {org['name']}")
            print(f"  Charter:     {org.get('charter', '(not set)')[:60]}")
            print(f"  Lifecycle:   {org.get('lifecycle_state', 'active')}")
    except Exception:
        pass

    try:
        from agent_registry import load_registry
        reg = load_registry()
        print(f"\n  Agents: {len(reg.get('agents', {}))}")
        for a in reg.get('agents', {}).values():
            print(f"    {a['name']:<12} role={a['role']:<10} REP={a.get('reputation_units',0):>3} AUTH={a.get('authority_units',0):>3} risk={a.get('risk_state','?')}")
    except Exception:
        pass

    try:
        ledger_path = os.path.join(ECONOMY_DIR, 'ledger.json')
        with open(ledger_path) as f:
            ledger = json.load(f)
        t = ledger.get('treasury', {})
        balance = t.get('cash_usd', 0)
        floor = t.get('reserve_floor_usd', 50)
        print(f"\n  Treasury:  ${balance:.2f} (reserve floor ${floor:.2f}, runway ${balance - floor:.2f})")
    except Exception:
        pass


def start_workspace(port):
    """Start the governed workspace server."""
    print(f"\n  Starting governed workspace on http://localhost:{port}")
    print(f"  Press Ctrl+C to stop.\n")
    subprocess.run(
        [sys.executable, os.path.join(KERNEL_DIR, 'workspace.py'), '--port', str(port)],
        cwd=ROOT
    )


def main():
    parser = argparse.ArgumentParser(
        description='Meridian Constitutional Kernel — Quickstart'
    )
    parser.add_argument('--port', type=int, default=18901,
                        help='Port for governed workspace (default: 18901)')
    parser.add_argument('--init-only', action='store_true',
                        help='Initialize without starting server')
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  Meridian Constitutional Kernel — Quickstart")
    print(f"{'='*55}")

    check_python_version()

    step("Checking Python version... OK")

    init_economy()
    init_kernel()
    show_status()

    if args.init_only:
        print(f"\n  Initialization complete.")
        print(f"  Run 'python3 kernel/workspace.py' to start the dashboard.")
    else:
        start_workspace(args.port)


if __name__ == '__main__':
    main()
