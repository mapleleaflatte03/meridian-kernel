#!/usr/bin/env python3
import base64
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error as urllib_error
from urllib import request as urllib_request

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
WORKSPACE = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)


def _now_stub():
    return '2026-03-22T00:00:00Z'


def _write_json(path, payload):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _seed_commitments(path, records):
    _write_json(
        path,
        {
            'commitments': {
                record['commitment_id']: record
                for record in records
            },
            'states': ['proposed', 'accepted', 'rejected', 'breached', 'settled'],
            'updatedAt': _now_stub(),
        },
    )


def _accepted_commitment_record(*, org_id, commitment_id, target_host_id,
                                target_institution_id, warrant_id=''):
    return {
        'commitment_id': commitment_id,
        'institution_id': org_id,
        'source_institution_id': org_id,
        'target_host_id': target_host_id,
        'target_institution_id': target_institution_id,
        'commitment_type': 'federated_delivery',
        'summary': 'Federated delivery settlement proof',
        'terms_hash': '',
        'terms_payload': {},
        'warrant_id': warrant_id,
        'state': 'accepted',
        'status': 'accepted',
        'proposed_by': f'{org_id}_owner',
        'proposed_at': _now_stub(),
        'updated_at': _now_stub(),
        'reviewed_by': f'{org_id}_owner',
        'reviewed_at': _now_stub(),
        'review_note': '',
        'accepted_by': f'{org_id}_owner',
        'accepted_at': _now_stub(),
        'rejected_by': '',
        'rejected_at': '',
        'breached_by': '',
        'settled_by': '',
        'delivery_refs': [],
        'settlement_refs': [],
        'last_delivery_at': '',
        'last_settlement_at': '',
        'breached_at': '',
        'settled_at': '',
        'note': '',
        'metadata': {},
    }


def _find_free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', 0))
        sock.listen(1)
        return sock.getsockname()[1]
    finally:
        sock.close()


def _auth_header(user, password):
    raw = f'{user}:{password}'.encode('utf-8')
    return 'Basic ' + base64.b64encode(raw).decode('ascii')


def _http_json(method, url, *, payload=None, headers=None):
    req = urllib_request.Request(
        url,
        data=(json.dumps(payload).encode('utf-8') if payload is not None else None),
        headers=headers or {},
        method=method,
    )
    try:
        with urllib_request.urlopen(req, timeout=10) as response:
            body = response.read().decode('utf-8')
            return response.status, (json.loads(body) if body else {})
    except urllib_error.HTTPError as exc:
        body = exc.read().decode('utf-8')
        return exc.code, (json.loads(body) if body else {})


def _seed_workspace_root(root_dir, *, org_id, user_id, host_id, port, signing_secret,
                         peer_entries=None):
    kernel_src = os.path.join(WORKSPACE, 'kernel')
    economy_src = os.path.join(WORKSPACE, 'economy')
    kernel_dst = os.path.join(root_dir, 'kernel')
    economy_dst = os.path.join(root_dir, 'economy')
    shutil.copytree(kernel_src, kernel_dst)
    shutil.copytree(economy_src, economy_dst)

    _write_json(
        os.path.join(kernel_dst, 'organizations.json'),
        {
            'organizations': {
                org_id: {
                    'id': org_id,
                    'name': f'{org_id} Institution',
                    'slug': org_id,
                    'owner_id': user_id,
                    'members': [
                        {
                            'user_id': user_id,
                            'role': 'owner',
                            'added_at': _now_stub(),
                        }
                    ],
                    'plan': 'enterprise',
                    'status': 'active',
                    'charter': '',
                    'policy_defaults': {},
                    'treasury_id': None,
                    'lifecycle_state': 'active',
                    'settings': {},
                    'created_at': _now_stub(),
                },
            },
            'updatedAt': _now_stub(),
        },
    )
    _write_json(
        os.path.join(kernel_dst, 'agent_registry.json'),
        {'agents': {}, 'updatedAt': _now_stub()},
    )
    _write_json(
        os.path.join(kernel_dst, 'host_identity.json'),
        {
            'host_id': host_id,
            'label': host_id,
            'role': 'institution_host',
            'federation_enabled': True,
            'peer_transport': 'https',
            'supported_boundaries': [
                'workspace',
                'cli',
                'federation_gateway',
            ],
            'settlement_adapters': [],
        },
    )
    _write_json(
        os.path.join(kernel_dst, 'institution_admissions.json'),
        {
            'host_id': host_id,
            'institutions': {
                org_id: {
                    'status': 'admitted',
                    'source': 'test_seed',
                    'updated_at': _now_stub(),
                    'admitted_at': _now_stub(),
                },
            },
            'updated_at': _now_stub(),
        },
    )
    _write_json(
        os.path.join(kernel_dst, 'federation_peers.json'),
        {
            'host_id': host_id,
            'peers': peer_entries or {},
            'updated_at': _now_stub(),
        },
    )
    open(os.path.join(kernel_dst, 'audit_log.jsonl'), 'w').close()
    open(os.path.join(kernel_dst, '.federation_replay'), 'w').close()

    env = os.environ.copy()
    env.update({
        'MERIDIAN_WORKSPACE_USER': f'{org_id}_user',
        'MERIDIAN_WORKSPACE_PASS': f'{org_id}_pass',
        'MERIDIAN_WORKSPACE_AUTH_ORG_ID': org_id,
        'MERIDIAN_WORKSPACE_USER_ID': user_id,
        'MERIDIAN_RUNTIME_HOST_IDENTITY_FILE': os.path.join(kernel_dst, 'host_identity.json'),
        'MERIDIAN_RUNTIME_ADMISSION_FILE': os.path.join(kernel_dst, 'institution_admissions.json'),
        'MERIDIAN_FEDERATION_PEERS_FILE': os.path.join(kernel_dst, 'federation_peers.json'),
        'MERIDIAN_FEDERATION_REPLAY_FILE': os.path.join(kernel_dst, '.federation_replay'),
        'MERIDIAN_FEDERATION_SIGNING_SECRET': signing_secret,
        'MERIDIAN_SESSION_SECRET': f'{host_id}-session-secret',
        'PYTHONUNBUFFERED': '1',
    })
    return {
        'root': root_dir,
        'kernel': kernel_dst,
        'economy': economy_dst,
        'port': port,
        'org_id': org_id,
        'user_id': user_id,
        'host_id': host_id,
        'workspace_py': os.path.join(kernel_dst, 'workspace.py'),
        'audit_log': os.path.join(kernel_dst, 'audit_log.jsonl'),
        'env': env,
        'auth_header': _auth_header(env['MERIDIAN_WORKSPACE_USER'], env['MERIDIAN_WORKSPACE_PASS']),
        'base_url': f'http://127.0.0.1:{port}',
    }


@contextlib.contextmanager
def _run_workspace(instance):
    proc = subprocess.Popen(
        [
            sys.executable,
            instance['workspace_py'],
            '--port',
            str(instance['port']),
            '--org-id',
            instance['org_id'],
        ],
        cwd=instance['root'],
        env=instance['env'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.time() + 10
        last_error = ''
        while time.time() < deadline:
            if proc.poll() is not None:
                output = proc.stdout.read() if proc.stdout else ''
                raise RuntimeError(
                    f"workspace {instance['host_id']} exited early with code {proc.returncode}: {output}"
                )
            try:
                status, body = _http_json('GET', instance['base_url'] + '/api/federation/manifest')
                if status == 200 and body.get('host_identity', {}).get('host_id') == instance['host_id']:
                    break
                last_error = f'status={status} body={body}'
            except Exception as exc:
                last_error = str(exc)
            time.sleep(0.1)
        else:
            raise RuntimeError(
                f"workspace {instance['host_id']} did not become ready: {last_error}"
            )
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()


def _issue_workspace_session(instance):
    status, body = _http_json(
        'POST',
        instance['base_url'] + '/api/session/issue',
        payload={},
        headers={
            'Authorization': instance['auth_header'],
            'Content-Type': 'application/json',
        },
    )
    if status != 200:
        raise AssertionError(f'failed issuing session for {instance["host_id"]}: {status} {body}')
    return body


def _issue_workspace_warrant(instance, token, request_payload, *, auto_issue=False,
                            review_decision='approve'):
    status, body = _http_json(
        'POST',
        instance['base_url'] + '/api/warrants/issue',
        payload={
            'action_class': 'federated_execution',
            'boundary_name': 'federation_gateway',
            'request_payload': request_payload,
            'risk_class': 'moderate',
            'auto_issue': auto_issue,
        },
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
    )
    if status != 200:
        raise AssertionError(f'failed issuing warrant for {instance["host_id"]}: {status} {body}')
    warrant = body['warrant']
    if not auto_issue and review_decision:
        status, body = _http_json(
            'POST',
            instance['base_url'] + f'/api/warrants/{review_decision}',
            payload={'warrant_id': warrant['warrant_id']},
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
        )
        if status != 200:
            raise AssertionError(
                f'failed {review_decision} warrant for {instance["host_id"]}: {status} {body}'
            )
        warrant = body['warrant']
    return warrant


class FederationTests(unittest.TestCase):
    def test_issue_and_validate_self_signed_envelope(self):
        from federation import FederationAuthority
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            role='control_host',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(host, signing_secret='alpha-secret')
        envelope = authority.issue(
            'org_alpha',
            'host_alpha',
            'org_alpha',
            'execution_request',
            payload={'task': 'demo'},
        )
        claims = authority.validate(
            envelope,
            payload={'task': 'demo'},
            expected_target_host_id='host_alpha',
            expected_target_org_id='org_alpha',
            expected_boundary_name='federation_gateway',
        )
        self.assertEqual(claims.source_host_id, 'host_alpha')
        self.assertEqual(claims.target_institution_id, 'org_alpha')

    def test_validate_rejects_wrong_target_host(self):
        from federation import FederationAuthority, FederationValidationError
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(host, signing_secret='alpha-secret')
        envelope = authority.issue(
            'org_alpha',
            'host_beta',
            'org_beta',
            'execution_request',
            payload={'task': 'demo'},
        )
        with self.assertRaises(FederationValidationError):
            authority.validate(
                envelope,
                payload={'task': 'demo'},
                expected_target_host_id='host_alpha',
            )

    def test_accept_rejects_replay_across_restart(self):
        from federation import FederationAuthority, ReplayStore, FederationReplayError
        from runtime_host import default_host_identity

        with tempfile.TemporaryDirectory() as tmp:
            replay_path = os.path.join(tmp, 'federation_replay.log')
            host = default_host_identity(
                host_id='host_alpha',
                federation_enabled=True,
                peer_transport='https',
            )
            issuer = FederationAuthority(host, signing_secret='alpha-secret')
            envelope = issuer.issue(
                'org_alpha',
                'host_alpha',
                'org_alpha',
                'execution_request',
                payload={'task': 'demo'},
            )

            receiver1 = FederationAuthority(
                host,
                signing_secret='alpha-secret',
                replay_store=ReplayStore(replay_path),
            )
            claims = receiver1.accept(
                envelope,
                payload={'task': 'demo'},
                expected_target_host_id='host_alpha',
                expected_target_org_id='org_alpha',
            )
            self.assertTrue(claims.envelope_id.startswith('fed_'))

            receiver2 = FederationAuthority(
                host,
                signing_secret='alpha-secret',
                replay_store=ReplayStore(replay_path),
            )
            with self.assertRaises(FederationReplayError):
                receiver2.accept(
                    envelope,
                    payload={'task': 'demo'},
                    expected_target_host_id='host_alpha',
                    expected_target_org_id='org_alpha',
                )

    def test_validate_uses_trusted_peer_registry(self):
        from federation import FederationAuthority, load_peer_registry
        from runtime_host import default_host_identity

        with tempfile.TemporaryDirectory() as tmp:
            peers_path = os.path.join(tmp, 'federation_peers.json')
            with open(peers_path, 'w') as f:
                json.dump({
                    'host_id': 'host_beta',
                    'peers': {
                        'host_alpha': {
                            'label': 'Alpha Host',
                            'transport': 'https',
                            'endpoint_url': 'http://127.0.0.1:19011',
                            'trust_state': 'trusted',
                            'shared_secret': 'alpha-secret',
                            'admitted_org_ids': ['org_alpha'],
                        }
                    },
                }, f)

            source_host = default_host_identity(
                host_id='host_alpha',
                federation_enabled=True,
                peer_transport='https',
            )
            target_host = default_host_identity(
                host_id='host_beta',
                role='witness_host',
                federation_enabled=True,
                peer_transport='https',
            )
            sender = FederationAuthority(source_host, signing_secret='alpha-secret')
            receiver = FederationAuthority(
                target_host,
                signing_secret='beta-secret',
                peer_registry=load_peer_registry(peers_path, host_identity=target_host),
            )
            envelope = sender.issue(
                'org_alpha',
                'host_beta',
                'org_beta',
                'settlement_notice',
                payload={'tx_ref': '0xabc'},
            )
            claims = receiver.validate(
                envelope,
                payload={'tx_ref': '0xabc'},
                expected_target_host_id='host_beta',
                expected_target_org_id='org_beta',
            )
            self.assertEqual(claims.source_host_id, 'host_alpha')
            self.assertEqual(claims.message_type, 'settlement_notice')

    def test_load_peer_registry_includes_endpoint_url(self):
        from federation import load_peer_registry
        from runtime_host import default_host_identity

        with tempfile.TemporaryDirectory() as tmp:
            peers_path = os.path.join(tmp, 'federation_peers.json')
            with open(peers_path, 'w') as f:
                json.dump({
                    'host_id': 'host_alpha',
                    'peers': {
                        'host_beta': {
                            'label': 'Beta Host',
                            'transport': 'https',
                            'base_url': 'http://127.0.0.1:19012',
                            'trust_state': 'trusted',
                            'shared_secret': 'beta-secret',
                        }
                    },
                }, f)

            registry = load_peer_registry(
                peers_path,
                host_identity=default_host_identity(host_id='host_alpha'),
            )
            peer = registry['peers']['host_beta']
            self.assertEqual(peer.endpoint_url, 'http://127.0.0.1:19012')
            self.assertEqual(peer.receive_url, 'http://127.0.0.1:19012/api/federation/receive')

    def test_deliver_posts_to_trusted_peer_endpoint(self):
        from federation import FederationAuthority, FederationPeer
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(
            host,
            signing_secret='alpha-secret',
            peer_registry={
                'source': 'test',
                'host_id': 'host_alpha',
                'trusted_peer_ids': ['host_beta'],
                'peers': {
                    'host_beta': FederationPeer(
                        'host_beta',
                        transport='https',
                        endpoint_url='http://127.0.0.1:19013',
                        trust_state='trusted',
                        shared_secret='beta-secret',
                        admitted_org_ids=['org_beta'],
                    ),
                },
            },
        )

        calls = {}

        def fake_post(url, data):
            body_b64 = data['envelope'].split('.', 1)[0]
            padding = '=' * ((4 - len(body_b64) % 4) % 4)
            envelope_payload = json.loads(
                base64.urlsafe_b64decode(body_b64 + padding).decode('utf-8')
            )
            calls['url'] = url
            calls['data'] = data
            return {
                'accepted': True,
                'receipt': {
                    'receipt_id': 'fedrcpt_demo',
                    'envelope_id': envelope_payload['envelope_id'],
                    'accepted_at': '2026-03-22T00:00:00Z',
                    'receiver_host_id': 'host_beta',
                    'receiver_institution_id': 'org_beta',
                    'message_type': envelope_payload['message_type'],
                    'boundary_name': envelope_payload['boundary_name'],
                    'identity_model': 'signed_host_service',
                },
            }

        result = authority.deliver(
            'host_beta',
            'org_alpha',
            'org_beta',
            'execution_request',
            payload={'task': 'demo'},
            http_post=fake_post,
            http_get=lambda _url: {
                'host_identity': {'host_id': 'host_beta'},
                'admission': {'admitted_org_ids': ['org_beta']},
                'service_registry': {
                    'federation_gateway': {
                        'identity_model': 'signed_host_service',
                        'supports_institution_routing': True,
                    },
                },
                'federation': {
                    'enabled': True,
                    'boundary_name': 'federation_gateway',
                    'identity_model': 'signed_host_service',
                },
            },
        )
        self.assertEqual(calls['url'], 'http://127.0.0.1:19013/api/federation/receive')
        self.assertIn('envelope', calls['data'])
        self.assertEqual(calls['data']['payload'], {'task': 'demo'})
        self.assertTrue(result['response']['accepted'])
        self.assertEqual(result['receipt']['receipt_id'], 'fedrcpt_demo')
        self.assertEqual(result['response']['receipt']['receipt_id'], 'fedrcpt_demo')
        self.assertEqual(result['peer']['host_id'], 'host_beta')
        self.assertEqual(result['claims']['target_host_id'], 'host_beta')
        self.assertEqual(result['claims']['target_institution_id'], 'org_beta')
        self.assertEqual(result['claims']['message_type'], 'execution_request')

    def test_deliver_rejects_receipt_with_wrong_receiver_host(self):
        from federation import FederationAuthority, FederationDeliveryError, FederationPeer
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(
            host,
            signing_secret='alpha-secret',
            peer_registry={
                'source': 'test',
                'host_id': 'host_alpha',
                'trusted_peer_ids': ['host_beta'],
                'peers': {
                    'host_beta': FederationPeer(
                        'host_beta',
                        transport='https',
                        endpoint_url='http://127.0.0.1:19013',
                        trust_state='trusted',
                        shared_secret='beta-secret',
                        admitted_org_ids=['org_beta'],
                    ),
                },
            },
        )

        with self.assertRaises(FederationDeliveryError):
            authority.deliver(
                'host_beta',
                'org_alpha',
                'org_beta',
                'execution_request',
                payload={'task': 'demo'},
                http_post=lambda _url, _data: {
                    'accepted': True,
                    'receipt': {
                        'receipt_id': 'fedrcpt_bad',
                        'envelope_id': 'fed_wrong',
                        'receiver_host_id': 'host_wrong',
                        'receiver_institution_id': 'org_beta',
                    },
                },
                http_get=lambda _url: {
                    'host_identity': {'host_id': 'host_beta'},
                    'admission': {'admitted_org_ids': ['org_beta']},
                    'service_registry': {
                        'federation_gateway': {
                            'identity_model': 'signed_host_service',
                            'supports_institution_routing': True,
                        },
                    },
                    'federation': {
                        'enabled': True,
                        'boundary_name': 'federation_gateway',
                        'identity_model': 'signed_host_service',
                    },
                },
            )

    def test_deliver_rejects_peer_without_endpoint_url(self):
        from federation import FederationAuthority, FederationDeliveryError, FederationPeer
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(
            host,
            signing_secret='alpha-secret',
            peer_registry={
                'source': 'test',
                'host_id': 'host_alpha',
                'trusted_peer_ids': ['host_beta'],
                'peers': {
                    'host_beta': FederationPeer(
                        'host_beta',
                        transport='https',
                        trust_state='trusted',
                        shared_secret='beta-secret',
                    ),
                },
            },
        )

        with self.assertRaises(FederationDeliveryError) as ctx:
            authority.deliver(
                'host_beta',
                'org_alpha',
                'org_beta',
                'execution_request',
                payload={'task': 'demo'},
            )
        self.assertEqual(ctx.exception.peer_host_id, '')
        self.assertEqual(ctx.exception.response, None)

    def test_deliver_failure_carries_claims(self):
        from federation import FederationAuthority, FederationDeliveryError, FederationPeer
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(
            host,
            signing_secret='alpha-secret',
            peer_registry={
                'source': 'test',
                'host_id': 'host_alpha',
                'trusted_peer_ids': ['host_beta'],
                'peers': {
                    'host_beta': FederationPeer(
                        'host_beta',
                        transport='https',
                        endpoint_url='http://127.0.0.1:19013',
                        trust_state='trusted',
                        shared_secret='beta-secret',
                        admitted_org_ids=['org_beta'],
                    ),
                },
            },
        )

        def fake_post(_url, _data):
            raise RuntimeError('network down')

        with self.assertRaises(FederationDeliveryError) as ctx:
            authority.deliver(
                'host_beta',
                'org_alpha',
                'org_beta',
                'execution_request',
                payload={'task': 'demo'},
                http_post=fake_post,
                http_get=lambda _url: {
                    'host_identity': {'host_id': 'host_beta'},
                    'admission': {'admitted_org_ids': ['org_beta']},
                    'service_registry': {
                        'federation_gateway': {
                            'identity_model': 'signed_host_service',
                            'supports_institution_routing': True,
                        },
                    },
                    'federation': {
                        'enabled': True,
                        'boundary_name': 'federation_gateway',
                        'identity_model': 'signed_host_service',
                    },
                },
            )

        self.assertEqual(ctx.exception.peer_host_id, 'host_beta')
        self.assertTrue(ctx.exception.envelope)
        self.assertEqual(ctx.exception.claims.target_host_id, 'host_beta')
        self.assertEqual(ctx.exception.claims.target_institution_id, 'org_beta')
        self.assertEqual(ctx.exception.claims.message_type, 'execution_request')

    def test_deliver_round_trips_over_http_between_two_hosts(self):
        from federation import FederationAuthority, FederationPeer
        from runtime_host import default_host_identity

        receiver_host = default_host_identity(
            host_id='host_beta',
            federation_enabled=True,
            peer_transport='https',
        )
        receiver = FederationAuthority(
            receiver_host,
            signing_secret='beta-secret',
            peer_registry={
                'source': 'test',
                'host_id': 'host_beta',
                'trusted_peer_ids': ['host_alpha'],
                'peers': {
                    'host_alpha': FederationPeer(
                        'host_alpha',
                        transport='https',
                        endpoint_url='http://127.0.0.1:0',
                        trust_state='trusted',
                        shared_secret='alpha-secret',
                        admitted_org_ids=['org_alpha'],
                    ),
                },
            },
        )
        received_claims = []

        class PeerHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def do_GET(self):
                if self.path != '/api/federation/manifest':
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps({
                    'manifest_version': 1,
                    'host_identity': {'host_id': 'host_beta'},
                    'admission': {'admitted_org_ids': ['org_beta']},
                    'service_registry': {
                        'federation_gateway': {
                            'identity_model': 'signed_host_service',
                            'supports_institution_routing': True,
                        },
                    },
                    'federation': {
                        'enabled': True,
                        'boundary_name': 'federation_gateway',
                        'identity_model': 'signed_host_service',
                    },
                }).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path != '/api/federation/receive':
                    self.send_response(404)
                    self.end_headers()
                    return
                length = int(self.headers.get('Content-Length', '0') or 0)
                payload = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
                claims = receiver.accept(
                    payload.get('envelope', ''),
                    payload=payload.get('payload'),
                    expected_target_host_id='host_beta',
                    expected_target_org_id='org_beta',
                    expected_boundary_name='federation_gateway',
                )
                received_claims.append(claims.to_dict())
                body = json.dumps({
                    'accepted': True,
                    'receipt': {
                        'receipt_id': 'fedrcpt_http',
                        'envelope_id': claims.envelope_id,
                        'accepted_at': '2026-03-22T00:00:00Z',
                        'receiver_host_id': 'host_beta',
                        'receiver_institution_id': 'org_beta',
                        'message_type': claims.message_type,
                        'boundary_name': claims.boundary_name,
                        'identity_model': 'signed_host_service',
                    },
                }).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        try:
            server = ThreadingHTTPServer(('127.0.0.1', 0), PeerHandler)
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            sender_host = default_host_identity(
                host_id='host_alpha',
                federation_enabled=True,
                peer_transport='https',
            )
            authority = FederationAuthority(
                sender_host,
                signing_secret='alpha-secret',
                peer_registry={
                    'source': 'test',
                    'host_id': 'host_alpha',
                    'trusted_peer_ids': ['host_beta'],
                    'peers': {
                        'host_beta': FederationPeer(
                            'host_beta',
                            transport='https',
                            endpoint_url=f'http://127.0.0.1:{server.server_address[1]}',
                            trust_state='trusted',
                            shared_secret='beta-secret',
                            admitted_org_ids=['org_beta'],
                        ),
                    },
                },
            )
            result = authority.deliver(
                'host_beta',
                'org_alpha',
                'org_beta',
                'execution_request',
                payload={'task': 'demo'},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(result['receipt']['receipt_id'], 'fedrcpt_http')
        self.assertEqual(result['receipt']['receiver_host_id'], 'host_beta')
        self.assertEqual(result['claims']['target_host_id'], 'host_beta')
        self.assertEqual(len(received_claims), 1)
        self.assertEqual(received_claims[0]['source_host_id'], 'host_alpha')
        self.assertEqual(received_claims[0]['target_institution_id'], 'org_beta')

    def test_deliver_rejects_http_manifest_target_mismatch(self):
        from federation import FederationAuthority, FederationDeliveryError, FederationPeer
        from runtime_host import default_host_identity

        class ManifestOnlyHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def do_GET(self):
                if self.path != '/api/federation/manifest':
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps({
                    'manifest_version': 1,
                    'host_identity': {'host_id': 'host_beta'},
                    'admission': {'admitted_org_ids': ['org_other']},
                    'service_registry': {
                        'federation_gateway': {
                            'identity_model': 'signed_host_service',
                            'supports_institution_routing': True,
                        },
                    },
                    'federation': {
                        'enabled': True,
                        'boundary_name': 'federation_gateway',
                        'identity_model': 'signed_host_service',
                    },
                }).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                self.send_response(500)
                self.end_headers()

        try:
            server = ThreadingHTTPServer(('127.0.0.1', 0), ManifestOnlyHandler)
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host = default_host_identity(
                host_id='host_alpha',
                federation_enabled=True,
                peer_transport='https',
            )
            authority = FederationAuthority(
                host,
                signing_secret='alpha-secret',
                peer_registry={
                    'source': 'test',
                    'host_id': 'host_alpha',
                    'trusted_peer_ids': ['host_beta'],
                    'peers': {
                        'host_beta': FederationPeer(
                            'host_beta',
                            transport='https',
                            endpoint_url=f'http://127.0.0.1:{server.server_address[1]}',
                            trust_state='trusted',
                            shared_secret='beta-secret',
                            admitted_org_ids=['org_beta'],
                        ),
                    },
                },
            )
            with self.assertRaises(FederationDeliveryError):
                authority.deliver(
                    'host_beta',
                    'org_alpha',
                    'org_beta',
                    'execution_request',
                    payload={'task': 'demo'},
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_workspace_federation_send_round_trips_between_two_hosts_with_session_audit(self):
        try:
            port_alpha = _find_free_port()
            port_beta = _find_free_port()
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')

        with tempfile.TemporaryDirectory() as tmp:
            alpha = _seed_workspace_root(
                os.path.join(tmp, 'alpha'),
                org_id='org_alpha',
                user_id='user_owner_alpha',
                host_id='host_alpha',
                port=port_alpha,
                signing_secret='alpha-secret',
                peer_entries={
                    'host_beta': {
                        'label': 'Beta Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_beta}',
                        'trust_state': 'trusted',
                        'shared_secret': 'beta-secret',
                        'admitted_org_ids': ['org_beta'],
                    },
                },
            )
            beta = _seed_workspace_root(
                os.path.join(tmp, 'beta'),
                org_id='org_beta',
                user_id='user_owner_beta',
                host_id='host_beta',
                port=port_beta,
                signing_secret='beta-secret',
                peer_entries={
                    'host_alpha': {
                        'label': 'Alpha Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_alpha}',
                        'trust_state': 'trusted',
                        'shared_secret': 'alpha-secret',
                        'admitted_org_ids': ['org_alpha'],
                    },
                },
            )
            with _run_workspace(beta), _run_workspace(alpha):
                session = _issue_workspace_session(alpha)
                session_id = session['session_id']
                request_payload = {'task': 'demo'}
                warrant = _issue_workspace_warrant(alpha, session['token'], request_payload)
                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/federation/send',
                    payload={
                        'target_host_id': 'host_beta',
                        'target_org_id': 'org_beta',
                        'message_type': 'execution_request',
                        'payload': request_payload,
                        'warrant_id': warrant['warrant_id'],
                    },
                    headers={
                        'Authorization': f"Bearer {session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(status, 200, body)
                delivery = body['delivery']
                self.assertEqual(delivery['receipt']['receiver_host_id'], 'host_beta')
                self.assertEqual(delivery['receipt']['receiver_institution_id'], 'org_beta')
                self.assertEqual(delivery['claims']['session_id'], session_id)
                self.assertEqual(delivery['claims']['actor_id'], 'user_owner_alpha')
                self.assertEqual(delivery['claims']['warrant_id'], warrant['warrant_id'])
                inbox_status, inbox_body = _http_json(
                    'GET',
                    beta['base_url'] + '/api/federation/inbox',
                    headers={'Authorization': beta['auth_header']},
                )
                self.assertEqual(inbox_status, 200, inbox_body)
                self.assertEqual(inbox_body['summary']['total'], 1)
                self.assertEqual(inbox_body['summary']['message_type_counts'], {
                    'execution_request': 1,
                })
                self.assertEqual(inbox_body['entries'][0]['envelope_id'], delivery['claims']['envelope_id'])
                self.assertEqual(inbox_body['entries'][0]['receipt_id'], delivery['receipt']['receipt_id'])
                self.assertEqual(inbox_body['entries'][0]['warrant_id'], warrant['warrant_id'])
                self.assertEqual(inbox_body['entries'][0]['payload'], request_payload)
                self.assertEqual(inbox_body['entries'][0]['state'], 'received')

            alpha_events = _read_jsonl(alpha['audit_log'])
            beta_events = _read_jsonl(beta['audit_log'])
            sent = [event for event in alpha_events if event.get('action') == 'federation_envelope_sent']
            received = [
                event for event in beta_events
                if event.get('action') == 'federation_envelope_received'
            ]
            self.assertTrue(sent)
            self.assertTrue(received)
            self.assertEqual(sent[-1].get('session_id'), session_id)
            self.assertEqual(received[-1].get('session_id'), session_id)
            self.assertEqual(sent[-1]['details']['receiver_host_id'], 'host_beta')
            self.assertEqual(sent[-1]['details']['warrant_id'], warrant['warrant_id'])
            self.assertEqual(received[-1]['details']['source_host_id'], 'host_alpha')
            self.assertEqual(received[-1]['details']['warrant_id'], warrant['warrant_id'])
            self.assertEqual(received[-1]['agent_id'], 'user_owner_alpha')

            warrants_path = os.path.join(alpha['economy'], 'warrants.json')
            with open(warrants_path) as f:
                warrant_store = json.load(f)
            warrant_record = warrant_store['warrants'][warrant['warrant_id']]
            self.assertEqual(warrant_record['execution_state'], 'executed')
            self.assertEqual(
                warrant_record['execution_refs']['receipt_id'],
                delivery['receipt']['receipt_id'],
            )

    def test_workspace_federation_settlement_notice_applies_on_receiver(self):
        try:
            port_alpha = _find_free_port()
            port_beta = _find_free_port()
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')

        with tempfile.TemporaryDirectory() as tmp:
            alpha = _seed_workspace_root(
                os.path.join(tmp, 'alpha'),
                org_id='org_alpha',
                user_id='user_owner_alpha',
                host_id='host_alpha',
                port=port_alpha,
                signing_secret='alpha-secret',
                peer_entries={
                    'host_beta': {
                        'label': 'Beta Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_beta}',
                        'trust_state': 'trusted',
                        'shared_secret': 'beta-secret',
                        'admitted_org_ids': ['org_beta'],
                    },
                },
            )
            beta = _seed_workspace_root(
                os.path.join(tmp, 'beta'),
                org_id='org_beta',
                user_id='user_owner_beta',
                host_id='host_beta',
                port=port_beta,
                signing_secret='beta-secret',
                peer_entries={
                    'host_alpha': {
                        'label': 'Alpha Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_alpha}',
                        'trust_state': 'trusted',
                        'shared_secret': 'alpha-secret',
                        'admitted_org_ids': ['org_alpha'],
                    },
                },
            )
            commitment_id = 'cmt_shared_settlement'
            _seed_commitments(
                os.path.join(alpha['economy'], 'commitments.json'),
                [
                    _accepted_commitment_record(
                        org_id='org_alpha',
                        commitment_id=commitment_id,
                        target_host_id='host_beta',
                        target_institution_id='org_beta',
                    ),
                ],
            )
            _seed_commitments(
                os.path.join(beta['economy'], 'commitments.json'),
                [
                    _accepted_commitment_record(
                        org_id='org_beta',
                        commitment_id=commitment_id,
                        target_host_id='host_alpha',
                        target_institution_id='org_alpha',
                    ),
                ],
            )

            with _run_workspace(beta), _run_workspace(alpha):
                session = _issue_workspace_session(alpha)
                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/federation/send',
                    payload={
                        'target_host_id': 'host_beta',
                        'target_org_id': 'org_beta',
                        'message_type': 'settlement_notice',
                        'commitment_id': commitment_id,
                        'payload': {
                            'proposal_id': 'ppo_demo',
                            'tx_ref': 'tx_demo_settlement',
                            'settlement_adapter': 'internal_ledger',
                            'proof_type': 'internal_ledger',
                            'verification_state': 'accepted',
                            'finality_state': 'final',
                            'proof': {'entry': 1},
                        },
                    },
                    headers={
                        'Authorization': f"Bearer {session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(status, 200, body)
                delivery = body['delivery']
                self.assertEqual(delivery['claims']['commitment_id'], commitment_id)
                self.assertTrue(delivery['response']['processing']['applied'])
                self.assertEqual(
                    delivery['response']['processing']['reason'],
                    'settlement_notice_applied',
                )
                self.assertEqual(
                    delivery['response']['processing']['commitment']['state'],
                    'settled',
                )
                self.assertEqual(
                    delivery['response']['processing']['settlement_ref']['tx_ref'],
                    'tx_demo_settlement',
                )
                self.assertEqual(
                    delivery['response']['processing']['inbox_entry']['state'],
                    'processed',
                )

                inbox_status, inbox_body = _http_json(
                    'GET',
                    beta['base_url'] + '/api/federation/inbox',
                    headers={'Authorization': beta['auth_header']},
                )
                self.assertEqual(inbox_status, 200, inbox_body)
                self.assertEqual(inbox_body['summary']['processed'], 1)
                self.assertEqual(inbox_body['entries'][0]['state'], 'processed')
                self.assertEqual(inbox_body['entries'][0]['commitment_id'], commitment_id)

            with open(os.path.join(beta['economy'], 'commitments.json')) as f:
                beta_commitments = json.load(f)
            beta_record = beta_commitments['commitments'][commitment_id]
            self.assertEqual(beta_record['state'], 'settled')
            self.assertEqual(beta_record['settlement_refs'][0]['proposal_id'], 'ppo_demo')
            self.assertEqual(beta_record['settlement_refs'][0]['tx_ref'], 'tx_demo_settlement')
            self.assertEqual(beta_record['settlement_refs'][0]['source_host_id'], 'host_alpha')

            beta_events = _read_jsonl(beta['audit_log'])
            applied = [
                event for event in beta_events
                if event.get('action') == 'federation_settlement_notice_applied'
            ]
            self.assertTrue(applied)
            self.assertEqual(applied[-1]['resource'], commitment_id)

    def test_workspace_federation_settlement_notice_replay_is_idempotent(self):
        try:
            port_alpha = _find_free_port()
            port_beta = _find_free_port()
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')

        with tempfile.TemporaryDirectory() as tmp:
            alpha = _seed_workspace_root(
                os.path.join(tmp, 'alpha'),
                org_id='org_alpha',
                user_id='user_owner_alpha',
                host_id='host_alpha',
                port=port_alpha,
                signing_secret='alpha-secret',
                peer_entries={
                    'host_beta': {
                        'label': 'Beta Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_beta}',
                        'trust_state': 'trusted',
                        'shared_secret': 'beta-secret',
                        'admitted_org_ids': ['org_beta'],
                    },
                },
            )
            beta = _seed_workspace_root(
                os.path.join(tmp, 'beta'),
                org_id='org_beta',
                user_id='user_owner_beta',
                host_id='host_beta',
                port=port_beta,
                signing_secret='beta-secret',
                peer_entries={
                    'host_alpha': {
                        'label': 'Alpha Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_alpha}',
                        'trust_state': 'trusted',
                        'shared_secret': 'alpha-secret',
                        'admitted_org_ids': ['org_alpha'],
                    },
                },
            )
            commitment_id = 'cmt_replay_settlement'
            _seed_commitments(
                os.path.join(beta['economy'], 'commitments.json'),
                [
                    _accepted_commitment_record(
                        org_id='org_beta',
                        commitment_id=commitment_id,
                        target_host_id='host_beta',
                        target_institution_id='org_beta',
                    ),
                ],
            )

            from federation import FederationAuthority
            from runtime_host import default_host_identity

            sender_host = default_host_identity(
                host_id='host_alpha',
                federation_enabled=True,
                peer_transport='https',
            )
            authority = FederationAuthority(sender_host, signing_secret='alpha-secret')
            envelope = authority.issue(
                'org_alpha',
                'host_beta',
                'org_beta',
                'settlement_notice',
                payload={
                    'proposal_id': 'ppo_replay',
                    'tx_ref': 'tx_replay',
                    'settlement_adapter': 'internal_ledger',
                    'proof_type': 'internal_ledger',
                    'verification_state': 'accepted',
                    'finality_state': 'final',
                    'proof': {'entry': 1},
                },
                commitment_id=commitment_id,
                warrant_id='',
            )

            with _run_workspace(beta), _run_workspace(alpha):
                first_status, first_body = _http_json(
                    'POST',
                    beta['base_url'] + '/api/federation/receive',
                    payload={
                        'envelope': envelope,
                        'payload': {
                            'proposal_id': 'ppo_replay',
                            'tx_ref': 'tx_replay',
                            'settlement_adapter': 'internal_ledger',
                            'proof_type': 'internal_ledger',
                            'verification_state': 'accepted',
                            'finality_state': 'final',
                            'proof': {'entry': 1},
                        },
                    },
                )
                self.assertEqual(first_status, 200, first_body)
                self.assertTrue(first_body['processing']['applied'])
                self.assertEqual(first_body['processing']['inbox_entry']['state'], 'processed')

                second_status, second_body = _http_json(
                    'POST',
                    beta['base_url'] + '/api/federation/receive',
                    payload={
                        'envelope': envelope,
                        'payload': {
                            'proposal_id': 'ppo_replay',
                            'tx_ref': 'tx_replay',
                            'settlement_adapter': 'internal_ledger',
                            'proof_type': 'internal_ledger',
                            'verification_state': 'accepted',
                            'finality_state': 'final',
                            'proof': {'entry': 1},
                        },
                    },
                )
                self.assertEqual(second_status, 409, second_body)
                self.assertIn('nonce already consumed', second_body['error'])

                inbox_status, inbox_body = _http_json(
                    'GET',
                    beta['base_url'] + '/api/federation/inbox',
                    headers={'Authorization': beta['auth_header']},
                )
                self.assertEqual(inbox_status, 200, inbox_body)
                self.assertEqual(inbox_body['summary']['total'], 1)
                self.assertEqual(inbox_body['summary']['processed'], 1)

            with open(os.path.join(beta['economy'], 'commitments.json')) as f:
                beta_commitments = json.load(f)
            beta_record = beta_commitments['commitments'][commitment_id]
            self.assertEqual(len(beta_record['settlement_refs']), 1)
            self.assertEqual(beta_record['settlement_refs'][0]['receipt_id'], first_body['receipt']['receipt_id'])
            self.assertEqual(beta_record['settlement_refs'][0]['envelope_id'], first_body['claims']['envelope_id'])

            beta_events = _read_jsonl(beta['audit_log'])
            applied = [
                event for event in beta_events
                if event.get('action') == 'federation_settlement_notice_applied'
            ]
            self.assertEqual(len(applied), 1)

    def test_workspace_federation_settlement_notice_keeps_inbox_received_when_case_blocked(self):
        try:
            port_alpha = _find_free_port()
            port_beta = _find_free_port()
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')

        with tempfile.TemporaryDirectory() as tmp:
            alpha = _seed_workspace_root(
                os.path.join(tmp, 'alpha'),
                org_id='org_alpha',
                user_id='user_owner_alpha',
                host_id='host_alpha',
                port=port_alpha,
                signing_secret='alpha-secret',
                peer_entries={
                    'host_beta': {
                        'label': 'Beta Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_beta}',
                        'trust_state': 'trusted',
                        'shared_secret': 'beta-secret',
                        'admitted_org_ids': ['org_beta'],
                    },
                },
            )
            beta = _seed_workspace_root(
                os.path.join(tmp, 'beta'),
                org_id='org_beta',
                user_id='user_owner_beta',
                host_id='host_beta',
                port=port_beta,
                signing_secret='beta-secret',
                peer_entries={
                    'host_alpha': {
                        'label': 'Alpha Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_alpha}',
                        'trust_state': 'trusted',
                        'shared_secret': 'alpha-secret',
                        'admitted_org_ids': ['org_alpha'],
                    },
                },
            )
            commitment_id = 'cmt_shared_blocked'
            _seed_commitments(
                os.path.join(alpha['economy'], 'commitments.json'),
                [
                    _accepted_commitment_record(
                        org_id='org_alpha',
                        commitment_id=commitment_id,
                        target_host_id='host_beta',
                        target_institution_id='org_beta',
                    ),
                ],
            )
            _seed_commitments(
                os.path.join(beta['economy'], 'commitments.json'),
                [
                    _accepted_commitment_record(
                        org_id='org_beta',
                        commitment_id=commitment_id,
                        target_host_id='host_alpha',
                        target_institution_id='org_alpha',
                    ),
                ],
            )

            with _run_workspace(beta), _run_workspace(alpha):
                beta_session = _issue_workspace_session(beta)
                status, body = _http_json(
                    'POST',
                    beta['base_url'] + '/api/cases/open',
                    payload={
                        'claim_type': 'non_delivery',
                        'linked_commitment_id': commitment_id,
                        'target_host_id': 'host_alpha',
                        'target_institution_id': 'org_alpha',
                    },
                    headers={
                        'Authorization': f"Bearer {beta_session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(status, 200, body)
                case_id = body['case']['case_id']

                alpha_session = _issue_workspace_session(alpha)
                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/federation/send',
                    payload={
                        'target_host_id': 'host_beta',
                        'target_org_id': 'org_beta',
                        'message_type': 'settlement_notice',
                        'commitment_id': commitment_id,
                        'payload': {
                            'proposal_id': 'ppo_blocked',
                            'tx_ref': 'tx_blocked',
                            'settlement_adapter': 'internal_ledger',
                        },
                    },
                    headers={
                        'Authorization': f"Bearer {alpha_session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(status, 200, body)
                delivery = body['delivery']
                self.assertFalse(delivery['response']['processing']['applied'])
                self.assertEqual(delivery['response']['processing']['reason'], 'case_blocked')
                self.assertEqual(delivery['response']['processing']['case']['case_id'], case_id)
                self.assertEqual(delivery['response']['inbox_entry']['state'], 'received')

                inbox_status, inbox_body = _http_json(
                    'GET',
                    beta['base_url'] + '/api/federation/inbox',
                    headers={'Authorization': beta['auth_header']},
                )
                self.assertEqual(inbox_status, 200, inbox_body)
                self.assertEqual(inbox_body['summary']['received'], 1)
                self.assertEqual(inbox_body['summary']['processed'], 0)
                self.assertEqual(inbox_body['entries'][0]['state'], 'received')

            with open(os.path.join(beta['economy'], 'commitments.json')) as f:
                beta_commitments = json.load(f)
            beta_record = beta_commitments['commitments'][commitment_id]
            self.assertEqual(beta_record['state'], 'accepted')
            self.assertEqual(beta_record['settlement_refs'], [])

            beta_events = _read_jsonl(beta['audit_log'])
            blocked = [
                event for event in beta_events
                if event.get('action') == 'federation_settlement_notice_blocked'
            ]
            self.assertTrue(blocked)
            self.assertEqual(blocked[-1]['resource'], commitment_id)

    def test_workspace_federation_send_rejects_manifest_host_mismatch(self):
        try:
            port_alpha = _find_free_port()
            port_beta = _find_free_port()
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')

        with tempfile.TemporaryDirectory() as tmp:
            alpha = _seed_workspace_root(
                os.path.join(tmp, 'alpha'),
                org_id='org_alpha',
                user_id='user_owner_alpha',
                host_id='host_alpha',
                port=port_alpha,
                signing_secret='alpha-secret',
                peer_entries={
                    'host_gamma': {
                        'label': 'Gamma Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_beta}',
                        'trust_state': 'trusted',
                        'shared_secret': 'gamma-secret',
                        'admitted_org_ids': ['org_beta'],
                    },
                },
            )
            beta = _seed_workspace_root(
                os.path.join(tmp, 'beta'),
                org_id='org_beta',
                user_id='user_owner_beta',
                host_id='host_beta',
                port=port_beta,
                signing_secret='beta-secret',
                peer_entries={
                    'host_alpha': {
                        'label': 'Alpha Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_alpha}',
                        'trust_state': 'trusted',
                        'shared_secret': 'alpha-secret',
                        'admitted_org_ids': ['org_alpha'],
                    },
                },
            )
            with _run_workspace(beta), _run_workspace(alpha):
                session = _issue_workspace_session(alpha)
                request_payload = {'task': 'demo'}
                warrant = _issue_workspace_warrant(alpha, session['token'], request_payload)
                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/federation/send',
                    payload={
                        'target_host_id': 'host_gamma',
                        'target_org_id': 'org_beta',
                        'message_type': 'execution_request',
                        'payload': request_payload,
                        'warrant_id': warrant['warrant_id'],
                    },
                    headers={
                        'Authorization': f"Bearer {session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(status, 502, body)
                self.assertIn("manifest host_id 'host_beta' does not match trusted peer 'host_gamma'", body['error'])

            beta_events = _read_jsonl(beta['audit_log'])
            received = [
                event for event in beta_events
                if event.get('action') == 'federation_envelope_received'
            ]
            self.assertEqual(received, [])

    def test_workspace_federation_send_rejects_manifest_target_org_mismatch(self):
        try:
            port_alpha = _find_free_port()
            port_beta = _find_free_port()
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')

        with tempfile.TemporaryDirectory() as tmp:
            alpha = _seed_workspace_root(
                os.path.join(tmp, 'alpha'),
                org_id='org_alpha',
                user_id='user_owner_alpha',
                host_id='host_alpha',
                port=port_alpha,
                signing_secret='alpha-secret',
                peer_entries={
                    'host_beta': {
                        'label': 'Beta Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_beta}',
                        'trust_state': 'trusted',
                        'shared_secret': 'beta-secret',
                        'admitted_org_ids': ['org_beta'],
                    },
                },
            )
            beta = _seed_workspace_root(
                os.path.join(tmp, 'beta'),
                org_id='org_beta',
                user_id='user_owner_beta',
                host_id='host_beta',
                port=port_beta,
                signing_secret='beta-secret',
                peer_entries={
                    'host_alpha': {
                        'label': 'Alpha Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_alpha}',
                        'trust_state': 'trusted',
                        'shared_secret': 'alpha-secret',
                        'admitted_org_ids': ['org_alpha'],
                    },
                },
            )
            with _run_workspace(beta), _run_workspace(alpha):
                session = _issue_workspace_session(alpha)
                request_payload = {'task': 'demo'}
                warrant = _issue_workspace_warrant(alpha, session['token'], request_payload)
                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/federation/send',
                    payload={
                        'target_host_id': 'host_beta',
                        'target_org_id': 'org_wrong',
                        'message_type': 'execution_request',
                        'payload': request_payload,
                        'warrant_id': warrant['warrant_id'],
                    },
                    headers={
                        'Authorization': f"Bearer {session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(status, 502, body)
                self.assertIn("registry does not admit target institution 'org_wrong'", body['error'])

            alpha_events = _read_jsonl(alpha['audit_log'])
            failed = [
                event for event in alpha_events
                if event.get('action') == 'federation_envelope_delivery_failed'
            ]
            beta_events = _read_jsonl(beta['audit_log'])
            received = [
                event for event in beta_events
                if event.get('action') == 'federation_envelope_received'
            ]
            self.assertTrue(failed)
            self.assertEqual(failed[-1]['details']['target_institution_id'], 'org_wrong')
            self.assertEqual(received, [])

    def test_workspace_federation_send_rejects_forged_peer_signature(self):
        try:
            port_alpha = _find_free_port()
            port_beta = _find_free_port()
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')

        with tempfile.TemporaryDirectory() as tmp:
            alpha = _seed_workspace_root(
                os.path.join(tmp, 'alpha'),
                org_id='org_alpha',
                user_id='user_owner_alpha',
                host_id='host_alpha',
                port=port_alpha,
                signing_secret='alpha-secret',
                peer_entries={
                    'host_beta': {
                        'label': 'Beta Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_beta}',
                        'trust_state': 'trusted',
                        'shared_secret': 'beta-secret',
                        'admitted_org_ids': ['org_beta'],
                    },
                },
            )
            beta = _seed_workspace_root(
                os.path.join(tmp, 'beta'),
                org_id='org_beta',
                user_id='user_owner_beta',
                host_id='host_beta',
                port=port_beta,
                signing_secret='beta-secret',
                peer_entries={
                    'host_alpha': {
                        'label': 'Alpha Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_alpha}',
                        'trust_state': 'trusted',
                        'shared_secret': 'wrong-alpha-secret',
                        'admitted_org_ids': ['org_alpha'],
                    },
                },
            )
            with _run_workspace(beta), _run_workspace(alpha):
                session = _issue_workspace_session(alpha)
                request_payload = {'task': 'demo'}
                warrant = _issue_workspace_warrant(alpha, session['token'], request_payload)
                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/federation/send',
                    payload={
                        'target_host_id': 'host_beta',
                        'target_org_id': 'org_beta',
                        'message_type': 'execution_request',
                        'payload': request_payload,
                        'warrant_id': warrant['warrant_id'],
                    },
                    headers={
                        'Authorization': f"Bearer {session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(status, 502, body)
                self.assertIn('HTTP 403', body['error'])
                self.assertIn('Envelope signature verification failed', body['error'])

            alpha_events = _read_jsonl(alpha['audit_log'])
            failed = [
                event for event in alpha_events
                if event.get('action') == 'federation_envelope_delivery_failed'
            ]
            beta_events = _read_jsonl(beta['audit_log'])
            received = [
                event for event in beta_events
                if event.get('action') == 'federation_envelope_received'
            ]
            self.assertTrue(failed)
            self.assertEqual(failed[-1]['details']['target_host_id'], 'host_beta')
            self.assertEqual(received, [])

    def test_workspace_federation_send_opens_case_for_bad_receipt(self):
        try:
            port_alpha = _find_free_port()
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')

        class BadReceiptHandler(BaseHTTPRequestHandler):
            receive_count = 0

            def log_message(self, format, *args):
                return

            def do_GET(self):
                if self.path != '/api/federation/manifest':
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps({
                    'manifest_version': 1,
                    'host_identity': {'host_id': 'host_beta'},
                    'admission': {'admitted_org_ids': ['org_beta']},
                    'service_registry': {
                        'federation_gateway': {
                            'identity_model': 'signed_host_service',
                            'supports_institution_routing': True,
                        },
                    },
                    'federation': {
                        'enabled': True,
                        'boundary_name': 'federation_gateway',
                        'identity_model': 'signed_host_service',
                    },
                }).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path != '/api/federation/receive':
                    self.send_response(404)
                    self.end_headers()
                    return
                type(self).receive_count += 1
                length = int(self.headers.get('Content-Length', '0') or 0)
                payload = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
                envelope = payload.get('envelope', '')
                body_b64 = envelope.split('.', 1)[0]
                padding = '=' * ((4 - len(body_b64) % 4) % 4)
                claims = json.loads(base64.urlsafe_b64decode(body_b64 + padding).decode('utf-8'))
                body = json.dumps({
                    'accepted': True,
                    'receipt': {
                        'receipt_id': 'fedrcpt_bad',
                        'envelope_id': claims['envelope_id'],
                        'accepted_at': '2026-03-22T00:00:00Z',
                        'receiver_host_id': 'host_beta',
                        'receiver_institution_id': 'org_wrong',
                        'message_type': claims['message_type'],
                        'boundary_name': claims['boundary_name'],
                        'identity_model': 'signed_host_service',
                    },
                }).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        try:
            server = ThreadingHTTPServer(('127.0.0.1', 0), BadReceiptHandler)
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                alpha = _seed_workspace_root(
                    os.path.join(tmp, 'alpha'),
                    org_id='org_alpha',
                    user_id='user_owner_alpha',
                    host_id='host_alpha',
                    port=port_alpha,
                    signing_secret='alpha-secret',
                    peer_entries={
                        'host_beta': {
                            'label': 'Beta Host',
                            'transport': 'https',
                            'endpoint_url': f'http://127.0.0.1:{server.server_address[1]}',
                            'trust_state': 'trusted',
                            'shared_secret': 'beta-secret',
                            'admitted_org_ids': ['org_beta'],
                        },
                    },
                )
                with _run_workspace(alpha):
                    session = _issue_workspace_session(alpha)
                    status, body = _http_json(
                        'POST',
                        alpha['base_url'] + '/api/federation/send',
                        payload={
                            'target_host_id': 'host_beta',
                            'target_org_id': 'org_beta',
                            'message_type': 'settlement_notice',
                            'payload': {'tx_ref': '0xabc'},
                        },
                        headers={
                            'Authorization': f"Bearer {session['token']}",
                            'Content-Type': 'application/json',
                        },
                    )
                    self.assertEqual(status, 502, body)
                    self.assertEqual(body['case']['claim_type'], 'misrouted_execution')
                    self.assertEqual(body['case']['target_host_id'], 'host_beta')
                    self.assertTrue(body['federation_peer']['applied'])
                    self.assertEqual(body['federation_peer']['trust_state'], 'suspended')
                    self.assertEqual(BadReceiptHandler.receive_count, 1)

                    blocked_status, blocked_body = _http_json(
                        'POST',
                        alpha['base_url'] + '/api/federation/send',
                        payload={
                            'target_host_id': 'host_beta',
                            'target_org_id': 'org_beta',
                            'message_type': 'settlement_notice',
                            'payload': {'tx_ref': '0xdef'},
                        },
                        headers={
                            'Authorization': f"Bearer {session['token']}",
                            'Content-Type': 'application/json',
                        },
                    )
                    self.assertEqual(blocked_status, 409, blocked_body)
                    self.assertEqual(blocked_body['case']['case_id'], body['case']['case_id'])
                    self.assertEqual(blocked_body['case']['claim_type'], 'misrouted_execution')
                    self.assertEqual(blocked_body['federation_peer']['peer_host_id'], 'host_beta')
                    self.assertEqual(blocked_body['federation_peer']['trust_state'], 'suspended')
                    self.assertEqual(blocked_body['federation_peer']['reason'], 'case_blocked')
                    self.assertEqual(BadReceiptHandler.receive_count, 1)

                    status, cases_body = _http_json(
                        'GET',
                        alpha['base_url'] + '/api/cases',
                        headers={'Authorization': alpha['auth_header']},
                    )
                    self.assertEqual(status, 200, cases_body)
                    self.assertEqual(cases_body['total'], 1)
                    self.assertEqual(cases_body['blocked_peer_host_ids'], ['host_beta'])

                alpha_events = _read_jsonl(alpha['audit_log'])
                opened = [e for e in alpha_events if e.get('action') == 'case_opened']
                suspended = [e for e in alpha_events if e.get('action') == 'federation_peer_auto_suspended']
                failed = [e for e in alpha_events if e.get('action') == 'federation_envelope_delivery_failed']
                blocked = [e for e in alpha_events if e.get('action') == 'federation_case_blocked']
                self.assertTrue(opened)
                self.assertEqual(opened[-1]['details']['claim_type'], 'misrouted_execution')
                self.assertTrue(suspended)
                self.assertEqual(suspended[-1]['details']['trust_state'], 'suspended')
                self.assertTrue(failed)
                self.assertTrue(blocked)
                self.assertEqual(blocked[-1]['details']['case_id'], opened[-1]['resource'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_workspace_commitment_settlement_is_blocked_by_active_case(self):
        try:
            port_alpha = _find_free_port()
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')
        with tempfile.TemporaryDirectory() as tmp:
            alpha = _seed_workspace_root(
                os.path.join(tmp, 'alpha'),
                org_id='org_alpha',
                user_id='user_owner_alpha',
                host_id='host_alpha',
                port=port_alpha,
                signing_secret='alpha-secret',
                peer_entries={},
            )
            with _run_workspace(alpha):
                session = _issue_workspace_session(alpha)
                request_payload = {'task': 'settle-demo'}
                warrant = _issue_workspace_warrant(alpha, session['token'], request_payload)

                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/commitments/propose',
                    payload={
                        'target_host_id': 'host_beta',
                        'target_institution_id': 'org_beta',
                        'summary': 'Deliver governed work',
                        'warrant_id': warrant['warrant_id'],
                    },
                    headers={
                        'Authorization': f"Bearer {session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(status, 200, body)
                commitment_id = body['commitment']['commitment_id']

                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/commitments/accept',
                    payload={'commitment_id': commitment_id},
                    headers={
                        'Authorization': f"Bearer {session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(status, 200, body)

                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/cases/open',
                    payload={
                        'claim_type': 'non_delivery',
                        'linked_commitment_id': commitment_id,
                        'linked_warrant_id': warrant['warrant_id'],
                        'target_host_id': 'host_beta',
                        'target_institution_id': 'org_beta',
                    },
                    headers={
                        'Authorization': f"Bearer {session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(status, 200, body)
                self.assertEqual(body['warrant']['court_review_state'], 'stayed')

                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/commitments/settle',
                    payload={'commitment_id': commitment_id},
                    headers={
                        'Authorization': f"Bearer {session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(status, 409, body)
                self.assertEqual(body['case']['linked_commitment_id'], commitment_id)
                self.assertEqual(body['warrant']['warrant_id'], warrant['warrant_id'])
                self.assertIn(body['warrant']['reason'], ('already_stayed', 'case_hold_applied'))

                status, warrants_body = _http_json(
                    'GET',
                    alpha['base_url'] + '/api/warrants',
                    headers={'Authorization': alpha['auth_header']},
                )
                self.assertEqual(status, 200, warrants_body)
                warrant_record = next(
                    item for item in warrants_body['warrants']
                    if item['warrant_id'] == warrant['warrant_id']
                )
                self.assertEqual(warrant_record['court_review_state'], 'stayed')

                alpha_events = _read_jsonl(alpha['audit_log'])
                blocked = [
                    event for event in alpha_events
                    if event.get('action') == 'commitment_settlement_blocked'
                ]
                self.assertTrue(blocked)
                self.assertEqual(blocked[-1]['resource'], commitment_id)

    def test_workspace_federation_send_bad_receipt_auto_stays_warrant(self):
        try:
            port_alpha = _find_free_port()
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')

        class BadReceiptHandler(BaseHTTPRequestHandler):
            receive_count = 0

            def log_message(self, format, *args):
                return

            def do_GET(self):
                if self.path != '/api/federation/manifest':
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps({
                    'manifest_version': 1,
                    'host_identity': {'host_id': 'host_beta'},
                    'admission': {'admitted_org_ids': ['org_beta']},
                    'service_registry': {
                        'federation_gateway': {
                            'identity_model': 'signed_host_service',
                            'supports_institution_routing': True,
                        },
                    },
                    'federation': {
                        'enabled': True,
                        'boundary_name': 'federation_gateway',
                        'identity_model': 'signed_host_service',
                    },
                }).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path != '/api/federation/receive':
                    self.send_response(404)
                    self.end_headers()
                    return
                type(self).receive_count += 1
                length = int(self.headers.get('Content-Length', '0') or 0)
                payload = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
                envelope = payload.get('envelope', '')
                body_b64 = envelope.split('.', 1)[0]
                padding = '=' * ((4 - len(body_b64) % 4) % 4)
                claims = json.loads(base64.urlsafe_b64decode(body_b64 + padding).decode('utf-8'))
                body = json.dumps({
                    'accepted': True,
                    'receipt': {
                        'receipt_id': 'fedrcpt_bad_warrant',
                        'envelope_id': claims['envelope_id'],
                        'accepted_at': '2026-03-22T00:00:00Z',
                        'receiver_host_id': 'host_beta',
                        'receiver_institution_id': 'org_wrong',
                        'message_type': claims['message_type'],
                        'boundary_name': claims['boundary_name'],
                        'identity_model': 'signed_host_service',
                    },
                }).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        try:
            server = ThreadingHTTPServer(('127.0.0.1', 0), BadReceiptHandler)
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                alpha = _seed_workspace_root(
                    os.path.join(tmp, 'alpha'),
                    org_id='org_alpha',
                    user_id='user_owner_alpha',
                    host_id='host_alpha',
                    port=port_alpha,
                    signing_secret='alpha-secret',
                    peer_entries={
                        'host_beta': {
                            'label': 'Beta Host',
                            'transport': 'https',
                            'endpoint_url': f'http://127.0.0.1:{server.server_address[1]}',
                            'trust_state': 'trusted',
                            'shared_secret': 'beta-secret',
                            'admitted_org_ids': ['org_beta'],
                        },
                    },
                )
                with _run_workspace(alpha):
                    session = _issue_workspace_session(alpha)
                    request_payload = {'task': 'demo'}
                    warrant = _issue_workspace_warrant(alpha, session['token'], request_payload)
                    status, body = _http_json(
                        'POST',
                        alpha['base_url'] + '/api/federation/send',
                        payload={
                            'target_host_id': 'host_beta',
                            'target_org_id': 'org_beta',
                            'message_type': 'execution_request',
                            'payload': request_payload,
                            'warrant_id': warrant['warrant_id'],
                        },
                        headers={
                            'Authorization': f"Bearer {session['token']}",
                            'Content-Type': 'application/json',
                        },
                    )
                    self.assertEqual(status, 502, body)
                    self.assertEqual(body['case']['claim_type'], 'misrouted_execution')
                    self.assertEqual(body['case']['linked_warrant_id'], warrant['warrant_id'])
                    self.assertTrue(body['warrant']['applied'])
                    self.assertEqual(body['warrant']['warrant_id'], warrant['warrant_id'])
                    self.assertEqual(body['warrant']['court_review_state'], 'stayed')
                    self.assertEqual(BadReceiptHandler.receive_count, 1)

                    status, warrants_body = _http_json(
                        'GET',
                        alpha['base_url'] + '/api/warrants',
                        headers={'Authorization': alpha['auth_header']},
                    )
                    self.assertEqual(status, 200, warrants_body)
                    warrant_record = next(
                        item for item in warrants_body['warrants']
                        if item['warrant_id'] == warrant['warrant_id']
                    )
                    self.assertEqual(warrant_record['court_review_state'], 'stayed')

                    blocked_status, blocked_body = _http_json(
                        'POST',
                        alpha['base_url'] + '/api/federation/send',
                        payload={
                            'target_host_id': 'host_beta',
                            'target_org_id': 'org_beta',
                            'message_type': 'execution_request',
                            'payload': request_payload,
                            'warrant_id': warrant['warrant_id'],
                        },
                        headers={
                            'Authorization': f"Bearer {session['token']}",
                            'Content-Type': 'application/json',
                        },
                    )
                    self.assertEqual(blocked_status, 403, blocked_body)
                    self.assertIn('court_review_state=stayed', blocked_body['error'])
                    self.assertEqual(BadReceiptHandler.receive_count, 1)

                alpha_events = _read_jsonl(alpha['audit_log'])
                stayed = [e for e in alpha_events if e.get('action') == 'warrant_stayed_for_case']
                failed = [e for e in alpha_events if e.get('action') == 'federation_envelope_delivery_failed']
                self.assertTrue(stayed)
                self.assertEqual(stayed[-1]['resource'], warrant['warrant_id'])
                self.assertTrue(failed)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_workspace_federation_send_rejects_missing_warrant(self):
        try:
            port_alpha = _find_free_port()
            port_beta = _find_free_port()
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')

        with tempfile.TemporaryDirectory() as tmp:
            alpha = _seed_workspace_root(
                os.path.join(tmp, 'alpha'),
                org_id='org_alpha',
                user_id='user_owner_alpha',
                host_id='host_alpha',
                port=port_alpha,
                signing_secret='alpha-secret',
                peer_entries={
                    'host_beta': {
                        'label': 'Beta Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_beta}',
                        'trust_state': 'trusted',
                        'shared_secret': 'beta-secret',
                        'admitted_org_ids': ['org_beta'],
                    },
                },
            )
            beta = _seed_workspace_root(
                os.path.join(tmp, 'beta'),
                org_id='org_beta',
                user_id='user_owner_beta',
                host_id='host_beta',
                port=port_beta,
                signing_secret='beta-secret',
                peer_entries={
                    'host_alpha': {
                        'label': 'Alpha Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_alpha}',
                        'trust_state': 'trusted',
                        'shared_secret': 'alpha-secret',
                        'admitted_org_ids': ['org_alpha'],
                    },
                },
            )
            with _run_workspace(beta), _run_workspace(alpha):
                session = _issue_workspace_session(alpha)
                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/federation/send',
                    payload={
                        'target_host_id': 'host_beta',
                        'target_org_id': 'org_beta',
                        'message_type': 'execution_request',
                        'payload': {'task': 'demo'},
                    },
                    headers={
                        'Authorization': f"Bearer {session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(status, 403, body)
                self.assertIn('requires warrant_id', body['error'])

            alpha_events = _read_jsonl(alpha['audit_log'])
            beta_events = _read_jsonl(beta['audit_log'])
            blocked = [
                event for event in alpha_events
                if event.get('action') == 'federation_warrant_blocked'
            ]
            received = [
                event for event in beta_events
                if event.get('action') == 'federation_envelope_received'
            ]
            self.assertTrue(blocked)
            self.assertEqual(blocked[-1]['details']['required_action_class'], 'federated_execution')
            self.assertEqual(received, [])

    def test_workspace_federation_send_rejects_stayed_warrant(self):
        try:
            port_alpha = _find_free_port()
            port_beta = _find_free_port()
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')

        with tempfile.TemporaryDirectory() as tmp:
            alpha = _seed_workspace_root(
                os.path.join(tmp, 'alpha'),
                org_id='org_alpha',
                user_id='user_owner_alpha',
                host_id='host_alpha',
                port=port_alpha,
                signing_secret='alpha-secret',
                peer_entries={
                    'host_beta': {
                        'label': 'Beta Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_beta}',
                        'trust_state': 'trusted',
                        'shared_secret': 'beta-secret',
                        'admitted_org_ids': ['org_beta'],
                    },
                },
            )
            beta = _seed_workspace_root(
                os.path.join(tmp, 'beta'),
                org_id='org_beta',
                user_id='user_owner_beta',
                host_id='host_beta',
                port=port_beta,
                signing_secret='beta-secret',
                peer_entries={
                    'host_alpha': {
                        'label': 'Alpha Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_alpha}',
                        'trust_state': 'trusted',
                        'shared_secret': 'alpha-secret',
                        'admitted_org_ids': ['org_alpha'],
                    },
                },
            )
            with _run_workspace(beta), _run_workspace(alpha):
                session = _issue_workspace_session(alpha)
                request_payload = {'task': 'demo'}
                warrant = _issue_workspace_warrant(
                    alpha,
                    session['token'],
                    request_payload,
                    review_decision='stay',
                )
                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/federation/send',
                    payload={
                        'target_host_id': 'host_beta',
                        'target_org_id': 'org_beta',
                        'message_type': 'execution_request',
                        'payload': request_payload,
                        'warrant_id': warrant['warrant_id'],
                    },
                    headers={
                        'Authorization': f"Bearer {session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(status, 403, body)
                self.assertIn('court_review_state=stayed', body['error'])

            alpha_events = _read_jsonl(alpha['audit_log'])
            beta_events = _read_jsonl(beta['audit_log'])
            blocked = [
                event for event in alpha_events
                if event.get('action') == 'federation_warrant_blocked'
            ]
            received = [
                event for event in beta_events
                if event.get('action') == 'federation_envelope_received'
            ]
            self.assertTrue(blocked)
            self.assertEqual(blocked[-1]['details']['warrant_id'], warrant['warrant_id'])
            self.assertEqual(received, [])

    def test_upsert_peer_registry_entry_round_trips_file_backed_registry(self):
        from federation import load_peer_registry, upsert_peer_registry_entry
        from runtime_host import default_host_identity

        with tempfile.TemporaryDirectory() as tmp:
            peers_path = os.path.join(tmp, 'federation_peers.json')
            host = default_host_identity(host_id='host_alpha')
            registry = upsert_peer_registry_entry(
                peers_path,
                'host_beta',
                host_identity=host,
                label='Beta Host',
                endpoint_url='http://127.0.0.1:19014',
                shared_secret='beta-secret',
                admitted_org_ids=['org_beta', 'org_beta'],
            )
            self.assertEqual(registry['host_id'], 'host_alpha')
            self.assertEqual(registry['trusted_peer_ids'], ['host_beta'])

            reloaded = load_peer_registry(peers_path, host_identity=host)
            peer = reloaded['peers']['host_beta']
            self.assertEqual(peer.label, 'Beta Host')
            self.assertEqual(peer.receive_url, 'http://127.0.0.1:19014/api/federation/receive')
            self.assertEqual(peer.admitted_org_ids, ['org_beta'])

    def test_refresh_peer_registry_entry_persists_capability_snapshot(self):
        from federation import refresh_peer_registry_entry, upsert_peer_registry_entry
        from runtime_host import default_host_identity

        with tempfile.TemporaryDirectory() as tmp:
            peers_path = os.path.join(tmp, 'federation_peers.json')
            host = default_host_identity(
                host_id='host_alpha',
                federation_enabled=True,
                peer_transport='https',
            )
            upsert_peer_registry_entry(
                peers_path,
                'host_beta',
                host_identity=host,
                label='Beta Host',
                endpoint_url='http://127.0.0.1:19015',
                shared_secret='beta-secret',
                admitted_org_ids=['org_beta'],
            )
            registry = refresh_peer_registry_entry(
                peers_path,
                'host_beta',
                host_identity=host,
                http_get=lambda _url: {
                    'manifest_version': 1,
                    'host_identity': {'host_id': 'host_beta'},
                    'admission': {'admitted_org_ids': ['org_beta']},
                    'service_registry': {
                        'federation_gateway': {
                            'identity_model': 'signed_host_service',
                            'supports_institution_routing': True,
                        },
                    },
                    'federation': {
                        'enabled': True,
                        'boundary_name': 'federation_gateway',
                        'identity_model': 'signed_host_service',
                    },
                },
                target_org_id='org_beta',
            )
            peer = registry['peers']['host_beta']
            self.assertTrue(peer.last_refreshed_at)
            self.assertEqual(peer.capability_snapshot['manifest_version'], 1)
            self.assertEqual(
                peer.capability_snapshot['federation']['boundary_name'],
                'federation_gateway',
            )

    def test_set_peer_trust_state_updates_snapshot_and_send_enabled(self):
        from federation import (
            FederationAuthority,
            set_peer_trust_state,
            upsert_peer_registry_entry,
        )
        from runtime_host import default_host_identity

        with tempfile.TemporaryDirectory() as tmp:
            peers_path = os.path.join(tmp, 'federation_peers.json')
            host = default_host_identity(
                host_id='host_alpha',
                federation_enabled=True,
                peer_transport='https',
            )
            registry = upsert_peer_registry_entry(
                peers_path,
                'host_beta',
                host_identity=host,
                endpoint_url='http://127.0.0.1:19015',
                shared_secret='beta-secret',
                admitted_org_ids=['org_beta'],
            )
            authority = FederationAuthority(host, signing_secret='alpha-secret', peer_registry=registry)
            self.assertTrue(authority.snapshot(bound_org_id='org_alpha')['send_enabled'])

            suspended = set_peer_trust_state(
                peers_path,
                'host_beta',
                'suspended',
                host_identity=host,
            )
            suspended_snapshot = FederationAuthority(
                host,
                signing_secret='alpha-secret',
                peer_registry=suspended,
            ).snapshot(bound_org_id='org_alpha')
            self.assertEqual(suspended_snapshot['trusted_peer_ids'], [])
            self.assertEqual(suspended_snapshot['all_peer_count'], 1)
            self.assertFalse(suspended_snapshot['send_enabled'])

    def test_preflight_delivery_validates_peer_manifest(self):
        from federation import FederationAuthority, FederationPeer
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(
            host,
            signing_secret='alpha-secret',
            peer_registry={
                'source': 'test',
                'host_id': 'host_alpha',
                'trusted_peer_ids': ['host_beta'],
                'peers': {
                    'host_beta': FederationPeer(
                        'host_beta',
                        transport='https',
                        endpoint_url='http://127.0.0.1:19017',
                        trust_state='trusted',
                        shared_secret='beta-secret',
                        admitted_org_ids=['org_beta'],
                    ),
                },
            },
        )

        manifest = authority.preflight_delivery(
            'host_beta',
            'org_beta',
            http_get=lambda _url: {
                'host_identity': {
                    'host_id': 'host_beta',
                    'role': 'institution_host',
                },
                'admission': {
                    'admitted_org_ids': ['org_beta'],
                },
                'service_registry': {
                    'federation_gateway': {
                        'identity_model': 'signed_host_service',
                        'supports_institution_routing': True,
                    },
                },
                'federation': {
                    'enabled': True,
                    'boundary_name': 'federation_gateway',
                    'identity_model': 'signed_host_service',
                },
            },
        )
        self.assertEqual(manifest['host_identity']['host_id'], 'host_beta')

    def test_preflight_delivery_rejects_manifest_without_target_org(self):
        from federation import FederationAuthority, FederationDeliveryError, FederationPeer
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        authority = FederationAuthority(
            host,
            signing_secret='alpha-secret',
            peer_registry={
                'source': 'test',
                'host_id': 'host_alpha',
                'trusted_peer_ids': ['host_beta'],
                'peers': {
                    'host_beta': FederationPeer(
                        'host_beta',
                        transport='https',
                        endpoint_url='http://127.0.0.1:19018',
                        trust_state='trusted',
                        shared_secret='beta-secret',
                        admitted_org_ids=['org_beta'],
                    ),
                },
            },
        )

        with self.assertRaises(FederationDeliveryError):
            authority.preflight_delivery(
                'host_beta',
                'org_gamma',
                http_get=lambda _url: {
                    'host_identity': {
                        'host_id': 'host_beta',
                        'role': 'institution_host',
                    },
                    'admission': {
                        'admitted_org_ids': ['org_beta'],
                    },
                    'service_registry': {
                        'federation_gateway': {
                            'identity_model': 'signed_host_service',
                            'supports_institution_routing': True,
                        },
                    },
                    'federation': {
                        'enabled': True,
                        'boundary_name': 'federation_gateway',
                        'identity_model': 'signed_host_service',
                    },
                },
            )

    def test_snapshot_reports_disabled_without_signing_secret(self):
        from federation import FederationAuthority
        from runtime_host import default_host_identity

        host = default_host_identity(
            host_id='host_alpha',
            federation_enabled=True,
            peer_transport='https',
        )
        snapshot = FederationAuthority(host, signing_secret=None).snapshot(bound_org_id='org_alpha')
        self.assertFalse(snapshot['enabled'])
        self.assertEqual(snapshot['disabled_reason'], 'signing_secret_missing')

    def test_load_peer_registry_rejects_trusted_peer_without_secret(self):
        from federation import load_peer_registry
        from runtime_host import default_host_identity

        with tempfile.TemporaryDirectory() as tmp:
            peers_path = os.path.join(tmp, 'federation_peers.json')
            with open(peers_path, 'w') as f:
                json.dump({
                    'host_id': 'host_alpha',
                    'peers': {
                        'host_beta': {
                            'trust_state': 'trusted',
                            'transport': 'https',
                        }
                    },
                }, f)
            with self.assertRaises(RuntimeError):
                load_peer_registry(peers_path, host_identity=default_host_identity(host_id='host_alpha'))

    def test_workspace_payout_execution_is_warrant_bound_over_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            alpha = _seed_workspace_root(
                os.path.join(tmp, 'alpha'),
                org_id='org_alpha',
                user_id='user_alpha',
                host_id='host_alpha',
                port=_find_free_port(),
                signing_secret='alpha-secret',
            )

            economy_dir = os.path.join(alpha['root'], 'economy')
            with open(os.path.join(economy_dir, 'ledger.json')) as f:
                ledger = json.load(f)
            ledger['treasury']['cash_usd'] = 140.0
            ledger['treasury']['reserve_floor_usd'] = 50.0
            ledger['treasury']['expenses_recorded_usd'] = 0.0
            _write_json(os.path.join(economy_dir, 'ledger.json'), ledger)
            _write_json(os.path.join(economy_dir, 'wallets.json'), {
                'wallets': {
                    'wallet_alpha': {
                        'id': 'wallet_alpha',
                        'verification_level': 3,
                        'verification_label': 'self_custody_verified',
                        'payout_eligible': True,
                        'status': 'active',
                    },
                },
                'verification_levels': {},
            })
            _write_json(os.path.join(economy_dir, 'contributors.json'), {
                'contributors': {
                    'contrib_alpha': {
                        'id': 'contrib_alpha',
                        'name': 'Contributor Alpha',
                        'payout_wallet_id': 'wallet_alpha',
                    },
                },
                'contribution_types': ['code'],
                'registration_requirements': {},
            })
            _write_json(os.path.join(economy_dir, 'payout_proposals.json'), {
                'proposals': {
                    'ppo_ready': {
                        'proposal_id': 'ppo_ready',
                        'id': 'ppo_ready',
                        'institution_id': 'org_alpha',
                        'contributor_id': 'contrib_alpha',
                        'contributor_name': 'Contributor Alpha',
                        'amount_usd': 12.0,
                        'currency': 'USDC',
                        'contribution_type': 'code',
                        'evidence': {'description': 'seeded integration proof'},
                        'recipient_wallet_id': 'wallet_alpha',
                        'proposed_by': 'user_seed',
                        'reviewed_by': 'user_reviewer',
                        'approved_by': 'user_owner',
                        'status': 'dispute_window',
                        'created_at': '2026-03-20T00:00:00Z',
                        'updated_at': '2026-03-20T00:00:00Z',
                        'submitted_at': '2026-03-20T00:00:00Z',
                        'reviewed_at': '2026-03-20T00:10:00Z',
                        'approved_at': '2026-03-20T00:20:00Z',
                        'dispute_window_started_at': '2026-03-20T00:20:00Z',
                        'dispute_window_ends_at': '2026-03-20T00:20:00Z',
                        'executed_at': '',
                        'executed_by': '',
                        'tx_hash': '',
                        'warrant_id': '',
                        'settlement_adapter': 'internal_ledger',
                        'execution_refs': {},
                        'note': '',
                        'metadata': {},
                    },
                },
            })

            with _run_workspace(alpha):
                session = _issue_workspace_session(alpha)
                token = session['token']
                bearer_headers = {
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json',
                }

                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/payouts/propose',
                    payload={
                        'contributor_id': 'contrib_alpha',
                        'amount_usd': 3.0,
                        'contribution_type': 'code',
                        'evidence': {'description': 'fresh API proposal'},
                        'recipient_wallet_id': 'wallet_alpha',
                    },
                    headers=bearer_headers,
                )
                self.assertEqual(status, 200)
                self.assertEqual(body['proposal']['status'], 'draft')

                request_payload = {
                    'proposal_id': 'ppo_ready',
                    'settlement_adapter': 'internal_ledger',
                    'tx_hash': 'tx_alpha_demo',
                }
                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/warrants/issue',
                    payload={
                        'action_class': 'payout_execution',
                        'boundary_name': 'payouts',
                        'request_payload': request_payload,
                        'risk_class': 'high',
                    },
                    headers=bearer_headers,
                )
                self.assertEqual(status, 200)
                warrant_id = body['warrant']['warrant_id']
                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/warrants/approve',
                    payload={'warrant_id': warrant_id},
                    headers=bearer_headers,
                )
                self.assertEqual(status, 200)

                status, body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/payouts/execute',
                    payload={
                        **request_payload,
                        'warrant_id': warrant_id,
                    },
                    headers=bearer_headers,
                )
                self.assertEqual(status, 200)
                self.assertEqual(body['proposal']['status'], 'executed')
                self.assertEqual(body['proposal']['warrant_id'], warrant_id)
                self.assertEqual(body['warrant']['execution_state'], 'executed')
                self.assertEqual(body['proposal']['execution_refs']['proof_type'], 'ledger_transaction')
                self.assertEqual(body['proposal']['execution_refs']['verification_state'], 'host_ledger_final')

                status, payouts = _http_json(
                    'GET',
                    alpha['base_url'] + '/api/payouts',
                    headers={'Authorization': f'Bearer {token}'},
                )
                self.assertEqual(status, 200)
                self.assertEqual(payouts['summary']['executed'], 1)
                self.assertGreaterEqual(payouts['summary']['total'], 2)
                self.assertEqual(
                    payouts['settlement_adapter_summary']['default_payout_adapter'],
                    'internal_ledger',
                )

            with open(os.path.join(economy_dir, 'ledger.json')) as f:
                ledger = json.load(f)
            self.assertAlmostEqual(ledger['treasury']['cash_usd'], 128.0, places=2)
            self.assertAlmostEqual(ledger['treasury']['expenses_recorded_usd'], 12.0, places=2)

            tx_rows = _read_jsonl(os.path.join(economy_dir, 'transactions.jsonl'))
            self.assertEqual(tx_rows[-1]['type'], 'payout_execution')
            self.assertEqual(tx_rows[-1]['proposal_id'], 'ppo_ready')
            self.assertEqual(tx_rows[-1]['tx_hash'], 'tx_alpha_demo')
            self.assertEqual(tx_rows[-1]['verification_state'], 'host_ledger_final')

            audit_rows = _read_jsonl(alpha['audit_log'])
            actions = [row.get('action') for row in audit_rows]
            self.assertIn('payout_proposal_created', actions)
            self.assertIn('payout_executed', actions)


if __name__ == '__main__':
    unittest.main()
