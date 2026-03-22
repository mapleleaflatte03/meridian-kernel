#!/usr/bin/env python3
"""
Cross-institution commitment primitives for Meridian Kernel.

This is the first first-class commitment object. It does not yet claim the
entire inter-institution commitments program. It does establish:

- institution-scoped, capsule-backed commitment records
- explicit target host / target institution binding
- workspace APIs to propose and review commitments
- optional sender-side federation validation when `commitment_id` is supplied
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
import uuid


PLATFORM_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(PLATFORM_DIR)
ECONOMY_DIR = os.path.join(WORKSPACE, 'economy')

if PLATFORM_DIR not in sys.path:
    sys.path.insert(0, PLATFORM_DIR)

try:
    from capsule import capsule_path
except ImportError:
    def capsule_path(org_id, filename):
        return os.path.join(ECONOMY_DIR, filename)


COMMITMENT_STATES = (
    'proposed',
    'accepted',
    'rejected',
    'breached',
    'settled',
)


def _now():
    return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def _payload_hash(payload):
    if payload is None:
        return ''
    if isinstance(payload, bytes):
        raw = payload
    elif isinstance(payload, str):
        raw = payload.encode('utf-8')
    else:
        raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _missing_org_error(org_id):
    raise SystemExit(
        f"ERROR: institution '{org_id}' is not initialized. Run quickstart.py --init-only or bootstrap the capsule first."
    )


def _store_path(org_id=None):
    return capsule_path(org_id, 'commitments.json')


def _empty_store():
    return {
        'commitments': {},
        'updatedAt': _now(),
        'states': list(COMMITMENT_STATES),
    }


def _load_store(org_id=None):
    path = _store_path(org_id)
    parent = os.path.dirname(path)
    if org_id and not os.path.isdir(parent):
        _missing_org_error(org_id)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return _empty_store()


def _save_store(data, org_id=None):
    data['updatedAt'] = _now()
    path = _store_path(org_id)
    parent = os.path.dirname(path)
    if org_id and not os.path.isdir(parent):
        _missing_org_error(org_id)
    os.makedirs(parent, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, sort_keys=True)


def propose_commitment(org_id, target_host_id, target_org_id, commitment_type,
                       actor_id, *, terms_payload=None, warrant_id='',
                       note=''):
    target_host_id = (target_host_id or '').strip()
    target_org_id = (target_org_id or '').strip()
    commitment_type = (commitment_type or '').strip()
    actor_id = (actor_id or '').strip()
    if not target_host_id:
        raise ValueError('target_host_id is required')
    if not target_org_id:
        raise ValueError('target_org_id is required')
    if not commitment_type:
        raise ValueError('commitment_type is required')
    if not actor_id:
        raise ValueError('actor_id is required')

    commitment_id = f'cmt_{uuid.uuid4().hex[:12]}'
    record = {
        'commitment_id': commitment_id,
        'source_institution_id': org_id,
        'target_host_id': target_host_id,
        'target_institution_id': target_org_id,
        'commitment_type': commitment_type,
        'terms_hash': _payload_hash(terms_payload),
        'terms_payload': terms_payload if terms_payload is not None else {},
        'warrant_id': (warrant_id or '').strip(),
        'state': 'proposed',
        'proposed_by': actor_id,
        'proposed_at': _now(),
        'reviewed_by': '',
        'reviewed_at': '',
        'review_note': '',
        'delivery_refs': [],
        'last_delivery_at': '',
        'breached_at': '',
        'settled_at': '',
        'note': note or '',
    }
    store = _load_store(org_id)
    store.setdefault('commitments', {})[commitment_id] = record
    _save_store(store, org_id)
    return record


def list_commitments(org_id=None, *, state=None):
    store = _load_store(org_id)
    commitments = list(store.get('commitments', {}).values())
    if state:
        commitments = [row for row in commitments if row.get('state') == state]
    commitments.sort(key=lambda row: row.get('proposed_at', ''), reverse=True)
    return commitments


def get_commitment(commitment_id, org_id=None):
    if not commitment_id:
        return None
    store = _load_store(org_id)
    return store.get('commitments', {}).get(commitment_id)


def review_commitment(commitment_id, decision, by, *, org_id=None, note=''):
    decision = (decision or '').strip()
    state_map = {
        'accept': 'accepted',
        'reject': 'rejected',
        'breach': 'breached',
        'settle': 'settled',
    }
    if decision not in state_map:
        raise ValueError(f'Unsupported commitment decision: {decision}')
    store = _load_store(org_id)
    record = store.get('commitments', {}).get(commitment_id)
    if not record:
        raise ValueError(f'Commitment not found: {commitment_id}')
    state = state_map[decision]
    record['state'] = state
    record['reviewed_by'] = (by or '').strip()
    record['reviewed_at'] = _now()
    record['review_note'] = note or ''
    if state == 'breached':
        record['breached_at'] = record['reviewed_at']
    if state == 'settled':
        record['settled_at'] = record['reviewed_at']
    _save_store(store, org_id)
    return record


def validate_commitment_for_federation(commitment_id, *, org_id=None,
                                       target_host_id='', target_org_id='',
                                       warrant_id=''):
    record = get_commitment(commitment_id, org_id=org_id)
    if not record:
        raise PermissionError(f"Commitment '{commitment_id}' does not exist")
    if record.get('state') != 'accepted':
        raise PermissionError(
            f"Commitment '{commitment_id}' is not active for federation "
            f"(state={record.get('state', '')})"
        )
    if target_host_id and record.get('target_host_id') != target_host_id:
        raise PermissionError(
            f"Commitment '{commitment_id}' target_host_id "
            f"{record.get('target_host_id', '')!r} does not match {target_host_id!r}"
        )
    if target_org_id and record.get('target_institution_id') != target_org_id:
        raise PermissionError(
            f"Commitment '{commitment_id}' target_institution_id "
            f"{record.get('target_institution_id', '')!r} does not match {target_org_id!r}"
        )
    if warrant_id and record.get('warrant_id') and record.get('warrant_id') != warrant_id:
        raise PermissionError(
            f"Commitment '{commitment_id}' warrant_id "
            f"{record.get('warrant_id', '')!r} does not match {warrant_id!r}"
        )
    return record


def mark_commitment_delivery(commitment_id, *, org_id=None, delivery_ref=None):
    store = _load_store(org_id)
    record = store.get('commitments', {}).get(commitment_id)
    if not record:
        raise ValueError(f'Commitment not found: {commitment_id}')
    ref = dict(delivery_ref or {})
    refs = list(record.get('delivery_refs', []))
    refs.append(ref)
    record['delivery_refs'] = refs
    record['last_delivery_at'] = _now()
    _save_store(store, org_id)
    return record


def main():
    parser = argparse.ArgumentParser(description='Commitment management')
    sub = parser.add_subparsers(dest='command')

    propose = sub.add_parser('propose')
    propose.add_argument('--org_id', required=True)
    propose.add_argument('--target_host_id', required=True)
    propose.add_argument('--target_org_id', required=True)
    propose.add_argument('--commitment_type', required=True)
    propose.add_argument('--actor_id', required=True)
    propose.add_argument('--warrant_id', default='')

    show = sub.add_parser('show')
    show.add_argument('--org_id', required=True)

    review = sub.add_parser('review')
    review.add_argument('--org_id', required=True)
    review.add_argument('--commitment_id', required=True)
    review.add_argument('--decision', required=True)
    review.add_argument('--by', required=True)

    args = parser.parse_args()
    if args.command == 'propose':
        print(json.dumps(propose_commitment(
            args.org_id,
            args.target_host_id,
            args.target_org_id,
            args.commitment_type,
            args.actor_id,
            warrant_id=args.warrant_id,
        ), indent=2))
    elif args.command == 'show':
        print(json.dumps({'commitments': list_commitments(args.org_id)}, indent=2))
    elif args.command == 'review':
        print(json.dumps(review_commitment(
            args.commitment_id,
            args.decision,
            args.by,
            org_id=args.org_id,
        ), indent=2))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
