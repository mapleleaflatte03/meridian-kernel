#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(THIS_DIR, '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, THIS_DIR)

from adapters import openclaw_compatible as openclaw_adapter  # noqa: E402
from test_federation import (  # noqa: E402
    _find_free_port,
    _http_json,
    _issue_workspace_session,
    _issue_workspace_warrant,
    _read_jsonl,
    _run_workspace,
    _seed_workspace_root,
)


class OpenClawFederationProofTests(unittest.TestCase):
    def setUp(self):
        self.orig_check_authority = openclaw_adapter.check_authority
        self.orig_check_budget = openclaw_adapter.check_budget
        self.orig_get_restrictions = openclaw_adapter.get_restrictions
        self.orig_meter_record = openclaw_adapter.meter_record
        self.orig_log_event = openclaw_adapter.log_event

    def tearDown(self):
        openclaw_adapter.check_authority = self.orig_check_authority
        openclaw_adapter.check_budget = self.orig_check_budget
        openclaw_adapter.get_restrictions = self.orig_get_restrictions
        openclaw_adapter.meter_record = self.orig_meter_record
        openclaw_adapter.log_event = self.orig_log_event

    def test_openclaw_reference_adapter_wraps_three_host_federation_execution(self):
        try:
            port_alpha = _find_free_port()
            port_beta = _find_free_port()
            port_gamma = _find_free_port()
        except PermissionError as exc:
            self.skipTest(f'localhost socket bind unavailable in sandbox: {exc}')

        seen = {}
        openclaw_adapter.get_restrictions = lambda agent_id, org_id=None: []
        openclaw_adapter.check_authority = lambda agent_id, action_type, org_id=None: (True, 'ok')
        openclaw_adapter.check_budget = lambda agent_id, cost_usd, org_id=None: (True, 'ok')
        openclaw_adapter.meter_record = lambda org_id, agent_id, metric, quantity=1.0, unit='calls', cost_usd=0.0, run_id='', details=None: (
            seen.setdefault('meter', {
                'org_id': org_id,
                'agent_id': agent_id,
                'metric': metric,
                'quantity': quantity,
                'unit': unit,
                'cost_usd': cost_usd,
                'run_id': run_id,
                'details': details or {},
            }) or 'meter_openclaw_ref'
        )
        openclaw_adapter.log_event = lambda org_id, agent_id, action, resource='', outcome='success', actor_type='agent', details=None, policy_ref='', session_id=None: (
            seen.setdefault('audit', {
                'org_id': org_id,
                'agent_id': agent_id,
                'action': action,
                'resource': resource,
                'outcome': outcome,
                'actor_type': actor_type,
                'details': details or {},
                'session_id': session_id,
            }) or 'event_openclaw_ref'
        )

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
                    'host_gamma': {
                        'label': 'Gamma Witness',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_gamma}',
                        'trust_state': 'trusted',
                        'shared_secret': 'gamma-secret',
                        'witness_archive_user': 'gamma-user',
                        'witness_archive_pass': 'gamma-pass',
                        'admitted_org_ids': ['org_gamma'],
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
                    'host_gamma': {
                        'label': 'Gamma Witness',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_gamma}',
                        'trust_state': 'trusted',
                        'shared_secret': 'gamma-secret',
                        'witness_archive_user': 'gamma-user',
                        'witness_archive_pass': 'gamma-pass',
                        'admitted_org_ids': ['org_gamma'],
                    },
                },
            )
            gamma = _seed_workspace_root(
                os.path.join(tmp, 'gamma'),
                org_id='org_gamma',
                user_id='user_witness_gamma',
                host_id='host_gamma',
                port=port_gamma,
                signing_secret='gamma-secret',
                host_role='witness_host',
                peer_entries={
                    'host_alpha': {
                        'label': 'Alpha Host',
                        'transport': 'https',
                        'endpoint_url': f'http://127.0.0.1:{port_alpha}',
                        'trust_state': 'trusted',
                        'shared_secret': 'alpha-secret',
                        'admitted_org_ids': ['org_alpha'],
                    },
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

            with _run_workspace(gamma), _run_workspace(beta), _run_workspace(alpha):
                alpha_session = _issue_workspace_session(alpha)
                adapter_envelope = openclaw_adapter.build_action_envelope(
                    'atlas',
                    'federated_execution',
                    'host_beta/shared_brief_review',
                    0.10,
                    run_id='run_three_host_proof',
                    session_id=alpha_session['token'][:16],
                    details={
                        'message_type': 'execution_request',
                        'target_host_id': 'host_beta',
                        'target_institution_id': 'org_beta',
                    },
                )
                action_gate = openclaw_adapter.pre_action_check('org_alpha', adapter_envelope)
                self.assertTrue(action_gate['allowed'])
                self.assertEqual(action_gate['stage'], 'ok')

                proposal_payload = {
                    'summary': 'Shared competitor brief',
                    'terms_payload': {'scope': 'shared-brief'},
                }
                proposal_warrant = _issue_workspace_warrant(
                    alpha,
                    alpha_session['token'],
                    proposal_payload,
                    action_class='cross_institution_commitment',
                )
                proposal_status, proposal_body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/commitments/propose',
                    payload={
                        'target_host_id': 'host_beta',
                        'target_institution_id': 'org_beta',
                        'summary': proposal_payload['summary'],
                        'terms_payload': proposal_payload['terms_payload'],
                        'warrant_id': proposal_warrant['warrant_id'],
                        'federate': True,
                    },
                    headers={
                        'Authorization': f"Bearer {alpha_session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(proposal_status, 200, proposal_body)
                self.assertEqual(proposal_body['delivery']['claims']['message_type'], 'commitment_proposal')
                self.assertEqual(proposal_body['delivery']['witness_archive']['created'], 1)
                commitment_id = proposal_body['commitment']['commitment_id']
                self.assertEqual(
                    proposal_body['delivery']['claims']['commitment_id'],
                    commitment_id,
                )
                adapter_envelope['details']['commitment_id'] = commitment_id
                execution_request_payload = {
                    'task': 'shared brief review',
                    'adapter_envelope': adapter_envelope,
                }

                beta_session = _issue_workspace_session(beta)
                acceptance_warrant = _issue_workspace_warrant(
                    beta,
                    beta_session['token'],
                    {'note': 'Beta accepts'},
                    action_class='cross_institution_commitment',
                )
                acceptance_status, acceptance_body = _http_json(
                    'POST',
                    beta['base_url'] + '/api/commitments/accept',
                    payload={
                        'commitment_id': commitment_id,
                        'note': 'Beta accepts',
                        'warrant_id': acceptance_warrant['warrant_id'],
                        'federate': True,
                    },
                    headers={
                        'Authorization': f"Bearer {beta_session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(acceptance_status, 200, acceptance_body)
                self.assertEqual(acceptance_body['delivery']['claims']['message_type'], 'commitment_acceptance')
                self.assertEqual(acceptance_body['delivery']['witness_archive']['created'], 1)

                execution_warrant = _issue_workspace_warrant(
                    alpha,
                    alpha_session['token'],
                    execution_request_payload,
                    action_class='federated_execution',
                )
                execution_status, execution_body = _http_json(
                    'POST',
                    alpha['base_url'] + '/api/federation/send',
                    payload={
                        'target_host_id': 'host_beta',
                        'target_org_id': 'org_beta',
                        'message_type': 'execution_request',
                        'payload': execution_request_payload,
                        'warrant_id': execution_warrant['warrant_id'],
                    },
                    headers={
                        'Authorization': f"Bearer {alpha_session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(execution_status, 200, execution_body)
                self.assertEqual(execution_body['delivery']['claims']['message_type'], 'execution_request')
                self.assertEqual(execution_body['delivery']['witness_archive']['created'], 1)

                post_record = openclaw_adapter.post_action_record(
                    'org_alpha',
                    dict(adapter_envelope, details={
                        **adapter_envelope['details'],
                        'federation_envelope_id': execution_body['delivery']['claims']['envelope_id'],
                        'receiver_host_id': execution_body['delivery']['receipt']['receiver_host_id'],
                    }),
                    actual_cost_usd=0.04,
                    outcome='success',
                    actor_type='agent',
                )
                self.assertEqual(post_record['cost_usd'], 0.04)
                self.assertEqual(seen['meter']['org_id'], 'org_alpha')
                self.assertEqual(seen['meter']['metric'], 'runtime_action')
                self.assertEqual(seen['audit']['action'], 'federated_execution')
                self.assertEqual(seen['audit']['resource'], 'host_beta/shared_brief_review')

                jobs_status, jobs_body = _http_json(
                    'GET',
                    beta['base_url'] + '/api/federation/execution-jobs',
                    headers={'Authorization': beta['auth_header']},
                )
                self.assertEqual(jobs_status, 200, jobs_body)
                self.assertEqual(jobs_body['summary']['pending_local_warrant'], 1)
                local_warrant_id = jobs_body['jobs'][0]['local_warrant_id']

                review_status, review_body = _http_json(
                    'POST',
                    beta['base_url'] + '/api/warrants/stay',
                    payload={
                        'warrant_id': local_warrant_id,
                        'note': 'Receiver hold pending local review',
                    },
                    headers={'Authorization': beta['auth_header']},
                )
                self.assertEqual(review_status, 200, review_body)
                self.assertEqual(review_body['court_notice']['court_notice']['decision'], 'stay')
                self.assertEqual(review_body['court_notice']['delivery']['witness_archive']['created'], 1)

                breach_warrant = _issue_workspace_warrant(
                    beta,
                    beta_session['token'],
                    {'note': 'Breach recorded after failed review'},
                    action_class='cross_institution_commitment',
                )
                breach_status, breach_body = _http_json(
                    'POST',
                    beta['base_url'] + '/api/commitments/breach',
                    payload={
                        'commitment_id': commitment_id,
                        'note': 'Breach recorded after failed review',
                        'warrant_id': breach_warrant['warrant_id'],
                        'federate': True,
                    },
                    headers={
                        'Authorization': f"Bearer {beta_session['token']}",
                        'Content-Type': 'application/json',
                    },
                )
                self.assertEqual(breach_status, 200, breach_body)
                self.assertEqual(
                    breach_body['delivery']['response']['processing']['federation_peer']['trust_state'],
                    'suspended',
                )
                self.assertEqual(breach_body['delivery']['witness_archive']['created'], 1)

                alpha_cases_status, alpha_cases_body = _http_json(
                    'GET',
                    alpha['base_url'] + '/api/cases',
                    headers={'Authorization': alpha['auth_header']},
                )
                self.assertEqual(alpha_cases_status, 200, alpha_cases_body)
                self.assertEqual(alpha_cases_body['blocking_commitment_ids'], [commitment_id])
                self.assertEqual(alpha_cases_body['blocked_peer_host_ids'], ['host_beta'])

                gamma_archive_status, gamma_archive_body = _http_json(
                    'GET',
                    gamma['base_url'] + '/api/federation/witness/archive',
                    headers={'Authorization': gamma['auth_header']},
                )
                self.assertEqual(gamma_archive_status, 200, gamma_archive_body)
                self.assertEqual(gamma_archive_body['summary']['total'], 5)
                self.assertEqual(
                    gamma_archive_body['summary']['message_type_counts'],
                    {
                        'commitment_acceptance': 1,
                        'commitment_breach_notice': 1,
                        'commitment_proposal': 1,
                        'court_notice': 1,
                        'execution_request': 1,
                    },
                )

            alpha_events = _read_jsonl(alpha['audit_log'])
            beta_events = _read_jsonl(beta['audit_log'])
            gamma_events = _read_jsonl(gamma['audit_log'])
            self.assertTrue(
                any(event.get('action') == 'federation_commitment_breach_notice_recorded' for event in alpha_events)
            )
            self.assertTrue(
                any(event.get('action') == 'federation_witness_archive_sent' for event in beta_events)
            )
            self.assertGreaterEqual(
                len([event for event in gamma_events if event.get('action') == 'federation_witness_observation_archived']),
                5,
            )


if __name__ == '__main__':
    unittest.main()
