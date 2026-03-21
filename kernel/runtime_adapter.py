#!/usr/bin/env python3
"""
Runtime Adapter primitive for Meridian Kernel.

Meridian is runtime-neutral. This module provides:
  - A machine-readable registry of governed runtimes (kernel/runtimes.json)
  - A registry-based constitutional contract assessment for each runtime
  - CLI for listing and inspecting runtimes

Meridian does not execute agents. It governs them. Any runtime that satisfies
the seven constitutional contract requirements can have its agents governed by
Meridian's five primitives: Institution, Agent, Authority, Treasury, Court.

Constitutional contract requirements are defined in kernel/runtimes.json
and documented in docs/RUNTIME_CONTRACT.md.

Usage:
  python3 runtime_adapter.py list
  python3 runtime_adapter.py show --runtime_id mcp_generic
  python3 runtime_adapter.py check-contract --runtime_id openclaw_compatible
  python3 runtime_adapter.py register --id my_runtime --label "My Runtime" \
      --type hosted --protocols "MCP,A2A" --identity_mode api_key
"""
import argparse
import datetime
import json
import os
import sys

PLATFORM_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_FILE = os.path.join(PLATFORM_DIR, 'runtimes.json')


def _now():
    return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


# -- Registry I/O -------------------------------------------------------------

def load_runtimes():
    """Load runtime registry from kernel/runtimes.json."""
    if not os.path.exists(REGISTRY_FILE):
        return {'runtimes': {}, 'contract_requirements': {}, 'updatedAt': _now()}
    with open(REGISTRY_FILE) as f:
        return json.load(f)


def save_runtimes(data):
    """Save runtime registry."""
    data['updatedAt'] = _now()
    with open(REGISTRY_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def get_runtime(runtime_id):
    """Get a single runtime by ID. Returns None if not found."""
    return load_runtimes().get('runtimes', {}).get(runtime_id)


# -- Contract checking --------------------------------------------------------

def check_contract(runtime_id):
    """
    Assess a runtime's declared Meridian constitutional contract compliance.

    This is a registry-backed assessment, not an active conformance probe.
    It reports what the runtime entry declares in kernel/runtimes.json.

    Returns a dict:
      {
        'runtime_id': str,
        'satisfied': [list of satisfied requirement IDs],
        'gaps': [list of unsatisfied requirement IDs],
        'unknown': [list of requirement IDs with null compliance],
        'score': int (0-7),
        'status': 'compliant' | 'partial' | 'non_compliant' | 'unknown',
        'verdict': str,
      }
    """
    data = load_runtimes()
    runtime = data.get('runtimes', {}).get(runtime_id)
    if not runtime:
        return {
            'runtime_id': runtime_id,
            'error': f'Runtime {runtime_id!r} not found in registry',
        }

    requirements = list(data.get('contract_requirements', {}).keys())
    thresholds = data.get('compliance_thresholds', {'compliant': 7, 'partial': 4})
    compliance = runtime.get('contract_compliance', {})

    satisfied = [r for r in requirements if compliance.get(r) is True]
    gaps = [r for r in requirements if compliance.get(r) is False]
    unknown = [r for r in requirements if compliance.get(r) is None]

    score = len(satisfied)
    if score >= thresholds.get('compliant', 7):
        status = 'compliant'
    elif score >= thresholds.get('partial', 4):
        status = 'partial'
    elif unknown and score == 0 and not gaps:
        status = 'unknown'
    else:
        status = 'non_compliant'

    if status == 'compliant':
        verdict = (
            f"Registry metadata says runtime {runtime_id!r} satisfies all "
            f"{score} constitutional contract requirements."
        )
    elif status == 'partial':
        verdict = (
            f"Registry metadata says runtime {runtime_id!r} satisfies "
            f"{score}/{len(requirements)} requirements. "
            f'Gaps: {", ".join(gaps + unknown)}. Active adapter verification is still required.'
        )
    elif status == 'unknown':
        verdict = (
            f"Runtime {runtime_id!r} has no declared compliance data. "
            'Runtime API review is required before an adapter can be built.'
        )
    else:
        unmet = gaps + unknown
        verdict = (
            f"Registry metadata says runtime {runtime_id!r} satisfies only "
            f"{score}/{len(requirements)} requirements. "
            f'Not governable without significant adapter work. '
            f'Unmet/unknown: {", ".join(unmet)}.'
        )

    return {
        'runtime_id': runtime_id,
        'label': runtime.get('label', runtime_id),
        'assessment_basis': 'registry_metadata',
        'satisfied': satisfied,
        'gaps': gaps,
        'unknown': unknown,
        'score': score,
        'total': len(requirements),
        'status': status,
        'verdict': verdict,
    }


def check_all_contracts():
    """Run contract check for every registered runtime."""
    data = load_runtimes()
    results = {}
    for rid in data.get('runtimes', {}):
        results[rid] = check_contract(rid)
    return results


# -- Runtime registration -----------------------------------------------------

def register_runtime(runtime_id, label, runtime_type, protocols, identity_mode,
                     execution_ownership='runtime', notes=''):
    """Register a new runtime in the registry."""
    data = load_runtimes()
    if runtime_id in data.get('runtimes', {}):
        raise ValueError(f'Runtime {runtime_id!r} already exists. Use update instead.')
    requirements = list(data.get('contract_requirements', {}).keys())
    entry = {
        'id': runtime_id,
        'label': label,
        'description': label,
        'type': runtime_type,
        'protocol_support': [p.strip() for p in protocols.split(',') if p.strip()],
        'identity_mode': identity_mode,
        'execution_ownership': execution_ownership,
        'capability_exposure': [],
        'contract_compliance': {r: None for r in requirements},
        'integration': {'treasury': 'none', 'audit': 'none', 'court': 'none'},
        'adapter_available': False,
        'status': 'planned',
        'notes': notes,
        'registered_at': _now(),
    }
    if 'runtimes' not in data:
        data['runtimes'] = {}
    data['runtimes'][runtime_id] = entry
    save_runtimes(data)
    return entry


# -- Adapter integration helpers (callable by runtime implementations) --------

def get_contract_requirements():
    """Return the seven constitutional contract requirements as a dict."""
    return load_runtimes().get('contract_requirements', {})


def get_compliant_runtimes():
    """Return list of runtime IDs that are fully contract-compliant."""
    data = load_runtimes()
    thresholds = data.get('compliance_thresholds', {'compliant': 7})
    results = []
    for rid, rt in data.get('runtimes', {}).items():
        compliance = rt.get('contract_compliance', {})
        score = sum(1 for v in compliance.values() if v is True)
        if score >= thresholds.get('compliant', 7):
            results.append(rid)
    return results


# -- CLI ----------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description='Runtime Adapter primitive -- registry and contract checker')
    sub = p.add_subparsers(dest='command')

    sub.add_parser('list')

    sh = sub.add_parser('show')
    sh.add_argument('--runtime_id', required=True)

    cc = sub.add_parser('check-contract')
    cc.add_argument('--runtime_id', required=True)

    sub.add_parser('check-all')

    reg = sub.add_parser('register')
    reg.add_argument('--id', required=True, dest='runtime_id')
    reg.add_argument('--label', required=True)
    reg.add_argument('--type', required=True, dest='runtime_type')
    reg.add_argument('--protocols', required=True,
                     help='Comma-separated: MCP,A2A,custom,etc.')
    reg.add_argument('--identity_mode', required=True)
    reg.add_argument('--execution_ownership', default='runtime')
    reg.add_argument('--notes', default='')

    args = p.parse_args()

    if args.command == 'list':
        data = load_runtimes()
        runtimes = data.get('runtimes', {})
        if not runtimes:
            print('No runtimes registered.')
            return
        print(f'\n=== Runtime Registry ({len(runtimes)} runtimes) ===')
        for rid, rt in runtimes.items():
            compliance = rt.get('contract_compliance', {})
            score = sum(1 for v in compliance.values() if v is True)
            total = len(compliance)
            print(f"  {rid}: {rt.get('label')} | type={rt.get('type')} | "
                  f"contract={score}/{total} | status={rt.get('status')} | "
                  f"adapter={'YES' if rt.get('adapter_available') else 'no'}")

    elif args.command == 'show':
        rt = get_runtime(args.runtime_id)
        if not rt:
            print(f'Runtime {args.runtime_id!r} not found.')
            sys.exit(1)
        print(json.dumps(rt, indent=2))

    elif args.command == 'check-contract':
        result = check_contract(args.runtime_id)
        if 'error' in result:
            print(f'ERROR: {result["error"]}')
            sys.exit(1)
        status = result['status'].upper()
        print(f'\n=== Contract Check: {args.runtime_id} ===')
        print(f'Status:    {status}')
        print(f'Score:     {result["score"]}/{result["total"]}')
        if result['satisfied']:
            print(f'Satisfied: {", ".join(result["satisfied"])}')
        if result['gaps']:
            print(f'Gaps:      {", ".join(result["gaps"])}')
        if result['unknown']:
            print(f'Unknown:   {", ".join(result["unknown"])}')
        print(f'Verdict:   {result["verdict"]}')
        sys.exit(0 if result['status'] == 'compliant' else 1)

    elif args.command == 'check-all':
        results = check_all_contracts()
        print(f'\n=== Contract Check: All Runtimes ===')
        for rid, result in results.items():
            if 'error' in result:
                print(f'  {rid}: ERROR -- {result["error"]}')
            else:
                print(f'  {rid}: {result["status"].upper()} ({result["score"]}/{result["total"]})')

    elif args.command == 'register':
        entry = register_runtime(
            args.runtime_id, args.label, args.runtime_type,
            args.protocols, args.identity_mode,
            args.execution_ownership, args.notes)
        print(f'Runtime registered: {entry["id"]} (status: {entry["status"]})')

    else:
        p.print_help()


if __name__ == '__main__':
    main()
