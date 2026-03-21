#!/usr/bin/env python3
"""
Treasury primitive for Meridian Kernel.

Read facade over economy/ledger.json treasury section + economy/revenue.py +
kernel/metering.py. Does NOT duplicate ledger writes -- reads from
authoritative sources.

Usage:
  python3 treasury.py balance
  python3 treasury.py runway
  python3 treasury.py spend [--org_id <org>] [--days 30]
  python3 treasury.py snapshot
  python3 treasury.py check-budget --agent_id <id> --cost 2.00
  python3 treasury.py contribute --amount 50.00 --note "owner top-up"
  python3 treasury.py set-reserve-floor --amount 20.00 --note "policy change"
  python3 treasury.py wallets
  python3 treasury.py accounts
  python3 treasury.py maintainers
  python3 treasury.py contributors
  python3 treasury.py proposals
  python3 treasury.py funding-sources
  python3 treasury.py check-payout-wallet --wallet_id <id>
"""
import argparse
import datetime
import json
import os
import sys

PLATFORM_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(PLATFORM_DIR)
ECONOMY_DIR = os.path.join(WORKSPACE, 'economy')

# Import economy modules (avoid name collision)
import importlib.util
_spec = importlib.util.spec_from_file_location('econ_revenue', os.path.join(ECONOMY_DIR, 'revenue.py'))
_econ_revenue_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_econ_revenue_mod)
load_revenue = _econ_revenue_mod.load_revenue
load_ledger = _econ_revenue_mod.load_ledger

# Optional accounting import -- accounting.py is a private company module.
# When not present, contribute/reserve-floor operations degrade gracefully.
_owner_contribute_capital = None
_update_reserve_floor = None
try:
    _accounting_path = os.path.join(WORKSPACE, 'accounting.py')
    if os.path.exists(_accounting_path):
        _accounting_spec = importlib.util.spec_from_file_location(
            'company_accounting', _accounting_path
        )
        _accounting_mod = importlib.util.module_from_spec(_accounting_spec)
        _accounting_spec.loader.exec_module(_accounting_mod)
        _owner_contribute_capital = _accounting_mod.contribute_capital
        _update_reserve_floor = _accounting_mod.update_reserve_floor
except Exception:
    pass

# Import platform metering
sys.path.insert(0, PLATFORM_DIR)
from metering import get_spend, summary as metering_summary
from agent_registry import check_budget as _agent_check_budget


def _now():
    return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


# -- Core functions -----------------------------------------------------------

def get_balance():
    """Read treasury.cash_usd from ledger.json."""
    ledger = load_ledger()
    return ledger['treasury']['cash_usd']


def get_reserve_floor():
    """Read treasury.reserve_floor_usd from ledger.json."""
    ledger = load_ledger()
    return ledger['treasury'].get('reserve_floor_usd', 50.0)


def get_runway():
    """Balance minus reserve floor. Negative means below reserve."""
    return get_balance() - get_reserve_floor()


def get_revenue_summary():
    """Read revenue state from economy/revenue.py."""
    rev = load_revenue()
    ledger = load_ledger()
    t = ledger['treasury']
    orders = rev.get('orders', {})
    paid = [o for o in orders.values() if o['status'] == 'paid']
    open_orders = [o for o in orders.values() if o['status'] not in ('paid', 'rejected')]
    return {
        'total_revenue_usd': t.get('total_revenue_usd', 0.0),
        'owner_capital_contributed_usd': t.get('owner_capital_contributed_usd', 0.0),
        'receivables_usd': rev.get('receivables_usd', 0.0),
        'clients': len(rev.get('clients', {})),
        'paid_orders': len(paid),
        'open_orders': len(open_orders),
    }


def get_spend_summary(org_id, period_days=30):
    """Aggregate spend from metering.jsonl."""
    since = (datetime.datetime.utcnow() -
             datetime.timedelta(days=period_days)).strftime('%Y-%m-%dT%H:%M:%SZ')
    total = get_spend(org_id, since=since)
    return {
        'org_id': org_id,
        'period_days': period_days,
        'total_spend_usd': round(total, 4),
    }


def contribute_owner_capital(amount_usd, note='', by='owner'):
    """Record owner capital contribution via the accounting layer.
    Falls back to direct ledger write if accounting module is not available."""
    if _owner_contribute_capital:
        return _owner_contribute_capital(amount_usd, note, actor=by)
    # Graceful fallback: write directly to ledger
    ledger = load_ledger()
    ledger['treasury']['cash_usd'] += amount_usd
    ledger['treasury']['owner_capital_contributed_usd'] = (
        ledger['treasury'].get('owner_capital_contributed_usd', 0.0) + amount_usd
    )
    ledger['updatedAt'] = _now()
    ledger_path = os.path.join(ECONOMY_DIR, 'ledger.json')
    with open(ledger_path, 'w') as f:
        json.dump(ledger, f, indent=2)
    # Append transaction for auditability
    tx_path = os.path.join(ECONOMY_DIR, 'transactions.jsonl')
    tx_entry = json.dumps({
        'type': 'treasury_deposit',
        'deposit_type': 'owner_capital',
        'amount_usd': amount_usd,
        'cash_after': ledger['treasury']['cash_usd'],
        'note': note,
        'ts': _now(),
    })
    with open(tx_path, 'a') as f:
        f.write(tx_entry + '\n')
    return {
        'amount_usd': amount_usd,
        'cash_after_usd': ledger['treasury']['cash_usd'],
        'note': note,
    }


def set_reserve_floor_policy(amount_usd, note='', by='owner'):
    """Update reserve floor policy via the accounting layer.
    Falls back to direct ledger write if accounting module is not available."""
    if _update_reserve_floor:
        return _update_reserve_floor(amount_usd, note, actor=by)
    # Graceful fallback: write directly to ledger
    ledger = load_ledger()
    old_floor = ledger['treasury'].get('reserve_floor_usd', 50.0)
    ledger['treasury']['reserve_floor_usd'] = amount_usd
    ledger['updatedAt'] = _now()
    ledger_path = os.path.join(ECONOMY_DIR, 'ledger.json')
    with open(ledger_path, 'w') as f:
        json.dump(ledger, f, indent=2)
    return {
        'old_reserve_floor_usd': old_floor,
        'new_reserve_floor_usd': amount_usd,
        'note': note,
    }


def check_budget(agent_id, cost_usd):
    """Check agent budget + treasury runway. Returns (allowed, reason)."""
    # Try economy_key -> registry ID mapping first
    from agent_registry import get_agent_by_economy_key
    reg_agent = get_agent_by_economy_key(agent_id)
    lookup_id = reg_agent['id'] if reg_agent else agent_id

    # Check agent-level budget
    allowed, reason = _agent_check_budget(lookup_id, cost_usd)
    if not allowed:
        return False, reason
    # Then check treasury runway -- negative runway blocks all spending
    runway = get_runway()
    if runway < 0:
        return False, f'Treasury below reserve floor (runway ${runway:.2f}). Recapitalize before spending.'
    if runway < cost_usd:
        return False, f'Treasury runway insufficient (${runway:.2f} available, ${cost_usd:.2f} requested)'
    return True, 'ok'


def record_expense(org_id, agent_id, amount_usd, category, description):
    """Record expense via metering + audit."""
    from metering import record as meter_record
    try:
        from audit import log_event
        log_event(org_id, agent_id, 'expense_recorded',
                  resource=category, outcome='success',
                  details={'amount_usd': amount_usd, 'description': description})
    except Exception:
        pass
    meter_record(org_id, agent_id, f'expense:{category}',
                 quantity=1, unit='transactions', cost_usd=amount_usd,
                 details={'description': description})


def can_payout(amount_usd):
    """Check if a payout is possible (balance > reserve_floor + amount)."""
    balance = get_balance()
    floor = get_reserve_floor()
    return balance >= floor + amount_usd


# -- Protocol registry readers ------------------------------------------------

TREASURY_DIR = os.path.join(WORKSPACE, 'treasury')


def _load_registry_file(filename):
    """Load a JSON registry file from the treasury directory. Returns empty dict on missing file."""
    path = os.path.join(TREASURY_DIR, filename)
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        return json.load(f)


def load_wallets():
    """Load wallet registry from treasury/wallets.json."""
    return _load_registry_file('wallets.json')


def load_treasury_accounts():
    """Load treasury accounts from treasury/treasury_accounts.json."""
    return _load_registry_file('treasury_accounts.json')


def load_maintainers():
    """Load maintainer registry from treasury/maintainers.json."""
    return _load_registry_file('maintainers.json')


def load_contributors():
    """Load contributor registry from treasury/contributors.json."""
    return _load_registry_file('contributors.json')


def load_payout_proposals():
    """Load payout proposals from treasury/payout_proposals.json."""
    return _load_registry_file('payout_proposals.json')


def load_funding_sources():
    """Load funding sources from treasury/funding_sources.json."""
    return _load_registry_file('funding_sources.json')


def get_wallet(wallet_id):
    """Get a single wallet by ID. Returns None if not found."""
    wallets = load_wallets()
    return wallets.get('wallets', {}).get(wallet_id)


def get_payout_eligible_wallets():
    """Return dict of wallets with verification Level 3+."""
    wallets = load_wallets()
    return {wid: w for wid, w in wallets.get('wallets', {}).items()
            if (w.get('verification_level') or 0) >= 3 and w.get('payout_eligible')}


def can_receive_payout(wallet_id):
    """Check if a wallet can receive payouts. Returns (bool, reason)."""
    wallet = get_wallet(wallet_id)
    if not wallet:
        return False, f'Wallet {wallet_id} not found in registry'
    level = wallet.get('verification_level')
    if level is None:
        return False, f'Wallet {wallet_id} has no verification level (status: {wallet.get("status")})'
    if level < 3:
        label = wallet.get('verification_label', 'unknown')
        return False, f'Wallet {wallet_id} is Level {level} ({label}). Minimum Level 3 (self_custody_verified) required.'
    if not wallet.get('payout_eligible'):
        return False, f'Wallet {wallet_id} is Level {level} but payout_eligible is false'
    if wallet.get('status') != 'active':
        return False, f'Wallet {wallet_id} status is {wallet.get("status")}, must be active'
    return True, f'Wallet {wallet_id} is Level {level} ({wallet.get("verification_label")}), payout eligible'


def treasury_snapshot():
    """Combined view: balance, revenue, spend, runway, reserve status."""
    ledger = load_ledger()
    t = ledger['treasury']
    rev_summary = get_revenue_summary()

    # Try to get default org for spend
    spend_usd = 0.0
    org_id = None
    try:
        from organizations import load_orgs
        for oid, org in load_orgs().get('organizations', {}).items():
            org_id = oid
            break
        if org_id:
            spend_usd = get_spend_summary(org_id, 30)['total_spend_usd']
    except Exception:
        pass

    balance = t['cash_usd']
    floor = t.get('reserve_floor_usd', 50.0)
    runway = balance - floor
    shortfall = max(0.0, floor - balance)
    remediation = {
        'blocked': runway < 0,
        'shortfall_usd': shortfall,
        'recommended_owner_capital_usd': shortfall,
        'recommended_reserve_floor_usd': max(0.0, balance),
        'next_steps': [],
    }
    if shortfall > 0:
        remediation['next_steps'].append(
            f"Record at least ${shortfall:.2f} of real owner capital or customer cash before running budget-gated phases."
        )
        remediation['next_steps'].append(
            f"If policy truly changed, explicitly lower reserve floor from ${floor:.2f} with an auditable note."
        )

    # Protocol summary
    protocol = {
        'wallet_count': len(load_wallets().get('wallets', {})),
        'payout_eligible_wallets': len(get_payout_eligible_wallets()),
        'maintainer_count': len(load_maintainers().get('maintainers', {})),
        'contributor_count': len(load_contributors().get('contributors', {})),
        'pending_proposals': len([p for p in load_payout_proposals().get('proposals', {}).values()
                                  if p.get('status') in ('submitted', 'under_review')]),
        'funding_sources': len(load_funding_sources().get('sources', {})),
    }

    return {
        'balance_usd': balance,
        'reserve_floor_usd': floor,
        'runway_usd': runway,
        'shortfall_usd': shortfall,
        'above_reserve': runway >= 0,
        'total_revenue_usd': t.get('total_revenue_usd', 0.0),
        'owner_capital_usd': t.get('owner_capital_contributed_usd', 0.0),
        'owner_draws_usd': t.get('owner_draws_usd', 0.0),
        'receivables_usd': rev_summary['receivables_usd'],
        'spend_30d_usd': spend_usd,
        'clients': rev_summary['clients'],
        'paid_orders': rev_summary['paid_orders'],
        'protocol': protocol,
        'remediation': remediation,
        'snapshot_at': _now(),
    }


# -- CLI ----------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description='Treasury primitive -- financial read facade')
    sub = p.add_subparsers(dest='command')

    sub.add_parser('balance')
    sub.add_parser('runway')

    sp = sub.add_parser('spend')
    sp.add_argument('--org_id', default=None)
    sp.add_argument('--days', type=int, default=30)

    sub.add_parser('snapshot')

    cb = sub.add_parser('check-budget')
    cb.add_argument('--agent_id', required=True)
    cb.add_argument('--cost', type=float, required=True)

    cc = sub.add_parser('contribute')
    cc.add_argument('--amount', type=float, required=True)
    cc.add_argument('--note', default='owner top-up')
    cc.add_argument('--by', default='owner')

    rf = sub.add_parser('set-reserve-floor')
    rf.add_argument('--amount', type=float, required=True)
    rf.add_argument('--note', default='reserve policy update')
    rf.add_argument('--by', default='owner')

    sub.add_parser('wallets')
    sub.add_parser('accounts')
    sub.add_parser('maintainers')
    sub.add_parser('contributors')
    sub.add_parser('proposals')
    sub.add_parser('funding-sources')

    cpw = sub.add_parser('check-payout-wallet')
    cpw.add_argument('--wallet_id', required=True)

    args = p.parse_args()

    if args.command == 'balance':
        print(f'Treasury balance: ${get_balance():.2f}')
    elif args.command == 'runway':
        runway = get_runway()
        floor = get_reserve_floor()
        status = 'ABOVE reserve' if runway >= 0 else 'BELOW reserve'
        print(f'Runway: ${runway:.2f} ({status}, floor=${floor:.2f})')
    elif args.command == 'spend':
        org_id = args.org_id
        if not org_id:
            try:
                from organizations import load_orgs
                for oid, org in load_orgs().get('organizations', {}).items():
                    org_id = oid
                    break
            except Exception:
                pass
        if org_id:
            s = get_spend_summary(org_id, args.days)
            print(f'Spend ({s["period_days"]}d): ${s["total_spend_usd"]:.4f}')
        else:
            print('No org found for spend query')
    elif args.command == 'snapshot':
        snap = treasury_snapshot()
        print(f"\n=== Treasury Snapshot ({snap['snapshot_at']}) ===")
        print(f"Balance:         ${snap['balance_usd']:.2f}")
        print(f"Reserve floor:   ${snap['reserve_floor_usd']:.2f}")
        print(f"Runway:          ${snap['runway_usd']:.2f} {'(OK)' if snap['above_reserve'] else '(BELOW RESERVE)'}")
        print(f"Revenue:         ${snap['total_revenue_usd']:.2f}")
        print(f"Owner capital:   ${snap['owner_capital_usd']:.2f}")
        print(f"Owner draws:     ${snap['owner_draws_usd']:.2f}")
        print(f"Receivables:     ${snap['receivables_usd']:.2f}")
        print(f"Spend (30d):     ${snap['spend_30d_usd']:.4f}")
        print(f"Clients:         {snap['clients']}")
        print(f"Paid orders:     {snap['paid_orders']}")
        proto = snap.get('protocol', {})
        if proto:
            print(f"\n--- Protocol ---")
            print(f"Wallets:         {proto.get('wallet_count', 0)} ({proto.get('payout_eligible_wallets', 0)} payout-eligible)")
            print(f"Maintainers:     {proto.get('maintainer_count', 0)}")
            print(f"Contributors:    {proto.get('contributor_count', 0)}")
            print(f"Pending proposals: {proto.get('pending_proposals', 0)}")
            print(f"Funding sources: {proto.get('funding_sources', 0)}")
    elif args.command == 'check-budget':
        allowed, reason = check_budget(args.agent_id, args.cost)
        status = 'ALLOWED' if allowed else 'BLOCKED'
        print(f'{status}: {reason}')
        sys.exit(0 if allowed else 1)
    elif args.command == 'contribute':
        result = contribute_owner_capital(args.amount, args.note, args.by)
        print(f"Capital contribution recorded: +${result['amount_usd']:.2f} | cash now ${result['cash_after_usd']:.2f}")
    elif args.command == 'set-reserve-floor':
        result = set_reserve_floor_policy(args.amount, args.note, args.by)
        print(f"Reserve floor updated: ${result['old_reserve_floor_usd']:.2f} -> ${result['new_reserve_floor_usd']:.2f}")
    elif args.command == 'wallets':
        data = load_wallets()
        wallets = data.get('wallets', {})
        if not wallets:
            print('No wallets registered.')
        else:
            print(f'\n=== Wallet Registry ({len(wallets)} entries) ===')
            for wid, w in wallets.items():
                level = w.get('verification_level')
                level_str = f"L{level}" if level is not None else "L?"
                label = w.get('verification_label', '?')
                addr = w.get('address') or '(not deployed)'
                eligible = 'ELIGIBLE' if w.get('payout_eligible') else 'NOT ELIGIBLE'
                print(f"  {wid}: {addr} | {level_str} ({label}) | {eligible} | {w.get('status')}")
    elif args.command == 'accounts':
        data = load_treasury_accounts()
        accounts = data.get('accounts', {})
        if not accounts:
            print('No treasury accounts defined.')
        else:
            print(f'\n=== Treasury Accounts ({len(accounts)}) ===')
            for aid, a in accounts.items():
                print(f"  {aid}: ${a.get('balance_usd', 0):.2f} (reserve ${a.get('reserve_floor_usd', 0):.2f}) | {a.get('status')}")
    elif args.command == 'maintainers':
        data = load_maintainers()
        maintainers = data.get('maintainers', {})
        if not maintainers:
            print('No maintainers registered.')
        else:
            print(f'\n=== Maintainers ({len(maintainers)}) ===')
            for mid, m in maintainers.items():
                wallet = m.get('payout_wallet_id') or 'none'
                print(f"  {m.get('name')} ({m.get('github')}) | role={m.get('role')} | wallet={wallet} | {m.get('status')}")
    elif args.command == 'contributors':
        data = load_contributors()
        contributors = data.get('contributors', {})
        if not contributors:
            print('No contributors registered.')
        else:
            print(f'\n=== Contributors ({len(contributors)}) ===')
            for cid, c in contributors.items():
                print(f"  {c.get('name', cid)} ({c.get('github', '?')}) | {c.get('status', '?')}")
    elif args.command == 'proposals':
        data = load_payout_proposals()
        proposals = data.get('proposals', {})
        if not proposals:
            print('No payout proposals.')
        else:
            print(f'\n=== Payout Proposals ({len(proposals)}) ===')
            for pid, p_ in proposals.items():
                print(f"  {pid}: ${p_.get('amount_usd', 0):.2f} | {p_.get('status')} | {p_.get('contributor_id')}")
    elif args.command == 'funding-sources':
        data = load_funding_sources()
        sources = data.get('sources', {})
        if not sources:
            print('No funding sources recorded.')
        else:
            print(f'\n=== Funding Sources ({len(sources)}) ===')
            for sid, s in sources.items():
                print(f"  {sid}: ${s.get('amount_usd', 0):.2f} {s.get('currency', '')} | {s.get('type')} | {s.get('recorded_at')}")
    elif args.command == 'check-payout-wallet':
        eligible, reason = can_receive_payout(args.wallet_id)
        status = 'ELIGIBLE' if eligible else 'BLOCKED'
        print(f'{status}: {reason}')
        sys.exit(0 if eligible else 1)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
