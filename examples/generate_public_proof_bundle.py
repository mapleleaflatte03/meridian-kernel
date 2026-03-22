#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import sys
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone


ROOT_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
TESTS_DIR = os.path.join(ROOT_DIR, 'kernel', 'tests')
sys.path.insert(0, TESTS_DIR)

from test_openclaw_federation_proof import (  # noqa: E402
    _run_openclaw_reference_adapter_federation_proof,
)
from test_three_host_federation_proof import _run_three_host_federation_proof  # noqa: E402


def _public_manifest_receipt(payload):
    host_identity = payload.get('host_identity', {}) or {}
    institution_context = payload.get('institution_context', {}) or {}
    admission = payload.get('admission', {}) or {}
    service_registry = payload.get('service_registry', {}) or {}
    federation_gateway = service_registry.get('federation_gateway', {}) or {}
    witness_archive = payload.get('witness_archive', {}) or {}
    federation = payload.get('federation', {}) or {}
    return {
        'manifest_version': payload.get('manifest_version'),
        'generated_at': payload.get('generated_at'),
        'host_identity': {
            'host_id': host_identity.get('host_id', ''),
            'label': host_identity.get('label', ''),
            'role': host_identity.get('role', ''),
            'federation_enabled': bool(host_identity.get('federation_enabled')),
            'peer_transport': host_identity.get('peer_transport', ''),
        },
        'institution_context': {
            'org_id': institution_context.get('org_id', ''),
            'institution_slug': institution_context.get('institution_slug', ''),
            'boundary_name': institution_context.get('boundary_name', ''),
            'identity_model': institution_context.get('identity_model', ''),
            'boundary_scope': institution_context.get('boundary_scope', ''),
        },
        'admission': {
            'mode': admission.get('mode', ''),
            'bound_org_id': admission.get('bound_org_id', ''),
            'admitted_org_ids': admission.get('admitted_org_ids', []),
            'additional_institutions_allowed': bool(admission.get('additional_institutions_allowed')),
            'shared_request_routing': bool(admission.get('shared_request_routing')),
            'management_mode': admission.get('management_mode', ''),
            'mutation_enabled': bool(admission.get('mutation_enabled')),
            'mutation_disabled_reason': admission.get('mutation_disabled_reason', ''),
        },
        'service_registry': {
            'federation_gateway': {
                'name': federation_gateway.get('name', ''),
                'identity_model': federation_gateway.get('identity_model', ''),
                'scope': federation_gateway.get('scope', ''),
                'supports_institution_routing': bool(federation_gateway.get('supports_institution_routing')),
                'supports_federation': bool(federation_gateway.get('supports_federation')),
                'requires_admitted_institution': bool(federation_gateway.get('requires_admitted_institution')),
                'requires_warrant': bool(federation_gateway.get('requires_warrant')),
                'required_warrant_actions': federation_gateway.get('required_warrant_actions', {}),
            },
        },
        'witness_archive': {
            'archive_enabled': bool(witness_archive.get('archive_enabled')),
            'archive_disabled_reason': witness_archive.get('archive_disabled_reason', ''),
            'management_mode': witness_archive.get('management_mode', ''),
        },
        'federation': {
            'enabled': bool(federation.get('enabled')),
            'disabled_reason': federation.get('disabled_reason', ''),
            'boundary_name': federation.get('boundary_name', ''),
            'identity_model': federation.get('identity_model', ''),
            'peer_transport': federation.get('peer_transport', ''),
            'send_enabled': bool(federation.get('send_enabled')),
        },
    }


def _fetch_live_manifest(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            raw = response.read()
            payload = json.loads(raw.decode('utf-8'))
            status = getattr(response, 'status', 200)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return {
            'included': False,
            'attempted': True,
            'route': url,
            'error': str(exc),
        }
    return {
        'included': True,
        'attempted': True,
        'route': url,
        'http_status': status,
        'fetched_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'body_sha256': hashlib.sha256(raw).hexdigest(),
        'manifest': _public_manifest_receipt(payload),
    }


def _derive_sibling_url(url, old_suffix, new_suffix):
    if not url or not url.endswith(old_suffix):
        return ''
    return url[:-len(old_suffix)] + new_suffix


def _fetch_live_runtime_proof(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            raw = response.read()
            payload = json.loads(raw.decode('utf-8'))
            status = getattr(response, 'status', 200)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return {
            'included': False,
            'attempted': True,
            'route': url,
            'error': str(exc),
        }
    return {
        'included': True,
        'attempted': True,
        'route': url,
        'http_status': status,
        'fetched_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'body_sha256': hashlib.sha256(raw).hexdigest(),
        'receipt': {
            'runtime_id': payload.get('runtime_id', ''),
            'proof_type': payload.get('proof_type', ''),
            'bound_org_id': payload.get('bound_org_id', ''),
            'deployment_truth': payload.get('deployment_truth', {}),
            'health': payload.get('health', {}),
            'pong_probe': payload.get('pong_probe', {}),
            'mapping': payload.get('mapping', {}),
        },
    }


def _summarize_openclaw_reference_proof(proof):
    return {
        'runtime_id': proof.get('runtime_id'),
        'adapter_kind': proof.get('adapter_kind'),
        'scope': proof.get('scope'),
        'action_gate': {
            'allowed': bool((proof.get('action_gate') or {}).get('allowed')),
            'stage': (proof.get('action_gate') or {}).get('stage', ''),
        },
        'commitment_id': proof.get('commitment_id', ''),
        'delivery': {
            'proposal_message_type': (((proof.get('proposal') or {}).get('body') or {}).get('delivery') or {}).get('claims', {}).get('message_type', ''),
            'acceptance_message_type': (((proof.get('acceptance') or {}).get('body') or {}).get('delivery') or {}).get('claims', {}).get('message_type', ''),
            'execution_message_type': (((proof.get('execution') or {}).get('body') or {}).get('delivery') or {}).get('claims', {}).get('message_type', ''),
            'execution_receiver_host_id': (((proof.get('execution') or {}).get('body') or {}).get('delivery') or {}).get('receipt', {}).get('receiver_host_id', ''),
            'proposal_witness_archive_created': (((proof.get('proposal') or {}).get('body') or {}).get('delivery') or {}).get('witness_archive', {}).get('created', 0),
            'acceptance_witness_archive_created': (((proof.get('acceptance') or {}).get('body') or {}).get('delivery') or {}).get('witness_archive', {}).get('created', 0),
            'execution_witness_archive_created': (((proof.get('execution') or {}).get('body') or {}).get('delivery') or {}).get('witness_archive', {}).get('created', 0),
            'review_witness_archive_created': (((proof.get('review') or {}).get('body') or {}).get('court_notice') or {}).get('delivery', {}).get('witness_archive', {}).get('created', 0),
            'breach_witness_archive_created': (((proof.get('breach') or {}).get('body') or {}).get('delivery') or {}).get('witness_archive', {}).get('created', 0),
        },
        'post_action_record': {
            'cost_usd': (proof.get('post_action_record') or {}).get('cost_usd', 0.0),
            'outcome': (proof.get('post_action_record') or {}).get('outcome', ''),
        },
        'meter_event': {
            'org_id': (proof.get('meter') or {}).get('org_id', ''),
            'agent_id': (proof.get('meter') or {}).get('agent_id', ''),
            'metric': (proof.get('meter') or {}).get('metric', ''),
            'quantity': (proof.get('meter') or {}).get('quantity', 0.0),
            'unit': (proof.get('meter') or {}).get('unit', ''),
            'cost_usd': (proof.get('meter') or {}).get('cost_usd', 0.0),
        },
        'audit_event': {
            'action': (proof.get('audit') or {}).get('action', ''),
            'resource': (proof.get('audit') or {}).get('resource', ''),
            'outcome': (proof.get('audit') or {}).get('outcome', ''),
            'actor_type': (proof.get('audit') or {}).get('actor_type', ''),
        },
        'receiver_review': {
            'decision': (((proof.get('review') or {}).get('body') or {}).get('court_notice') or {}).get('court_notice', {}).get('decision', ''),
            'local_warrant_id': (((proof.get('jobs') or {}).get('body') or {}).get('jobs') or [{}])[0].get('local_warrant_id', ''),
        },
        'breach_processing': {
            'trust_state': ((((proof.get('breach') or {}).get('body') or {}).get('delivery') or {}).get('response') or {}).get('processing', {}).get('federation_peer', {}).get('trust_state', ''),
            'blocking_commitment_ids': ((proof.get('cases') or {}).get('body') or {}).get('blocking_commitment_ids', []),
            'blocked_peer_host_ids': ((proof.get('cases') or {}).get('body') or {}).get('blocked_peer_host_ids', []),
        },
        'witness_archive_summary': ((proof.get('witness_archive') or {}).get('body') or {}).get('summary', {}),
        'audit_markers': {
            'alpha_has_breach_notice_recorded': 'federation_commitment_breach_notice_recorded' in ((proof.get('audit_events') or {}).get('alpha_actions') or []),
            'beta_has_witness_archive_sent': 'federation_witness_archive_sent' in ((proof.get('audit_events') or {}).get('beta_actions') or []),
            'gamma_archive_count': (proof.get('audit_events') or {}).get('gamma_archive_count', 0),
        },
    }


def build_bundle(live_manifest_url=None, live_runtime_proof_url=None):
    try:
        three_host = {
            'passed': True,
            'skipped': False,
            'summary': _run_three_host_federation_proof(),
        }
    except unittest.SkipTest as exc:
        three_host = {
            'passed': False,
            'skipped': True,
            'reason': str(exc),
        }
    try:
        openclaw = {
            'passed': True,
            'skipped': False,
            'summary': _summarize_openclaw_reference_proof(
                _run_openclaw_reference_adapter_federation_proof()
            ),
        }
    except unittest.SkipTest as exc:
        openclaw = {
            'passed': False,
            'skipped': True,
            'reason': str(exc),
        }
    return {
        'proof_bundle_version': 3,
        'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'reference_scope': 'oss_kernel_reference',
        'three_host_federation': three_host,
        'openclaw_reference_adapter_federation': openclaw,
        'live_host_receipt': (
            _fetch_live_manifest(live_manifest_url)
            if live_manifest_url else
            {
                'included': False,
                'attempted': False,
                'route': '',
                'reason': 'no_live_manifest_url_supplied',
            }
        ),
        'live_runtime_receipt': (
            _fetch_live_runtime_proof(
                live_runtime_proof_url
                or _derive_sibling_url(live_manifest_url or '', '/api/federation/manifest', '/api/runtime-proof')
            )
            if (live_runtime_proof_url or live_manifest_url) else
            {
                'included': False,
                'attempted': False,
                'route': '',
                'reason': 'no_live_runtime_proof_url_supplied',
            }
        ),
        'not_live_proven': [
            'live multi-host federation between independent deployments',
            'live OpenClaw end-to-end hosted wiring',
            'live non-internal settlement execution',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description='Generate the Meridian public proof bundle.')
    parser.add_argument(
        '--output',
        default='-',
        help='Write JSON bundle to this path, or - for stdout',
    )
    parser.add_argument(
        '--live-manifest-url',
        default='',
        help='Optional public live federation manifest URL to embed as a host receipt',
    )
    parser.add_argument(
        '--live-runtime-proof-url',
        default='',
        help='Optional public live runtime-proof URL; defaults to a sibling of --live-manifest-url when omitted',
    )
    args = parser.parse_args()

    bundle = build_bundle(
        live_manifest_url=args.live_manifest_url or None,
        live_runtime_proof_url=args.live_runtime_proof_url or None,
    )
    raw = json.dumps(bundle, indent=2, sort_keys=True) + '\n'
    if args.output == '-':
        sys.stdout.write(raw)
        return
    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as handle:
        handle.write(raw)
    print(output_path)


if __name__ == '__main__':
    main()
