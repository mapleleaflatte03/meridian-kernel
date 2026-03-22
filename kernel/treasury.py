#!/usr/bin/env python3
"""
Treasury primitive for Meridian Kernel.

Governance facade over the institution's capsule ledger, revenue state, and
metering data.  Reads resolve through capsule_path(org_id, ...) which
defaults to economy/ for the founding institution.  Write operations
(contribute, set-reserve-floor) delegate to the accounting layer when
available and fall back to direct capsule-path writes otherwise.

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
import uuid

PLATFORM_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(PLATFORM_DIR)
ECONOMY_DIR = os.path.join(WORKSPACE, 'economy')
LEGACY_TREASURY_DIR = os.path.join(WORKSPACE, 'treasury')

if PLATFORM_DIR not in sys.path:
    sys.path.insert(0, PLATFORM_DIR)

try:
    from capsule import capsule_path
except ImportError:
    def capsule_path(org_id, filename):
        return os.path.join(ECONOMY_DIR, filename)

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
from metering import get_spend, summary as metering_summary
from agent_registry import check_budget as _agent_check_budget
import commitments

try:
    from phase_machine import current_phase as _current_phase
except Exception:
    _current_phase = None


def _now():
    return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def _parse_ts(value):
    return datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')


_PROTOCOL_DEFAULTS = {
    'wallets.json': {
        'wallets': {},
        'verification_levels': {
            '0': {'label': 'observed_only', 'description': 'Seen on-chain, no ownership proof', 'payout_eligible': False},
            '1': {'label': 'linked', 'description': 'Owner claims ownership, no crypto proof', 'payout_eligible': False},
            '2': {'label': 'exchange_linked', 'description': 'Exchange deposit screen, NOT self-custody', 'payout_eligible': False},
            '3': {'label': 'self_custody_verified', 'description': 'SIWE signature or equivalent', 'payout_eligible': True},
            '4': {'label': 'multisig_controlled', 'description': 'Safe or similar multisig', 'payout_eligible': True},
        },
    },
    'treasury_accounts.json': {
        'accounts': {},
        'transfer_policy': {
            'requires_owner_approval': True,
            'must_maintain_reserve': True,
            'audit_required': True,
        },
    },
    'maintainers.json': {
        'maintainers': {},
        'roles': {
            'bdfl': 'Benevolent Dictator For Life -- final authority on project direction and treasury',
            'core': 'Core maintainer with merge rights and payout eligibility',
            'maintainer': 'Active maintainer with review and triage rights',
        },
    },
    'contributors.json': {
        'contributors': {},
        'contribution_types': [
            'code',
            'documentation',
            'security_report',
            'bug_report',
            'design',
            'vertical_example',
            'test_coverage',
            'review',
            'community',
        ],
        'registration_requirements': {
            'github_account': True,
            'signed_commits': False,
            'payout_wallet_level': 3,
            'notes': 'Contributors register by submitting accepted PRs. Payout eligibility requires a Level 3+ verified wallet.',
        },
    },
    'payout_proposals.json': {
        'proposals': {},
        'state_machine': {
            'states': ['draft', 'submitted', 'under_review', 'approved', 'dispute_window', 'executed', 'rejected', 'cancelled'],
            'transitions': {
                'draft': ['submitted', 'cancelled'],
                'submitted': ['under_review', 'rejected', 'cancelled'],
                'under_review': ['approved', 'rejected'],
                'approved': ['dispute_window'],
                'dispute_window': ['executed', 'rejected'],
                'executed': [],
                'rejected': [],
                'cancelled': [],
            },
            'dispute_window_hours': 72,
            'notes': 'Proposals require evidence of contribution, a reviewer, and owner approval. 72-hour dispute window between approval and execution.',
        },
        'proposal_schema': {
            'id': 'string -- unique proposal ID',
            'contributor_id': 'string -- references contributors.json',
            'amount_usd': 'number -- payout amount',
            'currency': 'string -- USDC or other',
            'contribution_type': 'string -- from contribution_types list',
            'evidence': {
                'pr_urls': ['list of PR URLs'],
                'commit_hashes': ['list of commit hashes'],
                'issue_refs': ['list of issue references'],
                'description': 'string -- summary of contribution',
            },
            'recipient_wallet_id': 'string -- references wallets.json, must be Level 3+',
            'proposed_by': 'string -- who created the proposal',
            'reviewed_by': 'string -- who reviewed',
            'approved_by': 'string -- who approved (must be owner or delegated authority)',
            'status': 'string -- from state_machine.states',
            'settlement_adapter': 'string -- adapter_id from settlement_adapters.json',
            'warrant_id': 'string or null -- executable warrant bound to payout execution',
            'created_at': 'ISO 8601 timestamp',
            'updated_at': 'ISO 8601 timestamp',
            'dispute_window_ends_at': 'ISO 8601 timestamp or null',
            'executed_at': 'ISO 8601 timestamp or null',
            'tx_hash': 'string or null -- on-chain transaction hash',
            'execution_refs': 'object -- normalized settlement proof, tx_ref, and verification/finality states',
        },
    },
    'settlement_adapters.json': {
        'default_payout_adapter': 'internal_ledger',
        'adapters': {
            'internal_ledger': {
                'label': 'Internal Ledger',
                'status': 'active',
                'payout_execution_enabled': True,
                'execution_mode': 'host_ledger',
                'settlement_path': 'journal_append',
                'supported_currencies': ['USDC', 'USD'],
                'requires_tx_hash': False,
                'requires_settlement_proof': False,
                'proof_type': 'ledger_transaction',
                'verification_state': 'host_ledger_final',
                'finality_state': 'host_local_final',
                'reversal_or_dispute_capability': 'court_case',
                'dispute_model': 'court_case',
                'finality_model': 'host_local_final',
                'notes': 'Reference payout adapter. Execution settles by appending an auditable institution-ledger transaction.',
            },
            'base_usdc_x402': {
                'label': 'Base USDC via x402',
                'status': 'registered',
                'payout_execution_enabled': False,
                'execution_mode': 'external_chain',
                'settlement_path': 'x402_onchain',
                'supported_currencies': ['USDC'],
                'requires_tx_hash': True,
                'requires_settlement_proof': True,
                'proof_type': 'onchain_receipt',
                'verification_state': 'external_verification_required',
                'finality_state': 'external_chain_finality',
                'reversal_or_dispute_capability': 'court_case_plus_chain_review',
                'dispute_model': 'court_case_plus_chain_review',
                'finality_model': 'external_chain_finality',
                'notes': 'Registered contract target only. Reference payout execution stays disabled until adapter-specific verification exists.',
            },
            'manual_bank_wire': {
                'label': 'Manual Bank Wire',
                'status': 'registered',
                'payout_execution_enabled': False,
                'execution_mode': 'manual_offchain',
                'settlement_path': 'manual_bank_review',
                'supported_currencies': ['USD'],
                'requires_tx_hash': False,
                'requires_settlement_proof': True,
                'proof_type': 'manual_wire_receipt',
                'verification_state': 'manual_review_required',
                'finality_state': 'manual_settlement_pending',
                'reversal_or_dispute_capability': 'manual_reversal_and_court_case',
                'dispute_model': 'manual_reversal_and_court_case',
                'finality_model': 'manual_settlement_pending',
                'notes': 'Registered but intentionally not executable on the reference path.',
            },
        },
    },
    'funding_sources.json': {
        'sources': {},
        'source_types': {
            'owner_capital': 'Direct capital contribution from project owner',
            'github_sponsors': 'Recurring or one-time sponsorship via GitHub Sponsors',
            'direct_crypto': 'Direct stablecoin transfer from identified sponsor',
            'customer_payment': 'Payment for a product or service',
            'grant': 'Grant from a foundation or organization',
            'reimbursement': 'Reimbursement of expenses previously paid out-of-pocket',
        },
    },
}


def _default_org_id():
    try:
        from organizations import load_orgs
        for oid in load_orgs().get('organizations', {}):
            return oid
    except Exception:
        pass
    return None


def _protocol_path(filename, org_id=None):
    return capsule_path(org_id, filename)


def _is_economy_capsule(path):
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(ECONOMY_DIR)]) == os.path.abspath(ECONOMY_DIR)
    except ValueError:
        return False


def _missing_org_error(org_id):
    raise SystemExit(
        f"ERROR: institution '{org_id}' is not initialized. Run quickstart.py --init-only or bootstrap the capsule first."
    )


def _ensure_protocol_registry(filename, org_id=None):
    path = _protocol_path(filename, org_id)
    parent = os.path.dirname(path)
    if org_id and not os.path.isdir(parent):
        _missing_org_error(org_id)
    if os.path.exists(path):
        return path

    legacy_path = os.path.join(LEGACY_TREASURY_DIR, filename)
    if _is_economy_capsule(path) and os.path.exists(legacy_path):
        os.makedirs(parent, exist_ok=True)
        with open(legacy_path) as f:
            data = json.load(f)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        return path

    os.makedirs(parent, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(_PROTOCOL_DEFAULTS[filename], f, indent=2)
    return path


# -- Core functions -----------------------------------------------------------

def get_balance(org_id=None):
    """Read treasury.cash_usd from ledger.json."""
    ledger = load_ledger(org_id)
    return ledger['treasury']['cash_usd']


def get_reserve_floor(org_id=None):
    """Read treasury.reserve_floor_usd from ledger.json."""
    ledger = load_ledger(org_id)
    return ledger['treasury'].get('reserve_floor_usd', 50.0)


def get_runway(org_id=None):
    """Balance minus reserve floor. Negative means below reserve."""
    return get_balance(org_id) - get_reserve_floor(org_id)


def get_revenue_summary(org_id=None):
    """Read revenue state from economy/revenue.py."""
    rev = load_revenue(org_id)
    ledger = load_ledger(org_id)
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


def contribute_owner_capital(amount_usd, note='', by='owner', org_id=None):
    """Record owner capital contribution via the accounting layer.
    Falls back to direct ledger write if accounting module is not available."""
    # Accounting module is founding-service-only (single-institution).
    # Route through it only for the founding org (org_id=None).
    # Non-founding orgs use the direct capsule-path fallback below.
    if _owner_contribute_capital and org_id is None:
        return _owner_contribute_capital(amount_usd, note, actor=by)
    # Graceful fallback: write directly to ledger
    ledger = load_ledger(org_id)
    ledger['treasury']['cash_usd'] += amount_usd
    ledger['treasury']['owner_capital_contributed_usd'] = (
        ledger['treasury'].get('owner_capital_contributed_usd', 0.0) + amount_usd
    )
    ledger['updatedAt'] = _now()
    ledger_path = capsule_path(org_id, 'ledger.json')
    if org_id and not os.path.isdir(os.path.dirname(ledger_path)):
        _missing_org_error(org_id)
    with open(ledger_path, 'w') as f:
        json.dump(ledger, f, indent=2)
    # Append transaction for auditability
    tx_path = capsule_path(org_id, 'transactions.jsonl')
    if org_id and not os.path.isdir(os.path.dirname(tx_path)):
        _missing_org_error(org_id)
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


def set_reserve_floor_policy(amount_usd, note='', by='owner', org_id=None):
    """Update reserve floor policy via the accounting layer.
    Falls back to direct ledger write if accounting module is not available."""
    if _update_reserve_floor and org_id is None:
        return _update_reserve_floor(amount_usd, note, actor=by)
    # Graceful fallback: write directly to ledger
    ledger = load_ledger(org_id)
    old_floor = ledger['treasury'].get('reserve_floor_usd', 50.0)
    ledger['treasury']['reserve_floor_usd'] = amount_usd
    ledger['updatedAt'] = _now()
    ledger_path = capsule_path(org_id, 'ledger.json')
    if org_id and not os.path.isdir(os.path.dirname(ledger_path)):
        _missing_org_error(org_id)
    with open(ledger_path, 'w') as f:
        json.dump(ledger, f, indent=2)
    return {
        'old_reserve_floor_usd': old_floor,
        'new_reserve_floor_usd': amount_usd,
        'note': note,
    }


def check_budget(agent_id, cost_usd, org_id=None):
    """Check agent budget + treasury runway. Returns (allowed, reason)."""
    # Try economy_key -> registry ID mapping first
    from agent_registry import get_agent_by_economy_key
    reg_agent = get_agent_by_economy_key(agent_id, org_id=org_id)
    lookup_id = reg_agent['id'] if reg_agent else agent_id

    # Check agent-level budget
    allowed, reason = _agent_check_budget(lookup_id, cost_usd)
    if not allowed:
        return False, reason
    # Then check treasury runway -- negative runway blocks all spending
    runway = get_runway(org_id)
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


def can_payout(amount_usd, org_id=None):
    """Check if a payout is possible (balance > reserve_floor + amount)."""
    balance = get_balance(org_id)
    floor = get_reserve_floor(org_id)
    return balance >= floor + amount_usd


# -- Protocol registry readers ------------------------------------------------


def _load_registry_file(filename, org_id=None):
    """Load a JSON registry file from the institution capsule."""
    path = _ensure_protocol_registry(filename, org_id)
    with open(path, 'r') as f:
        return json.load(f)


def _save_registry_file(filename, payload, org_id=None):
    """Persist a JSON registry file inside the institution capsule."""
    path = _ensure_protocol_registry(filename, org_id)
    parent = os.path.dirname(path)
    if org_id and not os.path.isdir(parent):
        _missing_org_error(org_id)
    os.makedirs(parent, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def load_wallets(org_id=None):
    """Load wallet registry from the institution capsule."""
    return _load_registry_file('wallets.json', org_id)


def load_treasury_accounts(org_id=None):
    """Load treasury accounts from the institution capsule."""
    return _load_registry_file('treasury_accounts.json', org_id)


def load_maintainers(org_id=None):
    """Load maintainer registry from the institution capsule."""
    return _load_registry_file('maintainers.json', org_id)


def load_contributors(org_id=None):
    """Load contributor registry from the institution capsule."""
    return _load_registry_file('contributors.json', org_id)


def load_payout_proposals(org_id=None):
    """Load payout proposals from the institution capsule."""
    return _load_registry_file('payout_proposals.json', org_id)


def load_settlement_adapters(org_id=None):
    """Load settlement adapter policy from the institution capsule."""
    return _load_registry_file('settlement_adapters.json', org_id)


def load_funding_sources(org_id=None):
    """Load funding sources from the institution capsule."""
    return _sync_funding_sources(org_id)


def _save_funding_source_store(store, org_id=None):
    payload = dict(store or {})
    payload['updatedAt'] = _now()
    payload.setdefault('sources', {})
    payload.setdefault('source_types', _PROTOCOL_DEFAULTS['funding_sources.json']['source_types'])
    _save_registry_file('funding_sources.json', payload, org_id)


def _sync_funding_sources(org_id=None):
    store = dict(_load_registry_file('funding_sources.json', org_id))
    original_sources = dict(store.get('sources', {}))
    sources = dict(original_sources)
    source_types = dict(
        store.get('source_types') or _PROTOCOL_DEFAULTS['funding_sources.json']['source_types']
    )
    store['source_types'] = source_types

    treasury = load_ledger(org_id).get('treasury', {})
    owner_capital_total = round(
        float(treasury.get('owner_capital_contributed_usd', 0.0) or 0.0),
        4,
    )
    explicit_owner_capital = round(sum(
        float(item.get('amount_usd') or 0.0)
        for item in sources.values()
        if item.get('type') == 'owner_capital'
        and not dict(item.get('metadata') or {}).get('derived_from_ledger')
    ), 4)
    derived_owner_capital = round(max(0.0, owner_capital_total - explicit_owner_capital), 4)
    derived_id = 'src_derived_owner_capital'
    if derived_owner_capital > 0:
        existing = dict(sources.get(derived_id, {}))
        metadata = dict(existing.get('metadata') or {})
        metadata.update({
            'derived_from_ledger': True,
            'source_metric': 'owner_capital_contributed_usd',
        })
        sources[derived_id] = {
            'source_id': derived_id,
            'type': 'owner_capital',
            'amount_usd': derived_owner_capital,
            'currency': 'USD',
            'actor_id': 'system',
            'note': 'Backfilled from canonical ledger owner capital total.',
            'source_ref': 'ledger_total:owner_capital',
            'metadata': metadata,
            'recorded_at': existing.get('recorded_at') or _now(),
        }
    else:
        sources.pop(derived_id, None)

    store['sources'] = sources
    if store.get('source_types') != source_types or original_sources != sources:
        _save_funding_source_store(store, org_id)
    return store


def _proposal_store(org_id=None):
    store = dict(load_payout_proposals(org_id))
    store.setdefault('proposals', {})
    store.setdefault('state_machine', _PROTOCOL_DEFAULTS['payout_proposals.json']['state_machine'])
    store.setdefault('proposal_schema', _PROTOCOL_DEFAULTS['payout_proposals.json']['proposal_schema'])
    return store


def _save_proposal_store(store, org_id=None):
    store = dict(store or {})
    store['updatedAt'] = _now()
    store.setdefault('proposals', {})
    store.setdefault('state_machine', _PROTOCOL_DEFAULTS['payout_proposals.json']['state_machine'])
    store.setdefault('proposal_schema', _PROTOCOL_DEFAULTS['payout_proposals.json']['proposal_schema'])
    _save_registry_file('payout_proposals.json', store, org_id)


def _settlement_store(org_id=None):
    store = dict(load_settlement_adapters(org_id))
    store.setdefault(
        'default_payout_adapter',
        _PROTOCOL_DEFAULTS['settlement_adapters.json']['default_payout_adapter'],
    )
    adapters = {}
    raw_adapters = store.get('adapters', {})
    for adapter_id, raw in _PROTOCOL_DEFAULTS['settlement_adapters.json']['adapters'].items():
        merged = dict(raw)
        merged.update(dict(raw_adapters.get(adapter_id, {})))
        merged['adapter_id'] = adapter_id
        merged.setdefault('label', adapter_id)
        merged.setdefault('status', 'registered')
        merged.setdefault('payout_execution_enabled', False)
        merged.setdefault('supported_currencies', ['USDC'])
        merged.setdefault('requires_tx_hash', False)
        merged.setdefault('requires_settlement_proof', False)
        merged.setdefault('proof_type', 'external_reference')
        merged.setdefault('verification_state', 'unknown')
        merged.setdefault('finality_state', 'unknown')
        merged.setdefault('reversal_or_dispute_capability', 'court_case')
        merged.setdefault('execution_mode', 'external_reference')
        merged.setdefault('settlement_path', 'external_reference')
        merged.setdefault('dispute_model', merged.get('reversal_or_dispute_capability', 'court_case'))
        merged.setdefault('finality_model', merged.get('finality_state', 'unknown'))
        adapters[adapter_id] = merged
    for adapter_id, raw in raw_adapters.items():
        if adapter_id in adapters:
            continue
        merged = dict(raw or {})
        merged['adapter_id'] = adapter_id
        merged.setdefault('label', adapter_id)
        merged.setdefault('status', 'registered')
        merged.setdefault('payout_execution_enabled', False)
        merged.setdefault('supported_currencies', ['USDC'])
        merged.setdefault('requires_tx_hash', False)
        merged.setdefault('requires_settlement_proof', False)
        merged.setdefault('proof_type', 'external_reference')
        merged.setdefault('verification_state', 'unknown')
        merged.setdefault('finality_state', 'unknown')
        merged.setdefault('reversal_or_dispute_capability', 'court_case')
        merged.setdefault('execution_mode', 'external_reference')
        merged.setdefault('settlement_path', 'external_reference')
        merged.setdefault('dispute_model', merged.get('reversal_or_dispute_capability', 'court_case'))
        merged.setdefault('finality_model', merged.get('finality_state', 'unknown'))
        adapters[adapter_id] = merged
    store['adapters'] = adapters
    return store


def get_settlement_adapter(adapter_id, org_id=None):
    adapter_id = (adapter_id or '').strip()
    if not adapter_id:
        adapter_id = _settlement_store(org_id).get('default_payout_adapter', 'internal_ledger')
    return _settlement_store(org_id).get('adapters', {}).get(adapter_id)


def list_settlement_adapters(org_id=None, *, payout_enabled_only=False):
    rows = list(_settlement_store(org_id).get('adapters', {}).values())
    if payout_enabled_only:
        rows = [row for row in rows if row.get('payout_execution_enabled')]
    rows.sort(key=lambda row: row.get('adapter_id', ''))
    return rows


def settlement_adapter_summary(org_id=None, *, host_supported_adapters=None):
    store = _settlement_store(org_id)
    rows = list(store.get('adapters', {}).values())
    host_supported = [item for item in (host_supported_adapters or []) if item]
    payout_enabled = [row for row in rows if row.get('payout_execution_enabled')]
    return {
        'default_payout_adapter': store.get('default_payout_adapter', 'internal_ledger'),
        'total': len(rows),
        'active': len([row for row in rows if row.get('status') == 'active']),
        'payout_enabled': len(payout_enabled),
        'host_supported_adapters': host_supported,
        'host_supported_payout_adapters': [
            row.get('adapter_id', '')
            for row in payout_enabled
            if row.get('adapter_id', '') in host_supported
        ],
    }


def _settlement_adapter_contract(adapter, *, host_supported_adapters=None):
    adapter = dict(adapter or {})
    adapter_id = (adapter.get('adapter_id') or '').strip()
    host_supported = [item for item in (host_supported_adapters or []) if item]
    host_supported_set = set(host_supported)
    host_supported_known = host_supported_adapters is not None
    host_supported_effective = adapter_id in host_supported_set
    # The reference host always has a local ledger path even when the host
    # identity does not explicitly enumerate settlement adapters.
    if host_supported_known and not host_supported_effective and adapter_id == 'internal_ledger':
        host_supported_effective = True
    blockers = []
    if not adapter.get('payout_execution_enabled'):
        blockers.append('payout_execution_disabled')
    if host_supported_known and adapter_id and not host_supported_effective:
        blockers.append('host_not_supported')
    contract = {
        'adapter_id': adapter_id,
        'label': adapter.get('label', adapter_id),
        'status': adapter.get('status', 'registered'),
        'payout_execution_enabled': bool(adapter.get('payout_execution_enabled')),
        'execution_mode': adapter.get('execution_mode', 'external_reference'),
        'settlement_path': adapter.get('settlement_path', 'external_reference'),
        'supported_currencies': list(adapter.get('supported_currencies', [])),
        'requires_tx_hash': bool(adapter.get('requires_tx_hash')),
        'requires_settlement_proof': bool(adapter.get('requires_settlement_proof')),
        'proof_type': adapter.get('proof_type', 'external_reference'),
        'verification_state': adapter.get('verification_state', 'unknown'),
        'finality_state': adapter.get('finality_state', 'unknown'),
        'finality_model': adapter.get('finality_model', adapter.get('finality_state', 'unknown')),
        'reversal_or_dispute_capability': adapter.get(
            'reversal_or_dispute_capability',
            'court_case',
        ),
        'dispute_model': adapter.get(
            'dispute_model',
            adapter.get('reversal_or_dispute_capability', 'court_case'),
        ),
        'host_supported': None if not host_supported_known else host_supported_effective,
        'host_supported_adapters': host_supported,
        'execution_readiness': 'ready' if not blockers else 'blocked',
        'execution_blockers': list(blockers),
        'execution_ready': not blockers,
    }
    return contract


def _append_transaction(org_id, entry):
    tx_path = capsule_path(org_id, 'transactions.jsonl')
    if org_id and not os.path.isdir(os.path.dirname(tx_path)):
        _missing_org_error(org_id)
    os.makedirs(os.path.dirname(tx_path), exist_ok=True)
    row = dict(entry or {})
    row.setdefault('ts', _now())
    with open(tx_path, 'a') as f:
        f.write(json.dumps(row, sort_keys=True) + '\n')
    return row


def _payout_contribution_types(org_id=None):
    registry = load_contributors(org_id)
    return registry.get('contribution_types') or _PROTOCOL_DEFAULTS['contributors.json']['contribution_types']


def get_contributor(contributor_id, org_id=None):
    contributor_id = (contributor_id or '').strip()
    if not contributor_id:
        return None
    return load_contributors(org_id).get('contributors', {}).get(contributor_id)


def get_payout_proposal(proposal_id, org_id=None):
    proposal_id = (proposal_id or '').strip()
    if not proposal_id:
        return None
    return _proposal_store(org_id).get('proposals', {}).get(proposal_id)


def list_payout_proposals(org_id=None, *, status=None):
    proposals = list(_proposal_store(org_id).get('proposals', {}).values())
    if status:
        proposals = [row for row in proposals if row.get('status') == status]
    proposals.sort(
        key=lambda row: (
            row.get('updated_at', ''),
            row.get('created_at', ''),
            row.get('proposal_id', ''),
        ),
        reverse=True,
    )
    return proposals


def payout_proposal_summary(org_id=None):
    rows = list_payout_proposals(org_id)
    summary = {
        'total': len(rows),
        'draft': 0,
        'submitted': 0,
        'under_review': 0,
        'approved': 0,
        'dispute_window': 0,
        'executed': 0,
        'rejected': 0,
        'cancelled': 0,
        'requested_usd': 0.0,
        'executed_usd': 0.0,
    }
    for row in rows:
        status = row.get('status', '')
        if status in summary:
            summary[status] += 1
        amount = float(row.get('amount_usd') or 0.0)
        summary['requested_usd'] += amount
        if status == 'executed':
            summary['executed_usd'] += amount
    summary['requested_usd'] = round(summary['requested_usd'], 4)
    summary['executed_usd'] = round(summary['executed_usd'], 4)
    return summary


def _normalize_payout_evidence(evidence):
    payload = dict(evidence or {})
    payload['pr_urls'] = [str(item).strip() for item in payload.get('pr_urls', []) if str(item).strip()]
    payload['commit_hashes'] = [str(item).strip() for item in payload.get('commit_hashes', []) if str(item).strip()]
    payload['issue_refs'] = [str(item).strip() for item in payload.get('issue_refs', []) if str(item).strip()]
    payload['description'] = str(payload.get('description', '') or '').strip()
    if not (
        payload['pr_urls']
        or payload['commit_hashes']
        or payload['issue_refs']
        or payload['description']
    ):
        raise ValueError('evidence must include at least one PR URL, commit hash, issue ref, or description')
    return payload


def _normalize_settlement_proof(adapter, *, tx_hash='', settlement_proof=None):
    payload = settlement_proof
    if payload is None:
        payload = {}
    elif isinstance(payload, str):
        payload = {'reference': payload.strip()}
    else:
        payload = dict(payload)

    normalized = {
        'proof_type': adapter.get('proof_type', 'external_reference'),
        'verification_state': adapter.get('verification_state', 'unknown'),
        'finality_state': adapter.get('finality_state', 'unknown'),
        'reversal_or_dispute_capability': adapter.get(
            'reversal_or_dispute_capability',
            'court_case',
        ),
        'execution_mode': adapter.get('execution_mode', 'external_reference'),
        'settlement_path': adapter.get('settlement_path', 'external_reference'),
        'dispute_model': adapter.get(
            'dispute_model',
            adapter.get('reversal_or_dispute_capability', 'court_case'),
        ),
        'finality_model': adapter.get('finality_model', adapter.get('finality_state', 'unknown')),
    }
    tx_hash = (tx_hash or '').strip()
    if tx_hash:
        normalized['tx_hash'] = tx_hash
    if adapter.get('adapter_id') == 'internal_ledger':
        normalized['reference'] = ''
        normalized['proof'] = {'mode': 'institution_transactions_journal'}
        return normalized

    cleaned = {}
    for key, value in payload.items():
        if isinstance(value, str):
            value = value.strip()
        if value in ('', None, [], {}):
            continue
        cleaned[key] = value
    if cleaned:
        normalized['proof'] = cleaned
        if 'reference' in cleaned:
            normalized['reference'] = cleaned['reference']
    return normalized


def _require_known_settlement_adapter(adapter_id, *, org_id=None):
    adapter = get_settlement_adapter(adapter_id, org_id)
    if not adapter:
        raise ValueError(f'Unknown settlement_adapter {adapter_id!r}')
    return adapter


def _validate_payout_execution_adapter(adapter_id, *, org_id=None, currency='USDC',
                                       tx_hash='', settlement_proof=None,
                                       host_supported_adapters=None):
    adapter = _require_known_settlement_adapter(adapter_id, org_id=org_id)
    contract = _settlement_adapter_contract(
        adapter,
        host_supported_adapters=host_supported_adapters,
    )
    supported_currencies = {str(item).upper() for item in adapter.get('supported_currencies', [])}
    currency = str(currency or '').upper()
    if supported_currencies and currency not in supported_currencies:
        raise PermissionError(
            f"Settlement adapter '{adapter_id}' does not support currency {currency!r}"
        )
    if contract['payout_execution_enabled'] is False:
        raise PermissionError(
            f"Settlement adapter '{adapter_id}' is registered but not enabled for payout execution"
        )
    if contract['host_supported'] is False:
        raise PermissionError(
            f"Settlement adapter '{adapter_id}' is not supported on this host"
        )
    if adapter.get('requires_tx_hash') and not (tx_hash or '').strip():
        raise ValueError(f"Settlement adapter '{adapter_id}' requires tx_hash")
    normalized = _normalize_settlement_proof(
        adapter,
        tx_hash=tx_hash,
        settlement_proof=settlement_proof,
    )
    if adapter.get('requires_settlement_proof') and not normalized.get('proof'):
        raise ValueError(f"Settlement adapter '{adapter_id}' requires settlement_proof")
    return adapter, normalized, contract


def preflight_settlement_adapter(adapter_id='', *, org_id=None, currency='USDC',
                                 tx_hash='', settlement_proof=None,
                                 host_supported_adapters=None):
    store = _settlement_store(org_id)
    requested_adapter_id = (
        (adapter_id or '').strip()
        or store.get('default_payout_adapter', 'internal_ledger')
    )
    result = {
        'default_payout_adapter': store.get('default_payout_adapter', 'internal_ledger'),
        'requested_adapter_id': requested_adapter_id,
        'currency': (currency or 'USDC').strip().upper(),
        'host_supported_adapters': list(host_supported_adapters or []),
        'known': False,
        'preflight_ok': False,
        'can_execute_now': False,
        'error_type': '',
        'error': '',
        'execution_blockers': [],
        'execution_blocker_messages': [],
    }
    adapter = get_settlement_adapter(requested_adapter_id, org_id)
    if not adapter:
        result['error_type'] = 'unknown_adapter'
        result['error'] = f'Unknown settlement_adapter {requested_adapter_id!r}'
        return result

    contract = _settlement_adapter_contract(
        adapter,
        host_supported_adapters=host_supported_adapters,
    )
    normalized = _normalize_settlement_proof(adapter, tx_hash=tx_hash, settlement_proof=settlement_proof)
    result.update({
        'known': True,
        'adapter': adapter,
        'execution_enabled': contract['payout_execution_enabled'],
        'host_supported': contract['host_supported'],
        'requirements': {
            'supported_currencies': list(adapter.get('supported_currencies', [])),
            'requires_tx_hash': bool(adapter.get('requires_tx_hash')),
            'requires_settlement_proof': bool(adapter.get('requires_settlement_proof')),
            'proof_type': adapter.get('proof_type', 'external_reference'),
            'verification_state': adapter.get('verification_state', 'unknown'),
            'finality_state': adapter.get('finality_state', 'unknown'),
            'reversal_or_dispute_capability': adapter.get(
                'reversal_or_dispute_capability',
                'court_case',
            ),
            'execution_mode': adapter.get('execution_mode', 'external_reference'),
            'settlement_path': adapter.get('settlement_path', 'external_reference'),
            'finality_model': adapter.get('finality_model', adapter.get('finality_state', 'unknown')),
            'dispute_model': adapter.get(
                'dispute_model',
                adapter.get('reversal_or_dispute_capability', 'court_case'),
            ),
        },
        'contract': contract,
        'normalized_proof': normalized,
        'execution_blockers': list(contract['execution_blockers']),
        'execution_ready': contract['execution_ready'],
    })
    try:
        _validated_adapter, normalized, contract = _validate_payout_execution_adapter(
            requested_adapter_id,
            org_id=org_id,
            currency=result['currency'],
            tx_hash=tx_hash,
            settlement_proof=settlement_proof,
            host_supported_adapters=host_supported_adapters,
        )
        result['preflight_ok'] = True
        result['can_execute_now'] = True
        result['normalized_proof'] = normalized
        result['contract'] = contract
        result['execution_blockers'] = []
        result['execution_ready'] = True
    except PermissionError as exc:
        result['error_type'] = 'permission_error'
        result['error'] = str(exc)
        result['execution_blockers'] = list(contract['execution_blockers'])
        result['execution_blocker_messages'] = [str(exc)]
    except ValueError as exc:
        result['error_type'] = 'validation_error'
        result['error'] = str(exc)
        result['execution_blockers'] = list(contract['execution_blockers'])
        result['execution_blocker_messages'] = [str(exc)]
    return result


def _resolve_recipient_wallet(contributor_id, recipient_wallet_id='', org_id=None):
    contributor = get_contributor(contributor_id, org_id)
    if not contributor:
        raise LookupError(f'Contributor not found: {contributor_id}')
    wallet_id = (
        (recipient_wallet_id or '').strip()
        or (contributor.get('payout_wallet_id') or '').strip()
    )
    if not wallet_id:
        raise ValueError(
            'recipient_wallet_id is required unless the contributor record defines payout_wallet_id'
        )
    eligible, reason = can_receive_payout(wallet_id, org_id)
    if not eligible:
        raise PermissionError(reason)
    return contributor, wallet_id


def _require_transition(record, target_state, *, org_id=None):
    current_state = (record.get('status') or '').strip()
    transitions = _proposal_store(org_id).get('state_machine', {}).get('transitions', {})
    allowed = list(transitions.get(current_state, []))
    if target_state not in allowed:
        raise ValueError(
            f"Proposal '{record.get('proposal_id', '')}' cannot transition from "
            f"{current_state!r} to {target_state!r}"
        )


def _payout_phase_gate(org_id=None):
    if _current_phase is None:
        return True, 'Phase machine unavailable; payout gate deferred to treasury reserve checks'
    phase_num, phase_info = _current_phase(org_id)
    if phase_num < 5:
        return False, (
            f"Phase {phase_num} ({phase_info.get('name', '')}) does not allow contributor payouts yet"
        )
    return True, f"Phase {phase_num} ({phase_info.get('name', '')}) permits contributor payouts"


def create_payout_proposal(contributor_id, amount_usd, contribution_type, *,
                           proposed_by, org_id=None, evidence=None,
                           recipient_wallet_id='', currency='USDC',
                           settlement_adapter='internal_ledger', note='',
                           metadata=None, linked_commitment_id=''):
    contributor_id = (contributor_id or '').strip()
    proposed_by = (proposed_by or '').strip()
    contribution_type = (contribution_type or '').strip()
    currency = (currency or 'USDC').strip().upper()
    settlement_adapter = (settlement_adapter or 'internal_ledger').strip()
    linked_commitment_id = (linked_commitment_id or '').strip()
    if not contributor_id:
        raise ValueError('contributor_id is required')
    if not proposed_by:
        raise ValueError('proposed_by is required')
    amount = round(float(amount_usd), 4)
    if amount <= 0:
        raise ValueError('amount_usd must be greater than 0')
    if contribution_type not in _payout_contribution_types(org_id):
        raise ValueError(f'Unknown contribution_type {contribution_type!r}')
    _require_known_settlement_adapter(settlement_adapter, org_id=org_id)
    if linked_commitment_id and not commitments.get_commitment(linked_commitment_id, org_id=org_id):
        raise LookupError(f'Commitment not found: {linked_commitment_id}')
    normalized_evidence = _normalize_payout_evidence(evidence)
    contributor, wallet_id = _resolve_recipient_wallet(
        contributor_id,
        recipient_wallet_id=recipient_wallet_id,
        org_id=org_id,
    )
    timestamp = _now()
    proposal_id = f'ppo_{uuid.uuid4().hex[:12]}'
    record = {
        'proposal_id': proposal_id,
        'id': proposal_id,
        'institution_id': org_id or _default_org_id(),
        'contributor_id': contributor_id,
        'contributor_name': contributor.get('name', ''),
        'amount_usd': amount,
        'currency': currency,
        'contribution_type': contribution_type,
        'evidence': normalized_evidence,
        'recipient_wallet_id': wallet_id,
        'proposed_by': proposed_by,
        'reviewed_by': '',
        'approved_by': '',
        'status': 'draft',
        'created_at': timestamp,
        'updated_at': timestamp,
        'submitted_at': '',
        'reviewed_at': '',
        'approved_at': '',
        'dispute_window_started_at': '',
        'dispute_window_ends_at': '',
        'executed_at': '',
        'executed_by': '',
        'tx_hash': '',
        'warrant_id': '',
        'settlement_adapter': settlement_adapter,
        'linked_commitment_id': linked_commitment_id,
        'execution_refs': {},
        'note': note or '',
        'metadata': dict(metadata or {}),
    }
    store = _proposal_store(org_id)
    store['proposals'][proposal_id] = record
    _save_proposal_store(store, org_id)
    return record


def submit_payout_proposal(proposal_id, actor_id, *, org_id=None, note='', owner_override=False):
    actor_id = (actor_id or '').strip()
    store = _proposal_store(org_id)
    record = store['proposals'].get((proposal_id or '').strip())
    if not record:
        raise LookupError(f'Payout proposal not found: {proposal_id}')
    _require_transition(record, 'submitted', org_id=org_id)
    if not owner_override and actor_id and actor_id != record.get('proposed_by'):
        raise PermissionError('Only the proposer or owner may submit this payout proposal')
    timestamp = _now()
    record['status'] = 'submitted'
    record['submitted_at'] = timestamp
    record['updated_at'] = timestamp
    if note:
        record['note'] = note
    _save_proposal_store(store, org_id)
    return record


def review_payout_proposal(proposal_id, reviewer_id, *, org_id=None, note=''):
    reviewer_id = (reviewer_id or '').strip()
    if not reviewer_id:
        raise ValueError('reviewer_id is required')
    store = _proposal_store(org_id)
    record = store['proposals'].get((proposal_id or '').strip())
    if not record:
        raise LookupError(f'Payout proposal not found: {proposal_id}')
    _require_transition(record, 'under_review', org_id=org_id)
    if reviewer_id in {
        record.get('contributor_id', ''),
        record.get('proposed_by', ''),
    }:
        raise PermissionError('Reviewer must not be the contributor or proposer')
    timestamp = _now()
    record['status'] = 'under_review'
    record['reviewed_by'] = reviewer_id
    record['reviewed_at'] = timestamp
    record['updated_at'] = timestamp
    if note:
        record['review_note'] = note
    _save_proposal_store(store, org_id)
    return record


def approve_payout_proposal(proposal_id, approver_id, *, org_id=None, note=''):
    approver_id = (approver_id or '').strip()
    if not approver_id:
        raise ValueError('approver_id is required')
    store = _proposal_store(org_id)
    record = store['proposals'].get((proposal_id or '').strip())
    if not record:
        raise LookupError(f'Payout proposal not found: {proposal_id}')
    _require_transition(record, 'approved', org_id=org_id)
    timestamp = _now()
    record['status'] = 'approved'
    record['approved_by'] = approver_id
    record['approved_at'] = timestamp
    record['updated_at'] = timestamp
    if note:
        record['approval_note'] = note
    _save_proposal_store(store, org_id)
    return record


def open_payout_dispute_window(proposal_id, actor_id, *, org_id=None, note='', dispute_window_hours=None):
    actor_id = (actor_id or '').strip()
    if not actor_id:
        raise ValueError('actor_id is required')
    store = _proposal_store(org_id)
    record = store['proposals'].get((proposal_id or '').strip())
    if not record:
        raise LookupError(f'Payout proposal not found: {proposal_id}')
    _require_transition(record, 'dispute_window', org_id=org_id)
    state_machine = store.get('state_machine', {})
    hours = state_machine.get('dispute_window_hours', 72) if dispute_window_hours is None else float(dispute_window_hours)
    if hours < 0:
        raise ValueError('dispute_window_hours must be >= 0')
    started_at = _parse_ts(_now())
    ends_at = started_at + datetime.timedelta(hours=hours)
    record['status'] = 'dispute_window'
    record['updated_at'] = started_at.strftime('%Y-%m-%dT%H:%M:%SZ')
    record['dispute_window_started_at'] = started_at.strftime('%Y-%m-%dT%H:%M:%SZ')
    record['dispute_window_ends_at'] = ends_at.strftime('%Y-%m-%dT%H:%M:%SZ')
    if note:
        record['approval_note'] = note
    _save_proposal_store(store, org_id)
    return record


def reject_payout_proposal(proposal_id, actor_id, *, org_id=None, note=''):
    actor_id = (actor_id or '').strip()
    if not actor_id:
        raise ValueError('actor_id is required')
    store = _proposal_store(org_id)
    record = store['proposals'].get((proposal_id or '').strip())
    if not record:
        raise LookupError(f'Payout proposal not found: {proposal_id}')
    current = record.get('status', '')
    allowed = current in ('submitted', 'under_review', 'dispute_window')
    if not allowed:
        raise ValueError(f"Proposal '{proposal_id}' cannot be rejected from status {current!r}")
    timestamp = _now()
    record['status'] = 'rejected'
    record['updated_at'] = timestamp
    record['reviewed_by'] = actor_id
    record['reviewed_at'] = timestamp
    if note:
        record['review_note'] = note
    _save_proposal_store(store, org_id)
    return record


def cancel_payout_proposal(proposal_id, actor_id, *, org_id=None, note='', owner_override=False):
    actor_id = (actor_id or '').strip()
    if not actor_id:
        raise ValueError('actor_id is required')
    store = _proposal_store(org_id)
    record = store['proposals'].get((proposal_id or '').strip())
    if not record:
        raise LookupError(f'Payout proposal not found: {proposal_id}')
    current = record.get('status', '')
    allowed = current in ('draft', 'submitted')
    if not allowed:
        raise ValueError(f"Proposal '{proposal_id}' cannot be cancelled from status {current!r}")
    if not owner_override and actor_id != record.get('proposed_by'):
        raise PermissionError('Only the proposer or owner may cancel this payout proposal')
    record['status'] = 'cancelled'
    record['updated_at'] = _now()
    if note:
        record['note'] = note
    _save_proposal_store(store, org_id)
    return record


def execute_payout_proposal(proposal_id, actor_id, *, org_id=None, warrant_id='',
                            settlement_adapter='', tx_hash='', note='',
                            allow_early=False, settlement_proof=None,
                            host_supported_adapters=None):
    actor_id = (actor_id or '').strip()
    if not actor_id:
        raise ValueError('actor_id is required')
    store = _proposal_store(org_id)
    record = store['proposals'].get((proposal_id or '').strip())
    if not record:
        raise LookupError(f'Payout proposal not found: {proposal_id}')
    _require_transition(record, 'executed', org_id=org_id)
    allowed, reason = _payout_phase_gate(org_id)
    if not allowed:
        raise PermissionError(reason)
    ends_at = record.get('dispute_window_ends_at', '')
    if not allow_early and ends_at:
        if _parse_ts(ends_at) > _parse_ts(_now()):
            raise PermissionError(
                f"Payout proposal '{proposal_id}' is still inside dispute window until {ends_at}"
            )
    eligible, reason = can_receive_payout(record.get('recipient_wallet_id', ''), org_id)
    if not eligible:
        raise PermissionError(reason)
    if not can_payout(float(record.get('amount_usd') or 0.0), org_id=org_id):
        raise PermissionError(
            f"Payout proposal '{proposal_id}' would breach treasury reserve floor"
        )
    linked_commitment_id = (record.get('linked_commitment_id') or '').strip()
    if linked_commitment_id:
        commitments.validate_commitment_for_settlement(
            linked_commitment_id,
            org_id=org_id,
        )

    settlement_adapter = (settlement_adapter or record.get('settlement_adapter') or 'internal_ledger').strip()
    adapter, normalized_proof, contract = _validate_payout_execution_adapter(
        settlement_adapter,
        org_id=org_id,
        currency=record.get('currency', 'USDC'),
        tx_hash=tx_hash,
        settlement_proof=settlement_proof,
        host_supported_adapters=host_supported_adapters,
    )
    ledger = load_ledger(org_id)
    treasury = ledger.setdefault('treasury', {})
    amount = round(float(record.get('amount_usd') or 0.0), 4)
    treasury['cash_usd'] = round(float(treasury.get('cash_usd', 0.0)) - amount, 4)
    treasury['expenses_recorded_usd'] = round(
        float(treasury.get('expenses_recorded_usd', 0.0)) + amount,
        4,
    )
    ledger['updatedAt'] = _now()
    ledger_path = capsule_path(org_id, 'ledger.json')
    if org_id and not os.path.isdir(os.path.dirname(ledger_path)):
        _missing_org_error(org_id)
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
    with open(ledger_path, 'w') as f:
        json.dump(ledger, f, indent=2)

    tx_ref = f'ptx_{uuid.uuid4().hex[:12]}'
    tx_row = _append_transaction(org_id, {
        'tx_ref': tx_ref,
        'type': 'payout_execution',
        'proposal_id': proposal_id,
        'contributor_id': record.get('contributor_id', ''),
        'recipient_wallet_id': record.get('recipient_wallet_id', ''),
        'amount_usd': amount,
        'currency': record.get('currency', 'USDC'),
        'settlement_adapter': settlement_adapter,
        'tx_hash': normalized_proof.get('tx_hash', ''),
        'verification_state': normalized_proof.get('verification_state', ''),
        'finality_state': normalized_proof.get('finality_state', ''),
        'warrant_id': (warrant_id or '').strip(),
        'cash_after': treasury['cash_usd'],
        'by': actor_id,
        'note': note or '',
        'settlement_proof': normalized_proof.get('proof', {}),
        'settlement_adapter_contract': contract,
    })
    timestamp = _now()
    record['status'] = 'executed'
    record['updated_at'] = timestamp
    record['executed_at'] = timestamp
    record['executed_by'] = actor_id
    record['warrant_id'] = (warrant_id or '').strip()
    record['settlement_adapter'] = settlement_adapter
    record['settlement_adapter_contract'] = contract
    record['tx_hash'] = normalized_proof.get('tx_hash', '')
    record['execution_refs'] = {
        'tx_ref': tx_row['tx_ref'],
        'settlement_adapter': settlement_adapter,
        'settlement_adapter_contract': contract,
        'tx_hash': normalized_proof.get('tx_hash', ''),
        'proof_type': adapter.get('proof_type', ''),
        'verification_state': normalized_proof.get('verification_state', ''),
        'finality_state': normalized_proof.get('finality_state', ''),
        'reversal_or_dispute_capability': normalized_proof.get(
            'reversal_or_dispute_capability',
            '',
        ),
        'proof': normalized_proof.get('proof', {}),
        'linked_commitment_id': linked_commitment_id,
    }
    if note:
        record['execution_note'] = note
    linked_commitment = None
    if linked_commitment_id:
        linked_commitment = commitments.record_settlement_ref(
            linked_commitment_id,
            {
                'proposal_id': proposal_id,
                'tx_ref': tx_row['tx_ref'],
                'settlement_adapter': settlement_adapter,
                'tx_hash': normalized_proof.get('tx_hash', ''),
                'proof_type': adapter.get('proof_type', ''),
                'verification_state': normalized_proof.get('verification_state', ''),
                'finality_state': normalized_proof.get('finality_state', ''),
                'warrant_id': (warrant_id or '').strip(),
                'recorded_by': actor_id,
                'proof': normalized_proof.get('proof', {}),
            },
            org_id=org_id,
        )
    _save_proposal_store(store, org_id)
    if linked_commitment is not None:
        record['linked_commitment'] = linked_commitment
    return record


def get_wallet(wallet_id, org_id=None):
    """Get a single wallet by ID. Returns None if not found."""
    wallets = load_wallets(org_id)
    return wallets.get('wallets', {}).get(wallet_id)


def get_payout_eligible_wallets(org_id=None):
    """Return dict of wallets with verification Level 3+."""
    wallets = load_wallets(org_id)
    return {wid: w for wid, w in wallets.get('wallets', {}).items()
            if (w.get('verification_level') or 0) >= 3 and w.get('payout_eligible')}


def can_receive_payout(wallet_id, org_id=None):
    """Check if a wallet can receive payouts. Returns (bool, reason)."""
    wallet = get_wallet(wallet_id, org_id)
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


def treasury_snapshot(org_id=None):
    """Combined view: balance, revenue, spend, runway, reserve status."""
    ledger = load_ledger(org_id)
    t = ledger['treasury']
    rev_summary = get_revenue_summary(org_id)

    scoped_org_id = org_id or _default_org_id()
    spend_usd = 0.0
    if scoped_org_id:
        try:
            spend_usd = get_spend_summary(scoped_org_id, 30)['total_spend_usd']
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
        'wallet_count': len(load_wallets(org_id).get('wallets', {})),
        'payout_eligible_wallets': len(get_payout_eligible_wallets(org_id)),
        'maintainer_count': len(load_maintainers(org_id).get('maintainers', {})),
        'contributor_count': len(load_contributors(org_id).get('contributors', {})),
        'pending_proposals': len([p for p in load_payout_proposals(org_id).get('proposals', {}).values()
                                  if p.get('status') in ('submitted', 'under_review')]),
        'settlement_adapter_count': len(list_settlement_adapters(org_id)),
        'payout_enabled_settlement_adapters': len(
            list_settlement_adapters(org_id, payout_enabled_only=True)
        ),
        'funding_sources': len(load_funding_sources(org_id).get('sources', {})),
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
        'settlement_adapter_summary': settlement_adapter_summary(org_id),
        'settlement_adapters': list_settlement_adapters(org_id),
        'remediation': remediation,
        'snapshot_at': _now(),
    }


# -- CLI ----------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description='Treasury primitive -- governance facade')
    sub = p.add_subparsers(dest='command')

    bal = sub.add_parser('balance')
    bal.add_argument('--org_id', default=None)
    run = sub.add_parser('runway')
    run.add_argument('--org_id', default=None)

    sp = sub.add_parser('spend')
    sp.add_argument('--org_id', default=None)
    sp.add_argument('--days', type=int, default=30)

    sn = sub.add_parser('snapshot')
    sn.add_argument('--org_id', default=None)

    cb = sub.add_parser('check-budget')
    cb.add_argument('--org_id', default=None)
    cb.add_argument('--agent_id', required=True)
    cb.add_argument('--cost', type=float, required=True)

    cc = sub.add_parser('contribute')
    cc.add_argument('--org_id', default=None)
    cc.add_argument('--amount', type=float, required=True)
    cc.add_argument('--note', default='owner top-up')
    cc.add_argument('--by', default='owner')

    rf = sub.add_parser('set-reserve-floor')
    rf.add_argument('--org_id', default=None)
    rf.add_argument('--amount', type=float, required=True)
    rf.add_argument('--note', default='reserve policy update')
    rf.add_argument('--by', default='owner')

    for name in ('wallets', 'accounts', 'maintainers', 'contributors', 'proposals', 'funding-sources'):
        parser = sub.add_parser(name)
        parser.add_argument('--org_id', default=None)

    cpw = sub.add_parser('check-payout-wallet')
    cpw.add_argument('--org_id', default=None)
    cpw.add_argument('--wallet_id', required=True)

    args = p.parse_args()

    if args.command == 'balance':
        print(f'Treasury balance: ${get_balance(args.org_id):.2f}')
    elif args.command == 'runway':
        runway = get_runway(args.org_id)
        floor = get_reserve_floor(args.org_id)
        status = 'ABOVE reserve' if runway >= 0 else 'BELOW reserve'
        print(f'Runway: ${runway:.2f} ({status}, floor=${floor:.2f})')
    elif args.command == 'spend':
        org_id = args.org_id
        if not org_id:
            org_id = _default_org_id()
        if org_id:
            s = get_spend_summary(org_id, args.days)
            print(f'Spend ({s["period_days"]}d): ${s["total_spend_usd"]:.4f}')
        else:
            print('No org found for spend query')
    elif args.command == 'snapshot':
        snap = treasury_snapshot(args.org_id)
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
        allowed, reason = check_budget(args.agent_id, args.cost, org_id=args.org_id)
        status = 'ALLOWED' if allowed else 'BLOCKED'
        print(f'{status}: {reason}')
        sys.exit(0 if allowed else 1)
    elif args.command == 'contribute':
        result = contribute_owner_capital(args.amount, args.note, args.by, org_id=args.org_id)
        print(f"Capital contribution recorded: +${result['amount_usd']:.2f} | cash now ${result['cash_after_usd']:.2f}")
    elif args.command == 'set-reserve-floor':
        result = set_reserve_floor_policy(args.amount, args.note, args.by, org_id=args.org_id)
        print(f"Reserve floor updated: ${result['old_reserve_floor_usd']:.2f} -> ${result['new_reserve_floor_usd']:.2f}")
    elif args.command == 'wallets':
        data = load_wallets(args.org_id)
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
        data = load_treasury_accounts(args.org_id)
        accounts = data.get('accounts', {})
        if not accounts:
            print('No treasury accounts defined.')
        else:
            print(f'\n=== Treasury Accounts ({len(accounts)}) ===')
            for aid, a in accounts.items():
                print(f"  {aid}: ${a.get('balance_usd', 0):.2f} (reserve ${a.get('reserve_floor_usd', 0):.2f}) | {a.get('status')}")
    elif args.command == 'maintainers':
        data = load_maintainers(args.org_id)
        maintainers = data.get('maintainers', {})
        if not maintainers:
            print('No maintainers registered.')
        else:
            print(f'\n=== Maintainers ({len(maintainers)}) ===')
            for mid, m in maintainers.items():
                wallet = m.get('payout_wallet_id') or 'none'
                print(f"  {m.get('name')} ({m.get('github')}) | role={m.get('role')} | wallet={wallet} | {m.get('status')}")
    elif args.command == 'contributors':
        data = load_contributors(args.org_id)
        contributors = data.get('contributors', {})
        if not contributors:
            print('No contributors registered.')
        else:
            print(f'\n=== Contributors ({len(contributors)}) ===')
            for cid, c in contributors.items():
                print(f"  {c.get('name', cid)} ({c.get('github', '?')}) | {c.get('status', '?')}")
    elif args.command == 'proposals':
        data = load_payout_proposals(args.org_id)
        proposals = data.get('proposals', {})
        if not proposals:
            print('No payout proposals.')
        else:
            print(f'\n=== Payout Proposals ({len(proposals)}) ===')
            for pid, p_ in proposals.items():
                print(f"  {pid}: ${p_.get('amount_usd', 0):.2f} | {p_.get('status')} | {p_.get('contributor_id')}")
    elif args.command == 'funding-sources':
        data = load_funding_sources(args.org_id)
        sources = data.get('sources', {})
        if not sources:
            print('No funding sources recorded.')
        else:
            print(f'\n=== Funding Sources ({len(sources)}) ===')
            for sid, s in sources.items():
                print(f"  {sid}: ${s.get('amount_usd', 0):.2f} {s.get('currency', '')} | {s.get('type')} | {s.get('recorded_at')}")
    elif args.command == 'check-payout-wallet':
        eligible, reason = can_receive_payout(args.wallet_id, org_id=args.org_id)
        status = 'ELIGIBLE' if eligible else 'BLOCKED'
        print(f'{status}: {reason}')
        sys.exit(0 if eligible else 1)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
