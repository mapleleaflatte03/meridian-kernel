#!/usr/bin/env python3
"""
Capsule-backed receiver-side execution jobs for federated Meridian work.

This is a narrow storage primitive only. It intentionally does not execute
work. It records incoming cross-host execution requests as institution-scoped
jobs that can be reviewed, blocked, rejected, or marked ready/executed.
"""
from __future__ import annotations

import collections
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import sys
import tempfile
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


JOB_STATES = (
    'pending_local_warrant',
    'ready',
    'executed',
    'blocked',
    'rejected',
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


def _store_path(org_id):
    if not (org_id or '').strip():
        raise ValueError('org_id is required')
    return capsule_path(org_id, 'federated_execution_jobs.json')


def _lock_path(org_id):
    if not (org_id or '').strip():
        raise ValueError('org_id is required')
    return capsule_path(org_id, '.federated_execution_jobs.lock')


def _empty_store(org_id):
    return {
        'version': 1,
        'updatedAt': _now(),
        'jobs': {},
        'states': list(JOB_STATES),
        '_meta': {
            'service_scope': 'institution_owned_service',
            'bound_org_id': (org_id or '').strip(),
        },
    }


def _normalize_state(state, *, existing_state=''):
    state = (state or '').strip().lower()
    existing_state = (existing_state or '').strip().lower()
    if state and state not in JOB_STATES:
        raise ValueError(f"Unknown execution job state {state!r}. Must be one of {JOB_STATES}")
    return state or existing_state or 'pending_local_warrant'


def _normalize_store(data, org_id):
    store = _empty_store(org_id)
    if not isinstance(data, dict):
        return store
    store.update({k: v for k, v in data.items() if k not in ('jobs', '_meta')})
    meta = dict(store.get('_meta', {}))
    meta.update(data.get('_meta', {}) or {})
    meta['bound_org_id'] = (org_id or '').strip()
    store['_meta'] = meta

    raw_jobs = data.get('jobs', {})
    jobs = {}
    if isinstance(raw_jobs, list):
        for item in raw_jobs:
            if isinstance(item, dict) and item.get('envelope_id'):
                jobs[item['envelope_id']] = dict(item)
    elif isinstance(raw_jobs, dict):
        for envelope_id, item in raw_jobs.items():
            if isinstance(item, dict):
                record = dict(item)
                record['envelope_id'] = record.get('envelope_id') or envelope_id
                jobs[record['envelope_id']] = record
    store['jobs'] = jobs
    if 'states' not in store or not store['states']:
        store['states'] = list(JOB_STATES)
    return store


def _load_store(org_id):
    path = _store_path(org_id)
    parent = os.path.dirname(path)
    if org_id and not os.path.isdir(parent):
        _missing_org_error(org_id)
    if os.path.exists(path):
        with open(path) as f:
            return _normalize_store(json.load(f), org_id)
    return _empty_store(org_id)


def _save_store(store, org_id):
    path = _store_path(org_id)
    parent = os.path.dirname(path)
    if org_id and not os.path.isdir(parent):
        _missing_org_error(org_id)
    os.makedirs(parent, exist_ok=True)
    payload = _normalize_store(store, org_id)
    payload['updatedAt'] = _now()
    fd, tmp_path = tempfile.mkstemp(
        prefix='.federated_execution_jobs.',
        suffix='.tmp',
        dir=parent,
    )
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return payload


@contextlib.contextmanager
def _jobs_lock(org_id):
    path = _lock_path(org_id)
    parent = os.path.dirname(path)
    if org_id and not os.path.isdir(parent):
        _missing_org_error(org_id)
    os.makedirs(parent, exist_ok=True)
    with open(path, 'a+') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _normalize_job(job, existing=None):
    job = dict(job or {})
    existing = dict(existing or {})
    envelope_id = (job.get('envelope_id') or existing.get('envelope_id') or '').strip()
    if not envelope_id:
        raise ValueError('envelope_id is required')

    record = dict(existing)
    record['envelope_id'] = envelope_id
    record['job_id'] = (job.get('job_id') or existing.get('job_id') or f'fej_{uuid.uuid4().hex[:12]}').strip()

    required_fields = (
        'source_host_id',
        'source_institution_id',
        'target_host_id',
        'target_institution_id',
        'message_type',
    )
    for field in required_fields:
        if field in job:
            value = (job.get(field) or '').strip()
            if not value:
                raise ValueError(f'{field} is required')
            record[field] = value
        elif not record.get(field):
            raise ValueError(f'{field} is required')

    optional_text_fields = (
        'receipt_id',
        'actor_type',
        'actor_id',
        'session_id',
        'boundary_name',
        'identity_model',
        'sender_warrant_id',
        'local_warrant_id',
        'commitment_id',
        'received_at',
        'updated_at',
        'executed_at',
        'note',
    )
    for field in optional_text_fields:
        if field in job:
            record[field] = (job.get(field) or '').strip()
        elif field not in record:
            record[field] = ''

    if 'state' in job:
        record['state'] = _normalize_state(job.get('state'), existing_state=record.get('state', ''))
    else:
        record['state'] = _normalize_state(record.get('state', ''), existing_state=record.get('state', ''))

    if 'payload' in job:
        record['payload'] = job.get('payload')
    elif 'payload' not in record:
        record['payload'] = None

    if 'payload_hash' in job:
        supplied = job.get('payload_hash')
        record['payload_hash'] = supplied.strip() if supplied else _payload_hash(record.get('payload'))
    elif 'payload_hash' not in record:
        record['payload_hash'] = _payload_hash(record.get('payload'))

    if 'execution_refs' in job:
        record['execution_refs'] = dict(job.get('execution_refs') or {})
    elif 'execution_refs' not in record:
        record['execution_refs'] = {}

    if 'metadata' in job:
        record['metadata'] = dict(job.get('metadata') or {})
    elif 'metadata' not in record:
        record['metadata'] = {}

    if not record.get('received_at'):
        record['received_at'] = _now()
    if not record.get('updated_at'):
        record['updated_at'] = record['received_at']
    if record['state'] == 'executed' and not record.get('executed_at'):
        record['executed_at'] = record['updated_at']
    if record['state'] != 'executed':
        record.setdefault('executed_at', '')

    return record


def upsert_execution_job(org_id, job):
    if not isinstance(job, dict):
        raise TypeError('job must be a dict')
    with _jobs_lock(org_id):
        store = _load_store(org_id)
        envelope_id = (job.get('envelope_id') or '').strip()
        existing = store.get('jobs', {}).get(envelope_id, {})
        record = _normalize_job(job, existing=existing)
        record['updated_at'] = _now()
        if record['state'] == 'executed' and not record.get('executed_at'):
            record['executed_at'] = record['updated_at']
        store.setdefault('jobs', {})[envelope_id] = record
        return _save_store(store, org_id)['jobs'][envelope_id]


def get_execution_job(envelope_id, org_id=None):
    if not envelope_id:
        return None
    store = _load_store(org_id)
    return store.get('jobs', {}).get(envelope_id)


def list_execution_jobs(org_id=None, *, state=None):
    store = _load_store(org_id)
    jobs = list(store.get('jobs', {}).values())
    if state:
        jobs = [row for row in jobs if row.get('state') == state]
    jobs.sort(key=lambda row: (row.get('received_at', ''), row.get('envelope_id', '')), reverse=True)
    return jobs


def execution_job_summary(org_id=None):
    jobs = list_execution_jobs(org_id)
    summary = {
        'total': len(jobs),
        'pending_local_warrant': 0,
        'ready': 0,
        'executed': 0,
        'blocked': 0,
        'rejected': 0,
        'message_type_counts': {},
    }
    message_type_counts = collections.Counter()
    for record in jobs:
        state = (record.get('state') or '').strip()
        if state in summary:
            summary[state] += 1
        message_type_counts[(record.get('message_type') or '').strip() or 'unknown'] += 1
    summary['message_type_counts'] = dict(sorted(message_type_counts.items()))
    return summary


def summary(org_id=None):
    return execution_job_summary(org_id)


def main():
    raise SystemExit('This module is a storage primitive only.')


if __name__ == '__main__':
    main()
