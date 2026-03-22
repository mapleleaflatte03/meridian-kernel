#!/usr/bin/env python3
"""
Governed Workspace -- Owner-facing surface for the Kernel.

Serves an HTML dashboard + JSON API for all five primitives:
  Institution, Agent, Authority, Treasury, Court.

Endpoints:
  GET  /                          -> Dashboard HTML
  GET  /api/status                -> Full system snapshot (JSON)
  GET  /api/institution           -> Institution state
  GET  /api/agents                -> Agent registry
  GET  /api/authority             -> Authority state (kill switch, approvals, delegations)
  GET  /api/treasury              -> Treasury snapshot
  GET  /api/treasury/wallets      -> Wallet registry
  GET  /api/treasury/accounts     -> Treasury sub-accounts
  GET  /api/treasury/maintainers  -> Maintainer registry
  GET  /api/treasury/contributors -> Contributor registry
  GET  /api/treasury/proposals    -> Payout proposals
  GET  /api/treasury/funding-sources -> Funding source records
  GET  /api/admission             -> Host admission state
  GET  /api/federation            -> Federation gateway state
  GET  /api/federation/peers      -> Federation peer registry state
  GET  /api/federation/manifest   -> Public host federation manifest
  GET  /api/runtimes              -> Runtime registry and contract status
  GET  /api/runtimes/<id>         -> Single runtime record
  GET  /api/court                 -> Court records
  GET  /api/warrants              -> Warrant records and summary
  GET  /api/commitments           -> Commitment records and summary
  GET  /api/cases                 -> Inter-institution cases and summary
  POST /api/authority/kill-switch -> Engage/disengage kill switch
  POST /api/authority/approve     -> Decide an approval
  POST /api/authority/request     -> Request approval
  POST /api/authority/delegate    -> Create delegation
  POST /api/authority/revoke      -> Revoke delegation
  POST /api/court/file            -> File a violation
  POST /api/court/resolve         -> Resolve a violation
  POST /api/court/appeal          -> File an appeal
  POST /api/court/decide-appeal   -> Decide an appeal
  POST /api/court/remediate       -> Lift lingering sanctions after review
  POST /api/warrants/issue        -> Issue a warrant record
  POST /api/warrants/approve      -> Approve a warrant for execution
  POST /api/warrants/stay         -> Stay a warrant before execution
  POST /api/warrants/revoke       -> Revoke a warrant before execution
  POST /api/commitments/propose   -> Propose a cross-institution commitment
  POST /api/commitments/accept    -> Accept a commitment
  POST /api/commitments/reject    -> Reject a commitment
  POST /api/commitments/breach    -> Mark a commitment as breached
  POST /api/commitments/settle    -> Mark a commitment as settled
  POST /api/cases/open            -> Open an inter-institution case
  POST /api/cases/stay            -> Stay an inter-institution case
  POST /api/cases/resolve         -> Resolve an inter-institution case
  POST /api/treasury/contribute   -> Record owner capital contribution
  POST /api/treasury/reserve-floor -> Update reserve floor policy
  POST /api/session/issue         -> Issue session token (requires auth)
  GET  /api/session/validate      -> Validate session token
  POST /api/session/revoke        -> Revoke a session
  POST /api/admission/admit       -> Admit an institution on this host
  POST /api/admission/suspend     -> Suspend an admitted institution on this host
  POST /api/admission/revoke      -> Revoke an institution on this host
  POST /api/federation/peers/upsert -> Create or update a federation peer
  POST /api/federation/peers/refresh -> Refresh peer capability snapshot from its public manifest
  POST /api/federation/peers/suspend -> Suspend a federation peer
  POST /api/federation/peers/revoke -> Revoke a federation peer
  POST /api/federation/send       -> Deliver a federation envelope to a trusted peer
  POST /api/federation/receive    -> Validate and consume a federation envelope
  POST /api/institution/charter   -> Set charter
  POST /api/institution/lifecycle -> Transition lifecycle

Run:
  python3 workspace.py                    # port 18901
  python3 workspace.py --port 18902
  python3 workspace.py --org-id <org>    # bind this process to one institution

When workspace credentials are configured, the dashboard and JSON API are
owner-authenticated with HTTP Basic auth.  Session tokens (Authorization:
Bearer) are also accepted as an alternative auth path.

Institution context:
  The built-in workspace is a founding-institution reference surface.  All
  HTTP endpoints bind to one institution selected at process start.
  The underlying kernel helpers accept org_id, but exposing arbitrary org
  selection over HTTP is intentionally deferred until an org-scoped auth
  model exists.
"""
import argparse
import base64
import datetime
import hashlib
import hmac
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PLATFORM_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(PLATFORM_DIR)
EXAMPLES_INTELLIGENCE_DIR = os.path.join(WORKSPACE, 'examples', 'intelligence')
WORKSPACE_CREDENTIALS_FILE = os.environ.get(
    'MERIDIAN_WORKSPACE_CREDENTIALS_FILE',
    '/etc/caddy/.workspace_credentials',
)
RUNTIME_HOST_IDENTITY_FILE = os.environ.get(
    'MERIDIAN_RUNTIME_HOST_IDENTITY_FILE',
    os.path.join(PLATFORM_DIR, 'host_identity.json'),
)
RUNTIME_ADMISSION_FILE = os.environ.get(
    'MERIDIAN_RUNTIME_ADMISSION_FILE',
    os.path.join(PLATFORM_DIR, 'institution_admissions.json'),
)
FEDERATION_PEERS_FILE = os.environ.get(
    'MERIDIAN_FEDERATION_PEERS_FILE',
    os.path.join(PLATFORM_DIR, 'federation_peers.json'),
)
FEDERATION_REPLAY_FILE = os.environ.get(
    'MERIDIAN_FEDERATION_REPLAY_FILE',
    os.path.join(PLATFORM_DIR, '.federation_replay'),
)
FEDERATION_SIGNING_SECRET = (
    os.environ.get('MERIDIAN_FEDERATION_SIGNING_SECRET', '').strip() or None
)
WORKSPACE_ORG_ID = (os.environ.get('MERIDIAN_WORKSPACE_ORG_ID') or '').strip() or None
WORKSPACE_AUTH_REQUIRED = os.environ.get('MERIDIAN_WORKSPACE_AUTH_REQUIRED', '').lower() in (
    '1', 'true', 'yes', 'on'
)
sys.path.insert(0, PLATFORM_DIR)
if os.path.isdir(EXAMPLES_INTELLIGENCE_DIR):
    sys.path.insert(0, EXAMPLES_INTELLIGENCE_DIR)

from organizations import (load_orgs, set_charter, set_policy_defaults,
                           transition_lifecycle as org_transition_lifecycle)
from agent_registry import load_registry, sync_from_economy
from audit import log_event, tail_events

import importlib.util

# Import authority, treasury, court via their public APIs
from authority import (check_authority, request_approval, decide_approval,
                       delegate, revoke_delegation, engage_kill_switch,
                       disengage_kill_switch, get_pending_approvals,
                       get_sprint_lead, is_kill_switch_engaged, _load_queue)
from treasury import (treasury_snapshot, get_balance, get_runway, check_budget,
                      contribute_owner_capital, set_reserve_floor_policy,
                      load_wallets, load_treasury_accounts, load_maintainers,
                      load_contributors, load_payout_proposals, load_funding_sources)
from runtime_adapter import load_runtimes, get_runtime, check_all_contracts
from court import (file_violation, get_violations, resolve_violation,
                   file_appeal, decide_appeal, get_agent_record, auto_review,
                   get_restrictions, remediate, _load_records, VIOLATION_TYPES)
from session import SessionAuthority
from warrants import (
    list_warrants,
    issue_warrant,
    review_warrant,
    validate_warrant_for_execution,
    mark_warrant_executed,
    warrant_action_for_message,
)
from commitments import (
    accept_commitment,
    breach_commitment,
    commitment_summary,
    list_commitments,
    record_delivery_ref,
    reject_commitment,
    propose_commitment,
    settle_commitment,
    validate_commitment_for_delivery,
)
from cases import (
    blocked_peer_host_ids,
    blocking_commitment_ids,
    blocking_commitment_case,
    blocking_peer_case,
    case_requires_peer_block,
    case_summary,
    ensure_case_for_delivery_failure,
    ensure_case_for_commitment_breach,
    list_cases,
    open_case,
    resolve_case,
    stay_case,
)
from federation import (
    FederationAuthority,
    ReplayStore,
    load_peer_registry,
    upsert_peer_registry_entry,
    refresh_peer_registry_entry,
    set_peer_trust_state,
    FederationUnavailable,
    FederationDeliveryError,
    FederationValidationError,
    FederationReplayError,
)
from institution_context import (
    InstitutionContext,
    WORKSPACE_BOUNDARY,
    runtime_core_snapshot,
)
from runtime_host import (
    load_host_identity,
    load_admission_registry,
    ensure_org_admitted,
    set_admission_state,
)

# Process-level session authority (tokens do not survive restarts unless
# MERIDIAN_SESSION_SECRET is set in the environment).
_session_revocation_file = (
    os.environ.get('MERIDIAN_SESSION_REVOCATIONS_FILE', '').strip() or None
)
if not _session_revocation_file and os.environ.get('MERIDIAN_SESSION_SECRET', '').strip():
    # Persistent signing key → revocations must also persist.
    _session_revocation_file = os.path.join(PLATFORM_DIR, '.session_revocations')
_session_authority = SessionAuthority(revocation_file=_session_revocation_file)

# Optional: CI vertical import from the example vertical if present
_ci_vertical_available = False
try:
    from ci_vertical import PIPELINE_PHASES, _phase_gate_snapshot, get_agent_remediation
    _ci_vertical_available = True
except ImportError:
    pass

# Optional: Phase machine import
_phase_machine_available = False
try:
    from phase_machine import current_phase, PHASES as PHASE_DEFS
    _phase_machine_available = True
except ImportError:
    pass


def _now():
    return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


ROLE_RANK = {
    'viewer': 0,
    'member': 1,
    'admin': 2,
    'owner': 3,
}

MUTATION_ROLE_REQUIREMENTS = {
    '/api/authority/kill-switch': 'admin',
    '/api/authority/approve': 'admin',
    '/api/authority/request': 'member',
    '/api/authority/delegate': 'admin',
    '/api/authority/revoke': 'admin',
    '/api/court/file': 'member',
    '/api/court/resolve': 'admin',
    '/api/court/appeal': 'member',
    '/api/court/decide-appeal': 'admin',
    '/api/court/auto-review': 'admin',
    '/api/court/remediate': 'admin',
    '/api/warrants/issue': 'admin',
    '/api/warrants/approve': 'admin',
    '/api/warrants/stay': 'admin',
    '/api/warrants/revoke': 'admin',
    '/api/commitments/propose': 'admin',
    '/api/commitments/accept': 'admin',
    '/api/commitments/reject': 'admin',
    '/api/commitments/breach': 'admin',
    '/api/commitments/settle': 'admin',
    '/api/cases/open': 'admin',
    '/api/cases/stay': 'admin',
    '/api/cases/resolve': 'admin',
    '/api/treasury/contribute': 'owner',
    '/api/treasury/reserve-floor': 'owner',
    '/api/admission/admit': 'owner',
    '/api/admission/suspend': 'owner',
    '/api/admission/revoke': 'owner',
    '/api/federation/send': 'admin',
    '/api/federation/peers/upsert': 'owner',
    '/api/federation/peers/refresh': 'owner',
    '/api/federation/peers/suspend': 'owner',
    '/api/federation/peers/revoke': 'owner',
    '/api/institution/charter': 'admin',
    '/api/institution/lifecycle': 'owner',
    '/api/session/issue': 'member',
    '/api/session/revoke': 'admin',
}


def _load_workspace_credentials():
    env_user = os.environ.get('MERIDIAN_WORKSPACE_USER')
    env_password = os.environ.get('MERIDIAN_WORKSPACE_PASS')
    env_org_id = (os.environ.get('MERIDIAN_WORKSPACE_AUTH_ORG_ID') or '').strip() or None
    env_user_id = (os.environ.get('MERIDIAN_WORKSPACE_USER_ID') or '').strip() or None
    if env_user and env_password:
        return env_user, env_password, env_org_id, env_user_id
    if not os.path.exists(WORKSPACE_CREDENTIALS_FILE):
        return None, None, None, None
    user = None
    password = None
    org_id = None
    user_id = None
    with open(WORKSPACE_CREDENTIALS_FILE) as f:
        for raw_line in f:
            line = raw_line.strip()
            if line.startswith('user:'):
                user = line.split(':', 1)[1].strip()
            elif line.startswith('pass:'):
                password = line.split(':', 1)[1].strip()
            elif line.startswith('org_id:'):
                org_id = line.split(':', 1)[1].strip() or None
            elif line.startswith('user_id:'):
                user_id = line.split(':', 1)[1].strip() or None
    return user, password, org_id, user_id


def _resolve_workspace_context():
    """Bind this workspace process to exactly one institution.

    Returns an InstitutionContext backed by the WORKSPACE_BOUNDARY declaration.
    Resolution order: explicit --org-id > credential org scope > founding default.
    """
    configured_org_id = WORKSPACE_ORG_ID
    cred_user, cred_password, credential_org_id, _credential_user_id = _load_workspace_credentials()
    credential_scope_active = bool(cred_user and cred_password and credential_org_id)
    if configured_org_id and credential_scope_active and configured_org_id != credential_org_id:
        raise RuntimeError(
            f"Workspace credentials are scoped to institution '{credential_org_id}', "
            f"but process binding requested '{configured_org_id}'"
        )
    if configured_org_id:
        org = load_orgs().get('organizations', {}).get(configured_org_id)
        if not org:
            raise RuntimeError(f'Configured workspace org not found: {configured_org_id}')
        ctx = InstitutionContext.bind(configured_org_id, org, 'configured_org', WORKSPACE_BOUNDARY)
        _runtime_host_state(ctx.org_id)
        return ctx
    if credential_scope_active:
        org = load_orgs().get('organizations', {}).get(credential_org_id)
        if not org:
            raise RuntimeError(f'Credential-scoped workspace org not found: {credential_org_id}')
        ctx = InstitutionContext.bind(credential_org_id, org, 'credentials_org', WORKSPACE_BOUNDARY)
        _runtime_host_state(ctx.org_id)
        return ctx
    ctx = InstitutionContext.resolve(WORKSPACE_BOUNDARY)
    _runtime_host_state(ctx.org_id)
    return ctx


def _runtime_host_state(bound_org_id):
    host_identity = load_host_identity(
        RUNTIME_HOST_IDENTITY_FILE,
        supported_boundaries=[
            'workspace',
            'cli',
            'federation_gateway',
            'mcp_service',
            'payment_monitor',
            'subscriptions',
            'accounting',
        ],
    )
    admission_registry = load_admission_registry(
        RUNTIME_ADMISSION_FILE,
        bound_org_id=bound_org_id,
        host_identity=host_identity,
    )
    ensure_org_admitted(bound_org_id, admission_registry)
    return host_identity, admission_registry


def _federation_authority(host_identity, peer_registry=None):
    return FederationAuthority(
        host_identity,
        signing_secret=FEDERATION_SIGNING_SECRET,
        peer_registry=(
            peer_registry
            if peer_registry is not None else
            load_peer_registry(FEDERATION_PEERS_FILE, host_identity=host_identity)
        ),
        replay_store=ReplayStore(FEDERATION_REPLAY_FILE),
    )


def _federation_management_state(host_identity):
    if getattr(host_identity, 'role', '') == 'witness_host':
        return {
            'management_mode': 'witness_read_only',
            'mutation_enabled': False,
            'mutation_disabled_reason': 'witness_host_read_only',
        }
    return {
        'management_mode': 'workspace_api_file_backed',
        'mutation_enabled': True,
        'mutation_disabled_reason': '',
    }


def _federation_snapshot(bound_org_id, host_identity=None, admission_registry=None, peer_registry=None):
    if host_identity is None or admission_registry is None:
        host_identity, admission_registry = _runtime_host_state(bound_org_id)
    snapshot = _federation_authority(host_identity, peer_registry=peer_registry).snapshot(
        bound_org_id=bound_org_id,
        admission_registry=admission_registry,
    )
    snapshot.update(_federation_management_state(host_identity))
    return snapshot


def _federation_manifest(context, host_identity=None, admission_registry=None):
    if host_identity is None or admission_registry is None:
        host_identity, admission_registry = _runtime_host_state(context.org_id)
    admission_management = _admission_management_state(host_identity)
    runtime_core = runtime_core_snapshot(
        context,
        additional_institutions_allowed=bool(
            admission_management['mutation_enabled']
            or len(admission_registry.get('admitted_org_ids', [])) > 1
        ),
        host_identity=host_identity,
        admission_registry=admission_registry,
        admission_management_mode=admission_management['management_mode'],
        admission_mutation_enabled=admission_management['mutation_enabled'],
        admission_mutation_disabled_reason=admission_management['mutation_disabled_reason'],
    )
    federation = _federation_snapshot(
        context.org_id,
        host_identity=host_identity,
        admission_registry=admission_registry,
    )
    return {
        'manifest_version': 1,
        'generated_at': _now(),
        'host_identity': runtime_core['host_identity'],
        'institution_context': runtime_core['institution_context'],
        'admission': runtime_core['admission'],
        'service_registry': runtime_core['service_registry'],
        'federation': {
            key: value
            for key, value in federation.items()
            if key not in ('peers', 'trusted_peers', 'trusted_peer_ids')
        },
    }


def _admission_management_state(host_identity):
    if getattr(host_identity, 'role', '') == 'witness_host':
        return {
            'management_mode': 'witness_read_only',
            'mutation_enabled': False,
            'mutation_disabled_reason': 'witness_host_read_only',
        }
    return {
        'management_mode': 'workspace_api_file_backed',
        'mutation_enabled': True,
        'mutation_disabled_reason': '',
    }


def _admission_snapshot(bound_org_id, host_identity=None, admission_registry=None):
    if host_identity is None or admission_registry is None:
        host_identity, admission_registry = _runtime_host_state(bound_org_id)
    institutions = {}
    for org_id, entry in sorted(admission_registry.get('institutions', {}).items()):
        data = dict(entry or {})
        data['org_id'] = org_id
        institutions[org_id] = data
    return {
        'bound_org_id': bound_org_id,
        'host_id': host_identity.host_id,
        'host_role': host_identity.role,
        'source': admission_registry.get('source', 'none'),
        'admitted_org_ids': list(admission_registry.get('admitted_org_ids', [])),
        'institutions': institutions,
        **_admission_management_state(host_identity),
    }


def _mutate_admission(bound_org_id, action, target_org_id):
    host_identity, _admission_registry = _runtime_host_state(bound_org_id)
    management = _admission_management_state(host_identity)
    if not management['mutation_enabled']:
        raise PermissionError(
            f"Admission mutations are disabled on host '{host_identity.host_id}' "
            f"({management['mutation_disabled_reason']})"
        )
    target_org_id = (target_org_id or '').strip()
    if not target_org_id:
        raise ValueError('org_id is required')
    if target_org_id not in load_orgs().get('organizations', {}):
        raise LookupError(f"Institution '{target_org_id}' is not registered")
    if action in ('suspend', 'revoke') and target_org_id == bound_org_id:
        raise PermissionError(
            'Cannot suspend or revoke the currently bound institution from its own workspace process'
        )
    status_map = {
        'admit': 'admitted',
        'suspend': 'suspended',
        'revoke': 'revoked',
    }
    if action not in status_map:
        raise ValueError(f'Unsupported admission action: {action}')
    updated = set_admission_state(
        RUNTIME_ADMISSION_FILE,
        target_org_id,
        status_map[action],
        bound_org_id=bound_org_id,
        host_identity=host_identity,
        source='workspace_api',
    )
    return _admission_snapshot(
        bound_org_id,
        host_identity=host_identity,
        admission_registry=updated,
    )


def _accept_federation_request(bound_org_id, envelope, payload=None):
    host_identity, admission_registry = _runtime_host_state(bound_org_id)
    authority = _federation_authority(host_identity)
    claims = authority.accept(
        envelope,
        payload=payload,
        expected_target_host_id=host_identity.host_id,
        expected_target_org_id=bound_org_id,
        expected_boundary_name='federation_gateway',
    )
    return claims, authority.snapshot(
        bound_org_id=bound_org_id,
        admission_registry=admission_registry,
    )


def _mutate_federation_peer(bound_org_id, action, payload):
    host_identity, admission_registry = _runtime_host_state(bound_org_id)
    management = _federation_management_state(host_identity)
    if not management['mutation_enabled']:
        raise PermissionError(
            f"Federation peer mutations are disabled on host '{host_identity.host_id}' "
            f"({management['mutation_disabled_reason']})"
        )

    payload = dict(payload or {})
    peer_host_id = (payload.get('peer_host_id') or payload.get('host_id') or '').strip()
    if not peer_host_id:
        raise ValueError('peer_host_id is required')
    if peer_host_id == host_identity.host_id:
        raise PermissionError('Cannot register the current host as its own federation peer')

    if action == 'upsert':
        peer_registry = upsert_peer_registry_entry(
            FEDERATION_PEERS_FILE,
            peer_host_id,
            host_identity=host_identity,
            label=payload.get('label'),
            transport=payload.get('transport'),
            endpoint_url=payload.get('endpoint_url'),
            trust_state=payload.get('trust_state'),
            shared_secret=payload.get('shared_secret'),
            admitted_org_ids=payload.get('admitted_org_ids'),
        )
    elif action == 'refresh':
        peer_registry = refresh_peer_registry_entry(
            FEDERATION_PEERS_FILE,
            peer_host_id,
            host_identity=host_identity,
            target_org_id=(payload.get('target_org_id') or '').strip() or None,
        )
    else:
        status_map = {
            'suspend': 'suspended',
            'revoke': 'revoked',
        }
        if action not in status_map:
            raise ValueError(f'Unsupported federation peer action: {action}')
        peer_registry = set_peer_trust_state(
            FEDERATION_PEERS_FILE,
            peer_host_id,
            status_map[action],
            host_identity=host_identity,
        )
    return _federation_snapshot(
        bound_org_id,
        host_identity=host_identity,
        admission_registry=admission_registry,
        peer_registry=peer_registry,
    )


def _federation_claims_dict(claims):
    if not claims:
        return {}
    if isinstance(claims, dict):
        return dict(claims)
    if hasattr(claims, 'to_dict'):
        return claims.to_dict()
    return {}


def _federation_audit_details(claims, **extra):
    claim_data = _federation_claims_dict(claims)
    details = {
        'envelope_id': claim_data.get('envelope_id', ''),
        'source_host_id': claim_data.get('source_host_id', ''),
        'source_institution_id': claim_data.get('source_institution_id', ''),
        'target_host_id': claim_data.get('target_host_id', ''),
        'target_institution_id': claim_data.get('target_institution_id', ''),
        'nonce': claim_data.get('nonce', ''),
        'boundary_name': claim_data.get('boundary_name', ''),
        'warrant_id': claim_data.get('warrant_id', ''),
        'commitment_id': claim_data.get('commitment_id', ''),
    }
    for key, value in extra.items():
        if value not in (None, ''):
            details[key] = value
    return details


def _federation_receipt(bound_org_id, receiver_host_id, claims):
    claim_data = _federation_claims_dict(claims)
    envelope_id = claim_data.get('envelope_id', '')
    receipt_material = ':'.join((
        (receiver_host_id or '').strip(),
        (bound_org_id or '').strip(),
        envelope_id,
    ))
    receipt_id = 'fedrcpt_' + hashlib.sha256(receipt_material.encode('utf-8')).hexdigest()[:12]
    return {
        'receipt_id': receipt_id,
        'envelope_id': envelope_id,
        'accepted_at': _now(),
        'receiver_host_id': (receiver_host_id or '').strip(),
        'receiver_institution_id': (bound_org_id or '').strip(),
        'message_type': claim_data.get('message_type', ''),
        'boundary_name': claim_data.get('boundary_name', ''),
        'identity_model': 'signed_host_service',
    }


def _federation_peer_state(peer_host_id, *, host_identity=None):
    peer_host_id = (peer_host_id or '').strip()
    if not peer_host_id:
        return None
    try:
        registry = load_peer_registry(
            FEDERATION_PEERS_FILE,
            host_identity=host_identity or load_host_identity(RUNTIME_HOST_IDENTITY_FILE),
        )
    except RuntimeError:
        return {
            'applied': False,
            'peer_host_id': peer_host_id,
            'reason': 'peer_registry_unavailable',
        }
    peer = registry.get('peers', {}).get(peer_host_id)
    if not peer:
        return {
            'applied': False,
            'peer_host_id': peer_host_id,
            'reason': 'peer_not_registered',
        }
    return {
        'applied': False,
        'peer_host_id': peer.host_id,
        'trust_state': peer.trust_state,
        'admitted_org_ids': list(peer.admitted_org_ids),
        'label': peer.label,
        'reason': 'case_blocked',
    }


def _deliver_federation_envelope(bound_org_id, target_host_id, target_org_id,
                                 message_type, payload=None, *,
                                 actor_type='host_service', actor_id='',
                                 session_id='', warrant_id='',
                                 commitment_id='', ttl_seconds=None):
    host_identity, admission_registry = _runtime_host_state(bound_org_id)
    authority = _federation_authority(host_identity)
    authority.ensure_enabled()
    execution_warrant = None
    linked_commitment = None
    required_action = warrant_action_for_message(message_type)
    if required_action:
        if not warrant_id:
            message = (
                f"Federation message_type '{message_type}' requires warrant_id "
                f"for action_class '{required_action}'"
            )
            log_event(
                bound_org_id,
                actor_id or f'host:{host_identity.host_id}',
                'federation_warrant_blocked',
                resource=message_type,
                outcome='blocked',
                actor_type=actor_type or 'service',
                details={
                    'target_host_id': target_host_id,
                    'target_institution_id': target_org_id,
                    'required_action_class': required_action,
                    'error': message,
                },
                session_id=session_id or None,
            )
            raise PermissionError(message)
        try:
            execution_warrant = validate_warrant_for_execution(
                warrant_id,
                org_id=bound_org_id,
                action_class=required_action,
                boundary_name='federation_gateway',
                actor_id=actor_id,
                session_id=session_id,
                request_payload=payload,
            )
        except PermissionError as exc:
            log_event(
                bound_org_id,
                actor_id or f'host:{host_identity.host_id}',
                'federation_warrant_blocked',
                resource=message_type,
                outcome='blocked',
                actor_type=actor_type or 'service',
                details={
                    'target_host_id': target_host_id,
                    'target_institution_id': target_org_id,
                    'warrant_id': warrant_id,
                    'required_action_class': required_action,
                    'error': str(exc),
                },
                session_id=session_id or None,
            )
            raise
    if commitment_id:
        try:
            linked_commitment = validate_commitment_for_delivery(
                commitment_id,
                target_institution_id=target_org_id,
                org_id=bound_org_id,
                target_host_id=target_host_id,
                warrant_id=warrant_id,
            )
        except (PermissionError, ValueError) as exc:
            log_event(
                bound_org_id,
                actor_id or f'host:{host_identity.host_id}',
                'federation_commitment_blocked',
                resource=message_type,
                outcome='blocked',
                actor_type=actor_type or 'service',
                details={
                    'target_host_id': target_host_id,
                    'target_institution_id': target_org_id,
                    'commitment_id': commitment_id,
                    'error': str(exc),
                },
                session_id=session_id or None,
            )
            raise
    blocking_case = _blocking_case_for_delivery(
        org_id=bound_org_id,
        commitment_id=commitment_id,
        target_host_id=target_host_id,
    )
    if blocking_case:
        message = (
            f"Federation delivery is blocked by case '{blocking_case.get('case_id', '')}' "
            f"(claim_type={blocking_case.get('claim_type', '')}, "
            f"status={blocking_case.get('status', '')})"
        )
        log_event(
            bound_org_id,
            actor_id or f'host:{host_identity.host_id}',
            'federation_case_blocked',
            resource=message_type,
            outcome='blocked',
            actor_type=actor_type or 'service',
            details={
                'target_host_id': target_host_id,
                'target_institution_id': target_org_id,
                'commitment_id': commitment_id,
                'case_id': blocking_case.get('case_id', ''),
                'claim_type': blocking_case.get('claim_type', ''),
                'case_status': blocking_case.get('status', ''),
                'error': message,
            },
            session_id=session_id or None,
        )
        error = PermissionError(message)
        error.case_record = blocking_case
        error.federation_peer = _federation_peer_state(
            target_host_id,
            host_identity=host_identity,
        )
        error.warrant = _maybe_stay_warrant_for_case(
            blocking_case,
            actor_id or f'host:{host_identity.host_id}',
            org_id=bound_org_id,
            session_id=session_id or None,
            note=message,
        )
        raise error
    try:
        delivery = authority.deliver(
            target_host_id,
            bound_org_id,
            target_org_id,
            message_type,
            payload=payload,
            actor_type=actor_type,
            actor_id=actor_id,
            session_id=session_id,
            warrant_id=warrant_id,
            commitment_id=commitment_id,
            ttl_seconds=ttl_seconds,
        )
    except FederationDeliveryError as exc:
        case_record, federation_peer = _maybe_open_case_for_delivery_failure(
            exc,
            actor_id or f'host:{host_identity.host_id}',
            org_id=bound_org_id,
            target_host_id=target_host_id,
            target_institution_id=target_org_id,
            commitment_id=commitment_id,
            warrant_id=warrant_id,
            session_id=session_id or None,
        )
        warrant_hold = _maybe_stay_warrant_for_case(
            case_record,
            actor_id or f'host:{host_identity.host_id}',
            org_id=bound_org_id,
            session_id=session_id or None,
            note=str(exc),
        )
        log_event(
            bound_org_id,
            actor_id or f'host:{host_identity.host_id}',
            'federation_envelope_delivery_failed',
            resource=message_type,
            outcome='failed',
            actor_type=actor_type or 'service',
            details=_federation_audit_details(
                exc.claims,
                target_host_id=exc.peer_host_id or target_host_id,
                target_institution_id=target_org_id,
                error=str(exc),
            ),
            session_id=session_id or None,
        )
        exc.case_record = case_record
        exc.federation_peer = federation_peer
        exc.warrant = warrant_hold
        raise

    claims = delivery.get('claims')
    receipt = dict(delivery.get('receipt') or {})
    if not receipt and isinstance(delivery.get('response'), dict):
        receipt = dict(delivery['response'].get('receipt') or {})
    if execution_warrant:
        mark_warrant_executed(
            warrant_id,
            org_id=bound_org_id,
            execution_refs={
                'message_type': message_type,
                'envelope_id': (claims or {}).get('envelope_id', ''),
                'target_host_id': target_host_id,
                'target_institution_id': target_org_id,
                'receipt_id': receipt.get('receipt_id', ''),
                'receiver_host_id': receipt.get('receiver_host_id', ''),
                'receiver_institution_id': receipt.get('receiver_institution_id', ''),
            },
        )
    commitment_delivery_ref = None
    if linked_commitment:
        commitment_delivery_ref = record_delivery_ref(
            commitment_id,
            org_id=bound_org_id,
            delivery_ref={
                'recorded_at': _now(),
                'message_type': message_type,
                'envelope_id': (claims or {}).get('envelope_id', ''),
                'target_host_id': target_host_id,
                'target_institution_id': target_org_id,
                'receipt_id': receipt.get('receipt_id', ''),
                'receiver_host_id': receipt.get('receiver_host_id', ''),
                'receiver_institution_id': receipt.get('receiver_institution_id', ''),
                'warrant_id': warrant_id,
            },
        )
        log_event(
            bound_org_id,
            actor_id or f'host:{host_identity.host_id}',
            'commitment_delivery_recorded',
            resource=commitment_id,
            outcome='success',
            actor_type=actor_type or 'service',
            details={
                'target_host_id': target_host_id,
                'target_institution_id': target_org_id,
                'message_type': message_type,
                'receipt_id': receipt.get('receipt_id', ''),
            },
            session_id=session_id or None,
        )
    log_event(
        bound_org_id,
        actor_id or f'host:{host_identity.host_id}',
        'federation_envelope_sent',
        resource=message_type,
        outcome='accepted',
        actor_type=actor_type or 'service',
        details=_federation_audit_details(
            claims,
            peer_transport=(delivery.get('peer') or {}).get('transport', ''),
            receipt_id=receipt.get('receipt_id', ''),
            receiver_host_id=receipt.get('receiver_host_id', ''),
            receiver_institution_id=receipt.get('receiver_institution_id', ''),
            commitment_delivery_recorded=bool(commitment_delivery_ref),
        ),
        session_id=session_id or None,
    )
    return delivery, authority.snapshot(
        bound_org_id=bound_org_id,
        admission_registry=admission_registry,
    )


def _requested_org_override(parsed_url, headers):
    query_org_ids = [value for value in parse_qs(parsed_url.query).get('org_id', []) if value]
    header_org_id = (headers.get('X-Meridian-Org-Id', '') or '').strip()
    requested = set(query_org_ids + ([header_org_id] if header_org_id else []))
    if not requested:
        return None
    if len(requested) > 1:
        raise ValueError('Conflicting institution context hints in request')
    return requested.pop()


def _enforce_request_context(parsed_url, headers, bound_org_id):
    requested_org_id = _requested_org_override(parsed_url, headers)
    if requested_org_id and requested_org_id != bound_org_id:
        raise ValueError(
            f"Workspace is bound to institution '{bound_org_id}'. "
            f"Request-level override '{requested_org_id}' is not allowed."
        )
    return {
        'mode': 'process_bound',
        'bound_org_id': bound_org_id,
        'request_override': 'exact-match-only',
        'requested_org_id': requested_org_id,
    }


def _resolve_auth_context(bound_org_id):
    user, password, credential_org_id, credential_user_id = _load_workspace_credentials()
    auth_enabled = bool(user and password)
    if credential_org_id and auth_enabled and credential_org_id != bound_org_id:
        raise RuntimeError(
            f"Workspace credentials are scoped to institution '{credential_org_id}', "
            f"but process is bound to '{bound_org_id}'"
        )
    resolved_user_id = None
    actor_source = None
    if credential_user_id:
        resolved_user_id = credential_user_id
        actor_source = 'credentials'
    elif user and _member_role(bound_org_id, user):
        resolved_user_id = user
        actor_source = 'basic_user_id'
    elif user == 'owner':
        org = load_orgs().get('organizations', {}).get(bound_org_id)
        owner_id = (org or {}).get('owner_id')
        if owner_id:
            resolved_user_id = owner_id
            actor_source = 'owner_alias'
    role = _member_role(bound_org_id, resolved_user_id)
    actor_id = resolved_user_id or (f'workspace_user:{user}' if user else None)
    if not auth_enabled:
        return {
            'enabled': False,
            'mode': 'required_missing' if WORKSPACE_AUTH_REQUIRED else 'disabled',
            'org_id': None,
            'user_id': None,
            'role': None,
            'actor_id': None,
            'actor_source': None,
        }
    if credential_org_id:
        return {
            'enabled': True,
            'mode': 'credential_bound',
            'org_id': credential_org_id,
            'user_id': resolved_user_id,
            'role': role,
            'actor_id': actor_id,
            'actor_source': actor_source or 'credentials',
        }
    return {
        'enabled': True,
        'mode': 'process_bound_basic',
        'org_id': bound_org_id,
        'user_id': resolved_user_id,
        'role': role,
        'actor_id': actor_id,
        'actor_source': actor_source or 'basic_user',
    }


def _resolve_auth_context_from_session(claims, bound_org_id):
    """Build auth context from validated session claims.

    The session records the role at issuance, but we re-check live membership
    so that removed or downgraded members lose access immediately.
    """
    if claims.org_id != bound_org_id:
        raise ValueError(
            f"Session is bound to institution '{claims.org_id}', "
            f"but workspace is bound to '{bound_org_id}'"
        )
    current_role = _member_role(bound_org_id, claims.user_id)
    return {
        'enabled': True,
        'mode': 'session_bound',
        'org_id': bound_org_id,
        'user_id': claims.user_id,
        'role': current_role,
        'actor_id': claims.user_id,
        'actor_source': 'session',
        'session_id': claims.session_id,
    }


def _member_role(org_id, user_id):
    if not org_id or not user_id:
        return None
    org = load_orgs().get('organizations', {}).get(org_id)
    if not org:
        return None
    for member in org.get('members', []):
        if member.get('user_id') == user_id:
            return member.get('role')
    return None


def _required_mutation_role(path):
    return MUTATION_ROLE_REQUIREMENTS.get(path, 'admin')


def _enforce_mutation_authorization(auth_context, org_id, path):
    if not auth_context.get('enabled'):
        raise PermissionError('Workspace auth is required for mutations')
    role = auth_context.get('role')
    if not role:
        raise PermissionError(
            f"Workspace credential actor is not a member of institution '{org_id}'"
        )
    required_role = _required_mutation_role(path)
    if ROLE_RANK.get(role, -1) < ROLE_RANK.get(required_role, 99):
        raise PermissionError(
            f"Workspace actor role '{role}' cannot mutate '{path}'; requires {required_role}"
        )
    return required_role


def _permission_snapshot(auth_context):
    role = auth_context.get('role')
    permissions = {}
    for path, required_role in MUTATION_ROLE_REQUIREMENTS.items():
        permissions[path] = {
            'required_role': required_role,
            'allowed': bool(
                auth_context.get('enabled')
                and role
                and ROLE_RANK.get(role, -1) >= ROLE_RANK.get(required_role, 99)
            ),
        }
    return {
        'read_allowed': bool(auth_context.get('enabled') or not WORKSPACE_AUTH_REQUIRED),
        'mutation_paths': permissions,
    }


def _warrant_summary(org_id):
    warrants = list_warrants(org_id)
    pending_review = 0
    executable = 0
    executed = 0
    for record in warrants:
        if record.get('court_review_state') == 'pending_review':
            pending_review += 1
        if record.get('court_review_state') in ('auto_issued', 'approved') and record.get('execution_state') == 'ready':
            executable += 1
        if record.get('execution_state') == 'executed':
            executed += 1
    return {
        'total': len(warrants),
        'pending_review': pending_review,
        'executable': executable,
        'executed': executed,
    }


def _commitment_summary(org_id):
    return commitment_summary(org_id)


def _commitment_management_state():
    return {
        'management_mode': 'workspace_api_file_backed',
        'mutation_enabled': True,
        'mutation_disabled_reason': '',
    }


def _commitment_snapshot(org_id):
    return {
        'bound_org_id': org_id,
        **_commitment_management_state(),
        **_commitment_summary(org_id),
        'commitments': list_commitments(org_id),
    }


def _case_management_state():
    return {
        'management_mode': 'workspace_api_file_backed',
        'mutation_enabled': True,
        'mutation_disabled_reason': '',
    }


def _case_snapshot(org_id):
    return {
        'bound_org_id': org_id,
        **_case_management_state(),
        **case_summary(org_id),
        'blocking_commitment_ids': blocking_commitment_ids(org_id),
        'blocked_peer_host_ids': blocked_peer_host_ids(org_id),
        'cases': list_cases(org_id),
    }


def _maybe_open_case_for_commitment_breach(commitment_record, actor_id, *, org_id, note=''):
    return ensure_case_for_commitment_breach(
        commitment_record,
        actor_id,
        org_id=org_id,
        note=note,
    )


def _maybe_stay_warrant_for_case(case_record, actor_id, *, org_id, session_id=None, note=''):
    warrant_id = (case_record or {}).get('linked_warrant_id', '').strip()
    if not warrant_id:
        return None
    record = next(
        (item for item in list_warrants(org_id) if item.get('warrant_id') == warrant_id),
        None,
    )
    if not record:
        return {
            'applied': False,
            'warrant_id': warrant_id,
            'reason': 'warrant_not_found',
            'court_review_state': '',
            'execution_state': '',
        }
    review_state = record.get('court_review_state', '')
    execution_state = record.get('execution_state', '')
    if execution_state != 'ready':
        return {
            'applied': False,
            'warrant_id': warrant_id,
            'reason': f'execution_state_{execution_state or "unknown"}',
            'court_review_state': review_state,
            'execution_state': execution_state,
            'warrant': record,
        }
    if review_state == 'stayed':
        return {
            'applied': False,
            'warrant_id': warrant_id,
            'reason': 'already_stayed',
            'court_review_state': review_state,
            'execution_state': execution_state,
            'warrant': record,
        }
    if review_state == 'revoked':
        return {
            'applied': False,
            'warrant_id': warrant_id,
            'reason': 'already_revoked',
            'court_review_state': review_state,
            'execution_state': execution_state,
            'warrant': record,
        }
    stayed = review_warrant(
        warrant_id,
        'stay',
        actor_id,
        org_id=org_id,
        note=note or f"Automatically stayed because case {case_record.get('case_id', '')} is active",
    )
    log_event(
        org_id,
        actor_id,
        'warrant_stayed_for_case',
        outcome='success',
        resource=warrant_id,
        details={
            'case_id': case_record.get('case_id', ''),
            'claim_type': case_record.get('claim_type', ''),
            'previous_court_review_state': review_state,
            'court_review_state': stayed.get('court_review_state', ''),
        },
        session_id=session_id,
    )
    return {
        'applied': True,
        'warrant_id': warrant_id,
        'reason': 'case_hold_applied',
        'court_review_state': stayed.get('court_review_state', ''),
        'execution_state': stayed.get('execution_state', ''),
        'warrant': stayed,
    }


def _maybe_block_commitment_settlement(commitment_id, actor_id, *, org_id, session_id=None, note=''):
    case_record = blocking_commitment_case(commitment_id, org_id=org_id)
    if not case_record:
        return None, None
    warrant = _maybe_stay_warrant_for_case(
        case_record,
        actor_id,
        org_id=org_id,
        session_id=session_id,
        note=note or f"Settlement blocked while case {case_record.get('case_id', '')} remains active",
    )
    log_event(
        org_id,
        actor_id,
        'commitment_settlement_blocked',
        outcome='blocked',
        resource=commitment_id,
        details={
            'case_id': case_record.get('case_id', ''),
            'claim_type': case_record.get('claim_type', ''),
            'case_status': case_record.get('status', ''),
            'linked_warrant_id': case_record.get('linked_warrant_id', ''),
        },
        session_id=session_id,
    )
    return case_record, warrant


def _blocking_case_for_delivery(*, org_id, commitment_id='', target_host_id=''):
    try:
        commitment_case = blocking_commitment_case(commitment_id, org_id=org_id)
        if commitment_case:
            return commitment_case
        return blocking_peer_case(target_host_id, org_id=org_id)
    except (SystemExit, ValueError):
        return None


def _maybe_suspend_peer_for_case(case_record, actor_id, *, org_id, session_id=None):
    if not case_requires_peer_block(case_record):
        return None
    target_host_id = (case_record.get('target_host_id') or '').strip()
    if not target_host_id:
        return None
    host_identity, admission_registry = _runtime_host_state(org_id)
    management = _federation_management_state(host_identity)
    if not management['mutation_enabled']:
        return {
            'applied': False,
            'peer_host_id': target_host_id,
            'reason': management['mutation_disabled_reason'],
            'trust_state': '',
        }
    try:
        peer_registry = set_peer_trust_state(
            FEDERATION_PEERS_FILE,
            target_host_id,
            'suspended',
            host_identity=host_identity,
        )
    except LookupError:
        return {
            'applied': False,
            'peer_host_id': target_host_id,
            'reason': 'peer_not_registered',
            'trust_state': '',
        }

    snapshot = _federation_snapshot(
        org_id,
        host_identity=host_identity,
        admission_registry=admission_registry,
        peer_registry=peer_registry,
    )
    peer_record = next(
        (peer for peer in snapshot.get('peers', []) if peer.get('host_id') == target_host_id),
        None,
    )
    log_event(
        org_id,
        actor_id,
        'federation_peer_auto_suspended',
        resource=target_host_id,
        outcome='success',
        details={
            'peer_host_id': target_host_id,
            'case_id': case_record.get('case_id', ''),
            'claim_type': case_record.get('claim_type', ''),
            'trust_state': (peer_record or {}).get('trust_state', ''),
        },
        session_id=session_id,
    )
    return {
        'applied': True,
        'peer_host_id': target_host_id,
        'reason': '',
        'trust_state': (peer_record or {}).get('trust_state', ''),
        'federation': snapshot,
    }


def _delivery_failure_claim_type(error_message):
    message = (error_message or '').lower()
    if not message:
        return ''
    if 'signature verification failed' in message:
        return 'fraudulent_proof'
    if 'receiver_host_id' in message or 'receiver_institution_id' in message:
        return 'misrouted_execution'
    if 'receipt' in message:
        return 'invalid_settlement_notice'
    return ''


def _maybe_open_case_for_delivery_failure(exc, actor_id, *, org_id, target_host_id,
                                          target_institution_id, commitment_id='',
                                          warrant_id='', session_id=None):
    claim_type = _delivery_failure_claim_type(str(exc))
    if not claim_type:
        return None, None
    try:
        case_record, created = ensure_case_for_delivery_failure(
            claim_type,
            actor_id,
            org_id=org_id,
            target_host_id=target_host_id,
            target_institution_id=target_institution_id,
            linked_commitment_id=commitment_id,
            linked_warrant_id=warrant_id,
            note=str(exc),
            metadata={
                'peer_host_id': exc.peer_host_id,
                'error': str(exc),
            },
        )
    except (SystemExit, ValueError):
        return None, None
    if created:
        log_event(
            org_id,
            actor_id,
            'case_opened',
            resource=case_record['case_id'],
            outcome='success',
            details={
                'claim_type': case_record.get('claim_type', ''),
                'linked_commitment_id': case_record.get('linked_commitment_id', ''),
                'source': 'federation_delivery_failure',
            },
            session_id=session_id,
        )
    return case_record, _maybe_suspend_peer_for_case(
        case_record,
        actor_id,
        org_id=org_id,
        session_id=session_id,
    )


def _scoped_registry(org_id):
    """Filter agent registry to a single institution's agents.

    Currently always called with the founding org from _get_founding_org().
    The org_id filter is real substrate behavior (not inert) — it correctly
    excludes agents that belong to a different org_id.  Multi-org API
    exposure is blocked until an org-scoped auth model exists.
    """
    reg = load_registry()
    if org_id is None:
        return reg
    scoped_agents = {
        agent_id: agent
        for agent_id, agent in reg.get('agents', {}).items()
        if agent.get('org_id') in (None, org_id)
    }
    return {
        **reg,
        'agents': scoped_agents,
    }


# -- API data builders --------------------------------------------------------

def api_status(org_id=None, context_source='founding_default', institution_context=None):
    if institution_context is not None:
        inst_ctx = institution_context
    elif org_id is None:
        inst_ctx = _resolve_workspace_context()
    else:
        org = load_orgs().get('organizations', {}).get(org_id)
        inst_ctx = InstitutionContext.bind(org_id, org, context_source, WORKSPACE_BOUNDARY)

    org_id = inst_ctx.org_id
    org = inst_ctx.org
    context_source = inst_ctx.context_source
    host_identity, admission_registry = _runtime_host_state(org_id)

    reg = _scoped_registry(org_id)
    queue = _load_queue(org_id)
    snap = treasury_snapshot(org_id)
    records = _load_records(org_id)
    lead_id, lead_auth = get_sprint_lead(org_id)
    auth_context = _resolve_auth_context(org_id)

    agents = []
    remediations = []
    for a in reg['agents'].values():
        restrictions = get_restrictions(a.get('economy_key', a['name'].lower()), org_id=org_id)
        remediation = None
        if _ci_vertical_available:
            remediation = get_agent_remediation(a.get('economy_key', a['name'].lower()), reg)
        if remediation:
            remediations.append(remediation)
        agents.append({
            'id': a['id'], 'name': a['name'], 'role': a['role'],
            'purpose': a['purpose'],
            'rep': a['reputation_units'], 'auth': a['authority_units'],
            'risk_state': a.get('risk_state', 'nominal'),
            'lifecycle_state': a.get('lifecycle_state', 'active'),
            'economy_key': a.get('economy_key'),
            'incident_count': a.get('incident_count', 0),
            'restrictions': restrictions,
            'is_sprint_lead': a.get('economy_key') == lead_id,
            'remediation': remediation,
        })

    open_violations = [v for v in records['violations'].values()
                       if v['status'] in ('open', 'sanctioned', 'appealed')]
    pending_appeals = [a for a in records['appeals'].values()
                       if a['status'] == 'pending']
    pending_approvals = [a for a in queue['pending_approvals'].values()
                         if a['status'] == 'pending']
    active_delegations = [d for d in queue['delegations'].values()
                          if d.get('expires_at', '') > _now()]

    result = {
        'context': {
            'mode': 'process_bound',
            'bound_org_id': org_id,
            'source': context_source,
            'request_override': 'exact-match-only',
            'auth': auth_context,
            'permissions': _permission_snapshot(auth_context),
        },
        'runtime_core': runtime_core_snapshot(
            inst_ctx,
            additional_institutions_allowed=True,
            host_identity=host_identity,
            admission_registry=admission_registry,
            admission_management_mode=_admission_management_state(host_identity)['management_mode'],
            admission_mutation_enabled=_admission_management_state(host_identity)['mutation_enabled'],
            admission_mutation_disabled_reason=_admission_management_state(host_identity)['mutation_disabled_reason'],
        ),
        'institution': {
            'id': org_id,
            'name': org.get('name', ''),
            'slug': org.get('slug', ''),
            'charter': org.get('charter', ''),
            'lifecycle_state': org.get('lifecycle_state', 'active'),
            'policy_defaults': org.get('policy_defaults', {}),
            'plan': org.get('plan', ''),
            'owner_id': org.get('owner_id', ''),
            'treasury_id': org.get('treasury_id'),
        } if org else None,
        'agents': agents,
        'authority': {
            'kill_switch': queue['kill_switch'],
            'pending_approvals': pending_approvals,
            'active_delegations': active_delegations,
            'sprint_lead': {'agent_id': lead_id, 'auth': lead_auth},
        },
        'treasury': snap,
        'court': {
            'open_violations': open_violations,
            'pending_appeals': pending_appeals,
            'total_violations': len(records['violations']),
            'total_appeals': len(records['appeals']),
        },
        'warrants': _warrant_summary(org_id),
        'commitments': _commitment_snapshot(org_id),
        'cases': _case_snapshot(org_id),
        'remediations': remediations,
        'timestamp': _now(),
    }
    result['runtime_core']['federation'] = _federation_snapshot(
        org_id,
        host_identity=host_identity,
        admission_registry=admission_registry,
    )

    if _ci_vertical_available:
        result['ci_vertical'] = _ci_vertical_status(reg, lead_id, org_id=org_id)

    if _phase_machine_available:
        try:
            phase_num, phase_info = current_phase(org_id)
            result['phase_machine'] = {
                'current_phase': phase_num,
                'name': phase_info['name'],
                'description': phase_info['description'],
                'next_phase': phase_info.get('next_phase'),
                'next_unlock': phase_info.get('next_unlock'),
                'checks': phase_info.get('checks', []),
            }
        except Exception:
            result['phase_machine'] = {'error': 'evaluation failed'}

    return result


def _ci_vertical_status(reg, lead_id, org_id=None):
    """Build CI vertical constitutional gate status."""
    phases, blocked_phases = _phase_gate_snapshot(reg, org_id=org_id)
    all_clear = all(p['clear'] for p in phases)

    return {
        'preflight': 'CLEAR' if (all_clear and not is_kill_switch_engaged(org_id=org_id)) else 'BLOCKED',
        'blocked_phases': blocked_phases,
        'phases': phases,
    }


# -- HTML Dashboard -----------------------------------------------------------

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Governed Workspace</title>
<style>
:root { --bg: #0a0a0f; --fg: #e0e0e0; --accent: #4fc3f7; --card: #151520;
        --border: #2a2a3a; --green: #4caf50; --gold: #ffd54f; --dim: #888;
        --red: #ef5350; --orange: #ff9800; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Inter', system-ui, sans-serif; background: var(--bg);
       color: var(--fg); line-height: 1.5; padding: 1.5rem; max-width: 1100px; margin: 0 auto; }
h1 { font-size: 1.5rem; color: #fff; margin-bottom: 0.5rem; }
h2 { font-size: 1.15rem; color: var(--accent); margin: 1.5rem 0 0.75rem;
     border-bottom: 1px solid var(--border); padding-bottom: 0.4rem; }
.subtitle { color: var(--dim); font-size: 0.9rem; margin-bottom: 1.5rem; }
.card { background: var(--card); border: 1px solid var(--border);
        border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
.grid3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.75rem; }
@media (max-width: 700px) { .grid2, .grid3 { grid-template-columns: 1fr; } }
.metric { text-align: center; }
.metric .val { font-size: 1.6rem; font-weight: 700; color: #fff; }
.metric .label { font-size: 0.8rem; color: var(--dim); }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
th { text-align: left; color: var(--dim); font-weight: 600; padding: 0.4rem 0.5rem;
     border-bottom: 1px solid var(--border); }
td { padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border); }
.tag { display: inline-block; padding: 2px 8px; border-radius: 4px;
       font-size: 0.75rem; font-weight: 700; }
.tag-live { background: #1a3a1a; color: var(--green); }
.tag-warn { background: #3a2a1a; color: var(--orange); }
.tag-crit { background: #3a1a1a; color: var(--red); }
.tag-off  { background: #1a2a1a; color: var(--green); }
.tag-on   { background: #3a1a1a; color: var(--red); }
.action-row { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 0.5rem 0; }
button { background: var(--accent); color: #000; border: none; padding: 6px 16px;
         border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 0.85rem; }
button:hover { background: #81d4fa; }
button.danger { background: var(--red); color: #fff; }
button.danger:hover { background: #c62828; }
button.secondary { background: transparent; border: 1px solid var(--border);
                   color: var(--fg); }
button.secondary:hover { border-color: var(--accent); color: var(--accent); }
input, select, textarea { background: #1a1a2a; border: 1px solid var(--border);
  color: var(--fg); padding: 6px 10px; border-radius: 4px; font-size: 0.85rem; }
textarea { width: 100%; min-height: 60px; font-family: inherit; }
.form-row { display: flex; gap: 0.5rem; align-items: center; margin: 0.4rem 0; flex-wrap: wrap; }
.form-row label { color: var(--dim); font-size: 0.8rem; min-width: 80px; }
.status-bar { display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 1rem;
              padding: 0.75rem 1rem; background: var(--card); border-radius: 8px;
              border: 1px solid var(--border); font-size: 0.85rem; }
.status-bar .item { display: flex; align-items: center; gap: 0.4rem; }
#toast { position: fixed; bottom: 1rem; right: 1rem; background: var(--card);
         border: 1px solid var(--accent); color: var(--fg); padding: 0.75rem 1.25rem;
         border-radius: 6px; display: none; z-index: 99; font-size: 0.9rem; }
.empty { color: var(--dim); font-style: italic; padding: 0.5rem 0; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
</style>
</head>
<body>

<h1>Governed Workspace</h1>
<p class="subtitle">Constitutional Operating System -- Five Primitives Demo</p>

<div class="status-bar" id="status-bar">Loading...</div>

<!-- PHASE MACHINE -->
<h2>Phase Machine</h2>
<div class="card" id="phase-card">Loading...</div>

<!-- INSTITUTION -->
<h2>Institution</h2>
<div class="card" id="inst-card">Loading...</div>

<!-- AGENTS -->
<h2>Agents</h2>
<div class="card" id="agents-card">Loading...</div>

<!-- AUTHORITY -->
<h2>Authority</h2>
<div id="authority-section">Loading...</div>

<!-- TREASURY -->
<h2>Treasury</h2>
<div class="card" id="treasury-card">Loading...</div>

<!-- COURT -->
<h2>Court</h2>
<div id="court-section">Loading...</div>

<!-- RECENT AUDIT -->
<h2>Recent Audit Trail</h2>
<div class="card" id="audit-card">Loading...</div>

<div id="toast"></div>

<script>
function toast(msg, ms) {
  var t = document.getElementById('toast');
  t.textContent = msg; t.style.display = 'block';
  setTimeout(function() { t.style.display = 'none'; }, ms || 3000);
}

function api(method, path, body) {
  var opts = { method: method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  return fetch(path, opts).then(function(r) { return r.json(); });
}

var currentContext = null;
function can(path) {
  var perms = currentContext && currentContext.permissions && currentContext.permissions.mutation_paths;
  return !!(perms && perms[path] && perms[path].allowed);
}
function requiredRole(path) {
  var perms = currentContext && currentContext.permissions && currentContext.permissions.mutation_paths;
  return perms && perms[path] ? perms[path].required_role : 'admin';
}

function riskTag(state) {
  if (state === 'critical') return '<span class="tag tag-crit">CRITICAL</span>';
  if (state === 'elevated') return '<span class="tag tag-warn">ELEVATED</span>';
  if (state === 'suspended') return '<span class="tag tag-crit">SUSPENDED</span>';
  return '<span class="tag tag-live">NOMINAL</span>';
}

function render(data) {
  currentContext = data.context || null;
  var ks = data.authority.kill_switch;
  var sb = '';
  sb += '<span class="item">Kill switch: ' + (ks.engaged
    ? '<span class="tag tag-on">ENGAGED</span>' : '<span class="tag tag-off">OFF</span>') + '</span>';
  sb += '<span class="item">Balance: <strong>$' + data.treasury.balance_usd.toFixed(2) + '</strong></span>';
  sb += '<span class="item">Runway: <strong>$' + data.treasury.runway_usd.toFixed(2) + '</strong></span>';
  sb += '<span class="item">Violations: <strong>' + data.court.open_violations.length + ' open</strong></span>';
  sb += '<span class="item">Approvals: <strong>' + data.authority.pending_approvals.length + ' pending</strong></span>';
  sb += '<span class="item">Lead: <strong>' + (data.authority.sprint_lead.agent_id || 'none') + '</strong></span>';
  if (data.context && data.context.auth && data.context.auth.actor_id) {
    sb += '<span class="item">Actor: <strong>' + data.context.auth.actor_id + '</strong> (' + (data.context.auth.role || 'unbound') + ')</span>';
  }
  document.getElementById('status-bar').innerHTML = sb;

  // Phase Machine
  var pm = data.phase_machine;
  if (pm && !pm.error) {
    var pc = '<div class="form-row"><label>Current Phase</label> <strong>Phase ' + pm.current_phase + ' &mdash; ' + pm.name + '</strong></div>';
    pc += '<div class="form-row"><label>Description</label> ' + pm.description + '</div>';
    if (pm.next_phase !== null && pm.next_phase !== undefined) {
      pc += '<div class="form-row"><label>Next Phase</label> Phase ' + pm.next_phase + '</div>';
      pc += '<div class="form-row"><label>Unlock needs</label> ' + (pm.next_unlock || '?') + '</div>';
    }
    if (pm.checks) {
      pc += '<table><tr><th>#</th><th>Phase</th><th>Status</th><th>Reason</th></tr>';
      pm.checks.forEach(function(c) {
        pc += '<tr><td>' + c.phase + '</td><td>' + c.name + '</td>';
        pc += '<td>' + (c.met ? '<span class="tag tag-live">PASS</span>' : '<span class="tag tag-warn">FAIL</span>') + '</td>';
        pc += '<td>' + c.reason + '</td></tr>';
      });
      pc += '</table>';
    }
    document.getElementById('phase-card').innerHTML = pc;
  } else {
    document.getElementById('phase-card').innerHTML = '<em>Phase machine not available</em>';
  }

  var inst = data.institution;
  if (inst) {
    var ic = '<div class="grid2"><div>';
    ic += '<div class="form-row"><label>Name</label> <strong>' + inst.name + '</strong></div>';
    ic += '<div class="form-row"><label>Lifecycle</label> <span class="tag tag-live">' + inst.lifecycle_state.toUpperCase() + '</span></div>';
    ic += '<div class="form-row"><label>Plan</label> ' + inst.plan + '</div>';
    ic += '</div><div>';
    ic += '<div class="form-row"><label>Charter</label></div>';
    ic += '<textarea id="charter-text" placeholder="Set institution charter...">' + (inst.charter || '') + '</textarea>';
    if (can('/api/institution/charter')) {
      ic += '<div class="action-row"><button onclick="setCharter()">Save Charter</button></div>';
    } else {
      ic += '<div class="form-row"><label></label><span style="color:var(--dim);font-size:0.8rem">Charter updates require ' + requiredRole('/api/institution/charter') + ' role.</span></div>';
    }
    ic += '</div></div>';
    document.getElementById('inst-card').innerHTML = ic;
  }

  var at = '<table><tr><th>Agent</th><th>Role</th><th>REP</th><th>AUTH</th><th>Risk</th><th>Lifecycle</th><th>Incidents</th><th>Restrictions</th><th>Lead</th></tr>';
  data.agents.forEach(function(a) {
    at += '<tr><td><strong>' + a.name + '</strong></td><td>' + a.role + '</td>';
    at += '<td>' + a.rep + '</td><td>' + a.auth + '</td>';
    at += '<td>' + riskTag(a.risk_state) + '</td>';
    at += '<td>' + a.lifecycle_state + '</td>';
    at += '<td>' + a.incident_count + '</td>';
    at += '<td>' + (a.restrictions.length ? a.restrictions.join(', ') : '-') + '</td>';
    at += '<td>' + (a.is_sprint_lead ? '<strong>LEAD</strong>' : '-') + '</td></tr>';
  });
  at += '</table>';
  document.getElementById('agents-card').innerHTML = at;

  var au = '<div class="card">';
  au += '<strong>Kill Switch</strong>: ' + (ks.engaged
    ? '<span class="tag tag-on">ENGAGED</span> by ' + ks.engaged_by + ' -- ' + ks.reason
      + (can('/api/authority/kill-switch') ? ' <button onclick="killSwitch(false)">Disengage</button>' : '')
    : '<span class="tag tag-off">OFF</span>' + (can('/api/authority/kill-switch') ? ' <button class="danger" onclick="killSwitch(true)">Engage Kill Switch</button>' : ' <span style="color:var(--dim);font-size:0.8rem">requires ' + requiredRole('/api/authority/kill-switch') + '</span>'));
  au += '</div>';
  au += '<div class="card"><strong>Pending Approvals</strong> (' + data.authority.pending_approvals.length + ')';
  if (data.authority.pending_approvals.length === 0) {
    au += '<div class="empty">No pending approvals</div>';
  }
  au += '</div>';
  document.getElementById('authority-section').innerHTML = au;

  var tr = data.treasury;
  var tc = '<div class="grid3">';
  tc += '<div class="metric"><div class="val">$' + tr.balance_usd.toFixed(2) + '</div><div class="label">Balance</div></div>';
  tc += '<div class="metric"><div class="val">$' + tr.runway_usd.toFixed(2) + '</div><div class="label">Runway</div></div>';
  tc += '<div class="metric"><div class="val">$' + tr.reserve_floor_usd.toFixed(2) + '</div><div class="label">Reserve Floor</div></div>';
  tc += '</div>';
  document.getElementById('treasury-card').innerHTML = tc;

  var co = '<div class="card"><strong>Open Violations</strong> (' + data.court.open_violations.length + ')';
  if (data.court.open_violations.length === 0) {
    co += '<div class="empty">No open violations</div>';
  }
  co += '</div>';
  document.getElementById('court-section').innerHTML = co;
}

function killSwitch(engage) {
  var reason = engage ? prompt('Reason for engaging kill switch:') : '';
  if (engage && !reason) return;
  api('POST', '/api/authority/kill-switch', { engage: engage, reason: reason })
    .then(function(r) { toast(r.message); refresh(); });
}

function setCharter() {
  if (!can('/api/institution/charter')) return toast('This action requires ' + requiredRole('/api/institution/charter') + ' role.');
  var text = document.getElementById('charter-text').value;
  api('POST', '/api/institution/charter', { text: text })
    .then(function(r) { toast(r.message); refresh(); });
}

function refresh() {
  api('GET', '/api/status').then(render).catch(function(e) {
    document.getElementById('status-bar').innerHTML = '<span style="color:var(--red)">Error loading: ' + e + '</span>';
  });
  api('GET', '/api/audit').then(function(data) {
    if (!data.events || data.events.length === 0) {
      document.getElementById('audit-card').innerHTML = '<div class="empty">No recent audit events</div>';
      return;
    }
    var at = '<table><tr><th>Time</th><th>Action</th><th>Agent</th><th>Outcome</th></tr>';
    data.events.slice(0, 20).forEach(function(e) {
      at += '<tr><td style="font-size:0.8rem">' + e.timestamp + '</td>';
      at += '<td>' + e.action + '</td><td>' + (e.agent_id || '-') + '</td>';
      at += '<td>' + e.outcome + '</td></tr>';
    });
    at += '</table>';
    document.getElementById('audit-card').innerHTML = at;
  }).catch(function(){});
}

refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>"""


# -- HTTP Request Handler -----------------------------------------------------

class WorkspaceHandler(BaseHTTPRequestHandler):

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _html(self, html):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode())

    def _unauthorized(self, is_api=True):
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Meridian Workspace"')
        if is_api:
            self.send_header('Content-Type', 'application/json')
        else:
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.end_headers()
        if is_api:
            self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
        else:
            self.wfile.write(b'Unauthorized')

    def _service_unavailable(self, message, is_api=True):
        self.send_response(503)
        if is_api:
            self.send_header('Content-Type', 'application/json')
        else:
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.end_headers()
        if is_api:
            self.wfile.write(json.dumps({'error': message}).encode())
        else:
            self.wfile.write(message.encode())

    def _is_authorized(self):
        header = self.headers.get('Authorization', '')
        # Bearer (session) auth — always available
        if header.startswith('Bearer '):
            token = header.split(' ', 1)[1].strip()
            return _session_authority.validate(token) is not None
        # Basic auth
        user, password, _credential_org_id, _credential_user_id = _load_workspace_credentials()
        if not user or not password:
            return False
        if not header.startswith('Basic '):
            return False
        try:
            decoded = base64.b64decode(header.split(' ', 1)[1]).decode('utf-8')
        except Exception:
            return False
        if ':' not in decoded:
            return False
        supplied_user, supplied_password = decoded.split(':', 1)
        return hmac.compare_digest(supplied_user, user) and hmac.compare_digest(supplied_password, password)

    def _require_auth(self, path):
        # Session validate is a passive introspection endpoint — the token is the proof.
        protected = (path == '/' or path.startswith('/workspace') or path.startswith('/api/')) \
            and path not in ('/api/session/validate', '/api/federation/manifest')
        if not protected:
            return True
        if self._is_authorized():
            return True
        user, password, _credential_org_id, _credential_user_id = _load_workspace_credentials()
        if not user or not password:
            if WORKSPACE_AUTH_REQUIRED:
                self._service_unavailable('Workspace auth is required but credentials are not configured',
                                          is_api=path.startswith('/api/'))
                return False
            return True
        self._unauthorized(is_api=path.startswith('/api/'))
        return False

    def _session_claims_from_request(self, expected_org_id=None):
        """Extract and validate session claims from a Bearer token."""
        header = self.headers.get('Authorization', '')
        if not header.startswith('Bearer '):
            return None
        token = header.split(' ', 1)[1].strip()
        return _session_authority.validate(token, expected_org_id=expected_org_id)

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def log_message(self, fmt, *args):
        pass  # Suppress default logging

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Meridian-Org-Id')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._require_auth(path):
            return
        try:
            inst_ctx = _resolve_workspace_context()
            org_id = inst_ctx.org_id
            org = inst_ctx.org
            context_source = inst_ctx.context_source
            request_context = _enforce_request_context(parsed, self.headers, org_id)
            session_claims = self._session_claims_from_request(expected_org_id=org_id)
            if session_claims:
                auth_context = _resolve_auth_context_from_session(session_claims, org_id)
            elif self.headers.get('Authorization', '').startswith('Bearer '):
                # Bearer was provided but invalid for this institution — never
                # fall back to credential auth silently.
                return self._json({
                    'error': 'Session token is not valid for this institution'
                }, 403)
            else:
                auth_context = _resolve_auth_context(org_id)
        except RuntimeError as e:
            return self._json({'error': str(e)}, 503)
        except ValueError as e:
            return self._json({'error': str(e)}, 400)

        if path == '/' or path == '/workspace':
            return self._html(DASHBOARD_HTML)
        elif path == '/api/status':
            return self._json(api_status(institution_context=inst_ctx))
        elif path == '/api/context':
            host_identity, admission_registry = _runtime_host_state(org_id)
            response = {
                **request_context,
                'auth': auth_context,
                'permissions': _permission_snapshot(auth_context),
                'institution': inst_ctx.to_dict(),
                'runtime_core': runtime_core_snapshot(
                    inst_ctx,
                    additional_institutions_allowed=True,
                    host_identity=host_identity,
                    admission_registry=admission_registry,
                    admission_management_mode=_admission_management_state(host_identity)['management_mode'],
                    admission_mutation_enabled=_admission_management_state(host_identity)['mutation_enabled'],
                    admission_mutation_disabled_reason=_admission_management_state(host_identity)['mutation_disabled_reason'],
                ),
            }
            response['runtime_core']['federation'] = _federation_snapshot(
                org_id,
                host_identity=host_identity,
                admission_registry=admission_registry,
            )
            return self._json(response)
        elif path == '/api/institution':
            return self._json(org or {})
        elif path == '/api/agents':
            reg = _scoped_registry(org_id)
            return self._json(list(reg['agents'].values()))
        elif path == '/api/authority':
            queue = _load_queue(org_id)
            lead_id, lead_auth = get_sprint_lead(org_id)
            return self._json({
                'kill_switch': queue['kill_switch'],
                'pending_approvals': list(queue['pending_approvals'].values()),
                'delegations': list(queue['delegations'].values()),
                'sprint_lead': {'agent_id': lead_id, 'auth': lead_auth},
            })
        elif path == '/api/treasury':
            return self._json(treasury_snapshot(org_id))
        elif path == '/api/treasury/wallets':
            return self._json(load_wallets(org_id))
        elif path == '/api/treasury/accounts':
            return self._json(load_treasury_accounts(org_id))
        elif path == '/api/treasury/maintainers':
            return self._json(load_maintainers(org_id))
        elif path == '/api/treasury/contributors':
            return self._json(load_contributors(org_id))
        elif path == '/api/treasury/proposals':
            return self._json(load_payout_proposals(org_id))
        elif path == '/api/treasury/funding-sources':
            return self._json(load_funding_sources(org_id))
        elif path == '/api/federation':
            host_identity, admission_registry = _runtime_host_state(org_id)
            return self._json(_federation_snapshot(
                org_id,
                host_identity=host_identity,
                admission_registry=admission_registry,
            ))
        elif path == '/api/federation/peers':
            host_identity, admission_registry = _runtime_host_state(org_id)
            return self._json(_federation_snapshot(
                org_id,
                host_identity=host_identity,
                admission_registry=admission_registry,
            ))
        elif path == '/api/federation/manifest':
            host_identity, admission_registry = _runtime_host_state(org_id)
            return self._json(_federation_manifest(
                inst_ctx,
                host_identity=host_identity,
                admission_registry=admission_registry,
            ))
        elif path == '/api/admission':
            host_identity, admission_registry = _runtime_host_state(org_id)
            return self._json(_admission_snapshot(
                org_id,
                host_identity=host_identity,
                admission_registry=admission_registry,
            ))
        elif path == '/api/runtimes':
            data = load_runtimes()
            contracts = check_all_contracts()
            runtimes = data.get('runtimes', {})
            # Embed contract check result into each runtime entry
            result = {}
            for rid, rt in runtimes.items():
                result[rid] = dict(rt)
                result[rid]['contract_check'] = contracts.get(rid, {})
            return self._json({
                'runtimes': result,
                'contract_requirements': data.get('contract_requirements', {}),
                'compliance_thresholds': data.get('compliance_thresholds', {}),
            })
        elif path.startswith('/api/runtimes/'):
            runtime_id = path[len('/api/runtimes/'):]
            rt = get_runtime(runtime_id)
            if rt is None:
                return self._json({'error': f'Runtime {runtime_id!r} not found'}, 404)
            from runtime_adapter import check_contract
            enriched = dict(rt)
            enriched['contract_check'] = check_contract(runtime_id)
            return self._json(enriched)
        elif path == '/api/session/validate':
            qs = parse_qs(parsed.query)
            token = None
            token_list = qs.get('token', [])
            if token_list:
                token = token_list[0]
            else:
                auth_header = self.headers.get('Authorization', '')
                if auth_header.startswith('Bearer '):
                    token = auth_header.split(' ', 1)[1].strip()
            if not token:
                return self._json({'error': 'No token provided — pass ?token= or Authorization: Bearer'}, 400)
            claims = _session_authority.validate(token, expected_org_id=org_id)
            if claims is None:
                return self._json({'valid': False})
            return self._json({'valid': True, 'claims': claims.to_dict()})
        elif path == '/api/court':
            records = _load_records(org_id)
            return self._json({
                'violations': list(records['violations'].values()),
                'appeals': list(records['appeals'].values()),
            })
        elif path == '/api/warrants':
            return self._json({
                'warrants': list_warrants(org_id),
                'summary': _warrant_summary(org_id),
            })
        elif path == '/api/commitments':
            return self._json(_commitment_snapshot(org_id))
        elif path == '/api/cases':
            return self._json(_case_snapshot(org_id))
        elif path == '/api/audit':
            events = tail_events(30, org_id=org_id)
            events.reverse()
            return self._json({'events': events})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == '/api/federation/receive':
            try:
                inst_ctx = _resolve_workspace_context()
                body = self._read_body()
                envelope = (body.get('envelope') or '').strip()
                if not envelope:
                    return self._json({'error': 'Federation envelope is required'}, 400)
                claims, federation_state = _accept_federation_request(
                    inst_ctx.org_id,
                    envelope,
                    payload=body.get('payload'),
                )
                receipt = _federation_receipt(
                    inst_ctx.org_id,
                    federation_state.get('host_id', ''),
                    claims,
                )
                log_event(
                    inst_ctx.org_id,
                    claims.actor_id or f'peer:{claims.source_host_id}',
                    'federation_envelope_received',
                    resource=claims.message_type,
                    outcome='accepted',
                    actor_type=claims.actor_type or 'service',
                    details={
                        'envelope_id': claims.envelope_id,
                        'source_host_id': claims.source_host_id,
                        'source_institution_id': claims.source_institution_id,
                        'target_host_id': claims.target_host_id,
                        'target_institution_id': claims.target_institution_id,
                        'nonce': claims.nonce,
                        'boundary_name': claims.boundary_name,
                        'warrant_id': claims.warrant_id,
                        'commitment_id': claims.commitment_id,
                        'receipt_id': receipt['receipt_id'],
                    },
                    session_id=claims.session_id or None,
                )
                return self._json({
                    'message': 'Federation envelope accepted',
                    'claims': claims.to_dict(),
                    'receipt': receipt,
                    'runtime_core': {
                        'federation': federation_state,
                    },
                })
            except FederationUnavailable as e:
                return self._json({'error': str(e)}, 503)
            except FederationReplayError as e:
                return self._json({'error': str(e)}, 409)
            except FederationValidationError as e:
                return self._json({'error': str(e)}, 403)
            except RuntimeError as e:
                return self._json({'error': str(e)}, 503)
            except ValueError as e:
                return self._json({'error': str(e)}, 400)

        if not self._require_auth(path):
            return
        try:
            inst_ctx = _resolve_workspace_context()
            org_id = inst_ctx.org_id
            _enforce_request_context(parsed, self.headers, org_id)
            session_claims = self._session_claims_from_request(expected_org_id=org_id)
            if session_claims:
                auth_context = _resolve_auth_context_from_session(session_claims, org_id)
            elif self.headers.get('Authorization', '').startswith('Bearer '):
                return self._json({
                    'error': 'Session token is not valid for this institution'
                }, 403)
            else:
                auth_context = _resolve_auth_context(org_id)
            _enforce_mutation_authorization(auth_context, org_id, path)
        except RuntimeError as e:
            return self._json({'error': str(e)}, 503)
        except ValueError as e:
            return self._json({'error': str(e)}, 400)
        except PermissionError as e:
            return self._json({'error': str(e)}, 403)

        try:
            body = self._read_body()
        except Exception:
            return self._json({'error': 'Invalid JSON'}, 400)

        by = auth_context.get('actor_id') or 'owner'  # server-enforced — never trust client-supplied actor identity
        _sid = auth_context.get('session_id')  # session traceability for audit

        try:
            if path == '/api/authority/kill-switch':
                if body.get('engage'):
                    engage_kill_switch(by, body.get('reason', ''), org_id=org_id)
                    log_event(org_id, by, 'kill_switch_engaged', outcome='success',
                              details={'by': by, 'reason': body.get('reason')},
                              session_id=_sid)
                    return self._json({'message': 'Kill switch ENGAGED'})
                else:
                    disengage_kill_switch(by, org_id=org_id)
                    log_event(org_id, by, 'kill_switch_disengaged', outcome='success',
                              details={'by': by}, session_id=_sid)
                    return self._json({'message': 'Kill switch disengaged'})

            elif path == '/api/authority/approve':
                decision = body['decision']
                decide_approval(body['approval_id'], decision,
                               by, body.get('reason', ''), org_id=org_id)
                log_event(org_id, by, 'approval_decided', resource=body['approval_id'],
                          outcome='success', details={'decision': decision, 'reason': body.get('reason', '')},
                          session_id=_sid)
                return self._json({'message': f'Approval {body["approval_id"]}: {decision}'})

            elif path == '/api/authority/request':
                aid = request_approval(body['agent'], body['action'],
                                       body['resource'], body.get('cost', 0), org_id=org_id)
                return self._json({'message': f'Approval requested: {aid}', 'approval_id': aid})

            elif path == '/api/authority/delegate':
                scopes = [s.strip() for s in body['scopes'].split(',') if s.strip()]
                did = delegate(body['from'], body['to'], scopes, body.get('hours', 24), org_id=org_id)
                return self._json({'message': f'Delegation created: {did}', 'delegation_id': did})

            elif path == '/api/authority/revoke':
                revoke_delegation(body['delegation_id'], org_id=org_id)
                log_event(org_id, by, 'delegation_revoked', resource=body['delegation_id'],
                          outcome='success', session_id=_sid)
                return self._json({'message': f'Delegation revoked: {body["delegation_id"]}'})

            elif path == '/api/court/file':
                vid = file_violation(body['agent'], org_id, body['type'],
                                     body['severity'], body['evidence'],
                                     body.get('policy_ref', ''))
                log_event(org_id, by, 'violation_filed', resource=vid,
                          outcome='success',
                          details={'agent': body['agent'], 'type': body['type'], 'severity': body['severity']},
                          session_id=_sid)
                return self._json({'message': f'Violation filed: {vid}', 'violation_id': vid})

            elif path == '/api/court/resolve':
                resolve_violation(body['violation_id'], body['note'], org_id=org_id)
                log_event(org_id, by, 'violation_resolved', resource=body['violation_id'],
                          outcome='success', details={'note': body['note']},
                          session_id=_sid)
                return self._json({'message': f'Violation resolved: {body["violation_id"]}'})

            elif path == '/api/court/appeal':
                aid = file_appeal(body['violation_id'], body['agent'], body['grounds'], org_id=org_id)
                return self._json({'message': f'Appeal filed: {aid}', 'appeal_id': aid})

            elif path == '/api/court/decide-appeal':
                decide_appeal(body['appeal_id'], body['decision'], by, org_id=org_id)
                log_event(org_id, by, 'appeal_decided', resource=body['appeal_id'],
                          outcome='success', details={'decision': body['decision']},
                          session_id=_sid)
                return self._json({'message': f'Appeal {body["appeal_id"]}: {body["decision"]}'})

            elif path == '/api/court/auto-review':
                vids = auto_review(org_id=org_id)
                log_event(org_id, by, 'court_auto_review', outcome='success',
                          details={'violations': vids, 'count': len(vids)},
                          session_id=_sid)
                return self._json({'message': f'Auto-review: {len(vids)} violation(s) created',
                                   'violations': vids})

            elif path == '/api/court/remediate':
                lifted = remediate(body['agent_id'], by,
                                   body.get('note', ''), org_id=org_id)
                log_event(org_id, by, 'court_remediation', resource=body['agent_id'],
                          outcome='success', details={'lifted': lifted, 'note': body.get('note', '')},
                          session_id=_sid)
                return self._json({'message': f'Remediation complete: lifted {lifted}',
                                   'lifted': lifted})

            elif path == '/api/treasury/contribute':
                result = contribute_owner_capital(body['amount'], body.get('note', ''),
                                                  by, org_id=org_id)
                log_event(org_id, by, 'treasury_owner_capital', outcome='success',
                          details=result, session_id=_sid)
                return self._json({
                    'message': f'Owner capital recorded: +${result["amount_usd"]:.2f}',
                    'snapshot': treasury_snapshot(org_id),
                })

            elif path == '/api/treasury/reserve-floor':
                result = set_reserve_floor_policy(body['amount'], body.get('note', ''),
                                                  by, org_id=org_id)
                log_event(org_id, by, 'treasury_reserve_floor_updated',
                          outcome='success', details=result, session_id=_sid)
                return self._json({
                    'message': 'Reserve floor updated',
                    'snapshot': treasury_snapshot(org_id),
                })

            elif path == '/api/session/issue':
                user_id = auth_context.get('user_id')
                role = auth_context.get('role')
                if not user_id or not role:
                    return self._json({
                        'error': 'Cannot issue session: actor is not a member of this institution'
                    }, 403)
                ttl = body.get('ttl_seconds')
                token = _session_authority.issue(org_id, user_id, role, ttl_seconds=ttl)
                claims = _session_authority.validate(token)
                log_event(org_id, by, 'session_issued', outcome='success',
                          details={'session_id': claims.session_id,
                                   'user_id': user_id, 'role': role},
                          session_id=_sid)
                return self._json({
                    'token': token,
                    'session_id': claims.session_id,
                    'org_id': org_id,
                    'user_id': user_id,
                    'role': role,
                    'expires_at': claims.expires_at,
                })

            elif path == '/api/session/revoke':
                session_id = body.get('session_id')
                if not session_id:
                    return self._json({'error': 'session_id is required'}, 400)
                _session_authority.revoke(session_id)
                log_event(org_id, by, 'session_revoked', outcome='success',
                          details={'session_id': session_id},
                          session_id=_sid)
                return self._json({'message': f'Session revoked: {session_id}'})

            elif path == '/api/warrants/issue':
                action_class = (body.get('action_class') or '').strip()
                boundary_name = (body.get('boundary_name') or '').strip()
                if not action_class:
                    return self._json({'error': 'action_class is required'}, 400)
                if not boundary_name:
                    return self._json({'error': 'boundary_name is required'}, 400)
                warrant = issue_warrant(
                    org_id,
                    action_class,
                    boundary_name,
                    by,
                    session_id=_sid or '',
                    request_payload=body.get('request_payload'),
                    risk_class=(body.get('risk_class') or 'moderate').strip(),
                    evidence_refs=body.get('evidence_refs'),
                    policy_refs=body.get('policy_refs'),
                    ttl_seconds=body.get('ttl_seconds'),
                    auto_issue=bool(body.get('auto_issue')),
                    note=body.get('note', ''),
                )
                log_event(org_id, by, 'warrant_issued', outcome='success',
                          resource=warrant['warrant_id'],
                          details={
                              'action_class': warrant['action_class'],
                              'boundary_name': warrant['boundary_name'],
                              'court_review_state': warrant['court_review_state'],
                          },
                          session_id=_sid)
                return self._json({
                    'message': f"Warrant issued: {warrant['warrant_id']}",
                    'warrant': warrant,
                })

            elif path in ('/api/warrants/approve', '/api/warrants/stay', '/api/warrants/revoke'):
                warrant_id = (body.get('warrant_id') or '').strip()
                if not warrant_id:
                    return self._json({'error': 'warrant_id is required'}, 400)
                decision = path.rsplit('/', 1)[-1]
                decision_past = {
                    'approve': 'approved',
                    'stay': 'stayed',
                    'revoke': 'revoked',
                }
                warrant = review_warrant(
                    warrant_id,
                    decision,
                    by,
                    org_id=org_id,
                    note=body.get('note', ''),
                )
                log_event(org_id, by, f'warrant_{decision}', outcome='success',
                          resource=warrant_id,
                          details={'court_review_state': warrant['court_review_state']},
                          session_id=_sid)
                return self._json({
                    'message': f"Warrant {decision_past[decision]}: {warrant_id}",
                    'warrant': warrant,
                })

            elif path == '/api/commitments/propose':
                target_host_id = (body.get('target_host_id') or '').strip()
                target_org_id = (
                    body.get('target_institution_id')
                    or body.get('target_org_id')
                    or ''
                ).strip()
                summary = (body.get('summary') or body.get('commitment_type') or '').strip()
                if not target_host_id:
                    return self._json({'error': 'target_host_id is required'}, 400)
                if not target_org_id:
                    return self._json({'error': 'target_institution_id is required'}, 400)
                if not summary:
                    return self._json({'error': 'summary is required'}, 400)
                commitment = propose_commitment(
                    org_id,
                    target_host_id,
                    target_org_id,
                    summary,
                    by,
                    terms_payload=body.get('terms_payload'),
                    warrant_id=(body.get('warrant_id') or '').strip(),
                    note=body.get('note', ''),
                    metadata=body.get('metadata'),
                )
                log_event(
                    org_id,
                    by,
                    'commitment_proposed',
                    outcome='success',
                    resource=commitment['commitment_id'],
                    details={
                        'target_host_id': target_host_id,
                        'target_institution_id': target_org_id,
                        'summary': summary,
                        'warrant_id': commitment.get('warrant_id', ''),
                    },
                    session_id=_sid,
                )
                return self._json({
                    'message': f"Commitment proposed: {commitment['commitment_id']}",
                    'commitment': commitment,
                    'summary': _commitment_summary(org_id),
                })

            elif path in (
                '/api/commitments/accept',
                '/api/commitments/reject',
                '/api/commitments/breach',
                '/api/commitments/settle',
            ):
                commitment_id = (body.get('commitment_id') or '').strip()
                if not commitment_id:
                    return self._json({'error': 'commitment_id is required'}, 400)
                decision = path.rsplit('/', 1)[-1]
                if decision == 'settle':
                    case_record, warrant = _maybe_block_commitment_settlement(
                        commitment_id,
                        by,
                        org_id=org_id,
                        session_id=_sid,
                        note=body.get('note', ''),
                    )
                    if case_record:
                        return self._json({
                            'error': (
                                f"Commitment '{commitment_id}' cannot settle while case "
                                f"'{case_record.get('case_id', '')}' is {case_record.get('status', '')}"
                            ),
                            'case': case_record,
                            'warrant': warrant,
                            'summary': _commitment_summary(org_id),
                        }, 409)
                decision_past = {
                    'accept': 'accepted',
                    'reject': 'rejected',
                    'breach': 'breached',
                    'settle': 'settled',
                }
                event_name = {
                    'accept': 'commitment_accepted',
                    'reject': 'commitment_rejected',
                    'breach': 'commitment_breached',
                    'settle': 'commitment_settled',
                }[decision]
                commitment = {
                    'accept': accept_commitment,
                    'reject': reject_commitment,
                    'breach': breach_commitment,
                    'settle': settle_commitment,
                }[decision](
                    commitment_id,
                    by,
                    org_id=org_id,
                    note=body.get('note', ''),
                )
                log_event(
                    org_id,
                    by,
                    event_name,
                    outcome='success',
                    resource=commitment_id,
                    details={'status': commitment['status']},
                    session_id=_sid,
                )
                case_record = None
                warrant = None
                if decision == 'breach' and body.get('open_case', True):
                    case_record, created = _maybe_open_case_for_commitment_breach(
                        commitment,
                        by,
                        org_id=org_id,
                        note=body.get('case_note') or body.get('note', ''),
                    )
                    if created:
                        log_event(
                            org_id,
                            by,
                            'case_opened',
                            outcome='success',
                            resource=case_record['case_id'],
                            details={
                                'claim_type': case_record['claim_type'],
                                'linked_commitment_id': commitment_id,
                                'linked_warrant_id': case_record.get('linked_warrant_id', ''),
                            },
                            session_id=_sid,
                        )
                    warrant = _maybe_stay_warrant_for_case(
                        case_record,
                        by,
                        org_id=org_id,
                        session_id=_sid,
                        note=body.get('case_note') or body.get('note', ''),
                    )
                return self._json({
                    'message': f"Commitment {decision_past[decision]}: {commitment_id}",
                    'commitment': commitment,
                    'summary': _commitment_summary(org_id),
                    'case': case_record,
                    'warrant': warrant,
                })

            elif path == '/api/cases/open':
                claim_type = (body.get('claim_type') or '').strip()
                if not claim_type:
                    return self._json({'error': 'claim_type is required'}, 400)
                case_record = open_case(
                    org_id,
                    claim_type,
                    by,
                    target_host_id=(body.get('target_host_id') or '').strip(),
                    target_institution_id=(
                        body.get('target_institution_id')
                        or body.get('target_org_id')
                        or ''
                    ).strip(),
                    linked_commitment_id=(body.get('linked_commitment_id') or '').strip(),
                    linked_warrant_id=(body.get('linked_warrant_id') or '').strip(),
                    evidence_refs=body.get('evidence_refs') or [],
                    note=body.get('note', ''),
                    metadata=body.get('metadata'),
                )
                log_event(
                    org_id,
                    by,
                    'case_opened',
                    outcome='success',
                    resource=case_record['case_id'],
                    details={
                        'claim_type': claim_type,
                        'linked_commitment_id': case_record.get('linked_commitment_id', ''),
                        'linked_warrant_id': case_record.get('linked_warrant_id', ''),
                    },
                    session_id=_sid,
                )
                federation_peer = _maybe_suspend_peer_for_case(
                    case_record,
                    by,
                    org_id=org_id,
                    session_id=_sid,
                )
                warrant = _maybe_stay_warrant_for_case(
                    case_record,
                    by,
                    org_id=org_id,
                    session_id=_sid,
                    note=body.get('note', ''),
                )
                return self._json({
                    'message': f"Case opened: {case_record['case_id']}",
                    'case': case_record,
                    'summary': _case_snapshot(org_id),
                    'federation_peer': federation_peer,
                    'warrant': warrant,
                })

            elif path in ('/api/cases/stay', '/api/cases/resolve'):
                case_id = (body.get('case_id') or '').strip()
                if not case_id:
                    return self._json({'error': 'case_id is required'}, 400)
                decision = path.rsplit('/', 1)[-1]
                event_name = {
                    'stay': 'case_stayed',
                    'resolve': 'case_resolved',
                }[decision]
                case_record = {
                    'stay': stay_case,
                    'resolve': resolve_case,
                }[decision](
                    case_id,
                    by,
                    org_id=org_id,
                    note=body.get('note', ''),
                )
                log_event(
                    org_id,
                    by,
                    event_name,
                    outcome='success',
                    resource=case_id,
                    details={'status': case_record['status']},
                    session_id=_sid,
                )
                federation_peer = None
                warrant = None
                if decision == 'stay':
                    federation_peer = _maybe_suspend_peer_for_case(
                        case_record,
                        by,
                        org_id=org_id,
                        session_id=_sid,
                    )
                    warrant = _maybe_stay_warrant_for_case(
                        case_record,
                        by,
                        org_id=org_id,
                        session_id=_sid,
                        note=body.get('note', ''),
                    )
                return self._json({
                    'message': f"Case {case_record['status']}: {case_id}",
                    'case': case_record,
                    'summary': _case_snapshot(org_id),
                    'federation_peer': federation_peer,
                    'warrant': warrant,
                })

            elif path == '/api/federation/send':
                target_host_id = (body.get('target_host_id') or '').strip()
                target_org_id = (body.get('target_org_id') or '').strip()
                message_type = (body.get('message_type') or '').strip()
                if not target_host_id:
                    return self._json({'error': 'target_host_id is required'}, 400)
                if not target_org_id:
                    return self._json({'error': 'target_org_id is required'}, 400)
                if not message_type:
                    return self._json({'error': 'message_type is required'}, 400)
                try:
                    delivery, federation_state = _deliver_federation_envelope(
                        org_id,
                        target_host_id,
                        target_org_id,
                        message_type,
                        payload=body.get('payload'),
                        actor_type='user',
                        actor_id=by,
                        session_id=_sid or '',
                        warrant_id=(body.get('warrant_id') or '').strip(),
                        commitment_id=(body.get('commitment_id') or '').strip(),
                        ttl_seconds=body.get('ttl_seconds'),
                    )
                except FederationUnavailable as e:
                    return self._json({'error': str(e)}, 503)
                except PermissionError as e:
                    case_record = getattr(e, 'case_record', None)
                    if case_record:
                        return self._json({
                            'error': str(e),
                            'case': case_record,
                            'federation_peer': getattr(e, 'federation_peer', None),
                            'warrant': getattr(e, 'warrant', None),
                        }, 409)
                    return self._json({'error': str(e)}, 403)
                except FederationDeliveryError as e:
                    return self._json({
                        'error': str(e),
                        'peer_host_id': e.peer_host_id,
                        'claims': _federation_claims_dict(e.claims),
                        'case': getattr(e, 'case_record', None),
                        'federation_peer': getattr(e, 'federation_peer', None),
                        'warrant': getattr(e, 'warrant', None),
                    }, 502)
                return self._json({
                    'message': 'Federation envelope delivered',
                    'delivery': delivery,
                    'runtime_core': {
                        'federation': federation_state,
                    },
                })

            elif path in (
                '/api/federation/peers/upsert',
                '/api/federation/peers/refresh',
                '/api/federation/peers/suspend',
                '/api/federation/peers/revoke',
            ):
                action = path.rsplit('/', 1)[-1]
                peer_host_id = (body.get('peer_host_id') or body.get('host_id') or '').strip()
                snapshot = _mutate_federation_peer(org_id, action, body)
                peer_record = next(
                    (
                        peer for peer in snapshot.get('peers', [])
                        if peer.get('host_id') == peer_host_id
                    ),
                    None,
                )
                log_event(
                    org_id,
                    by,
                    f'federation_peer_{action}',
                    resource=peer_host_id,
                    outcome='success',
                    details={
                        'peer_host_id': peer_host_id,
                        'host_id': snapshot['host_id'],
                        'management_mode': snapshot['management_mode'],
                        'trust_state': (peer_record or {}).get('trust_state', ''),
                        'last_refreshed_at': (peer_record or {}).get('last_refreshed_at', ''),
                        'manifest_version': (
                            ((peer_record or {}).get('capability_snapshot') or {}).get('manifest_version')
                        ),
                    },
                    session_id=_sid,
                )
                return self._json({
                    'message': f'Federation peer {action} applied to {peer_host_id}',
                    'federation': snapshot,
                })

            elif path in ('/api/admission/admit', '/api/admission/suspend', '/api/admission/revoke'):
                action = path.rsplit('/', 1)[-1]
                target_org_id = body.get('org_id')
                snapshot = _mutate_admission(org_id, action, target_org_id)
                log_event(
                    org_id,
                    by,
                    f'admission_{action}',
                    resource=target_org_id or '',
                    outcome='success',
                    details={
                        'target_org_id': target_org_id,
                        'host_id': snapshot['host_id'],
                        'host_role': snapshot['host_role'],
                        'status': snapshot['institutions'][target_org_id]['status'],
                    },
                    session_id=_sid,
                )
                return self._json({
                    'message': f'Admission {action} applied to {target_org_id}',
                    'admission': snapshot,
                })

            elif path == '/api/institution/charter':
                set_charter(org_id, body['text'])
                log_event(org_id, by, 'charter_set', outcome='success',
                          session_id=_sid)
                return self._json({'message': 'Charter saved'})

            elif path == '/api/institution/lifecycle':
                org_transition_lifecycle(org_id, body['state'])
                log_event(org_id, by, 'lifecycle_transitioned', outcome='success',
                          details={'state': body['state']}, session_id=_sid)
                return self._json({'message': f'Lifecycle transitioned to {body["state"]}'})

            else:
                return self._json({'error': 'Not found'}, 404)

        except PermissionError as e:
            return self._json({'error': str(e)}, 403)
        except LookupError as e:
            return self._json({'error': str(e)}, 404)
        except Exception as e:
            return self._json({'error': str(e)}, 400)


def main():
    global WORKSPACE_ORG_ID
    parser = argparse.ArgumentParser(description='Governed Workspace server')
    parser.add_argument('--port', type=int, default=18901)
    parser.add_argument('--org-id', default=None,
                        help='Bind this workspace process to one institution. No request-level org routing is exposed.')
    args = parser.parse_args()
    if args.org_id:
        WORKSPACE_ORG_ID = args.org_id

    inst_ctx = _resolve_workspace_context()
    org_id, org, context_source = inst_ctx.org_id, inst_ctx.org, inst_ctx.context_source

    server = HTTPServer(('127.0.0.1', args.port), WorkspaceHandler)
    print(f'Governed Workspace running at http://127.0.0.1:{args.port}')
    print(f'Dashboard: http://127.0.0.1:{args.port}/')
    print(f'API:       http://127.0.0.1:{args.port}/api/status')
    print(f'Bound institution: {org.get("slug", "") if org else ""} ({org_id}) via {context_source}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutdown.')
        server.server_close()


if __name__ == '__main__':
    main()
