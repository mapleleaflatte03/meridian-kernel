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


if __name__ == '__main__':
    unittest.main()
