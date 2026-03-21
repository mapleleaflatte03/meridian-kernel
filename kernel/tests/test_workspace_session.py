#!/usr/bin/env python3
"""Tests for session integration in the workspace."""
import importlib.util
import os
import unittest
from urllib.parse import urlparse


ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
WORKSPACE_PY = os.path.join(ROOT, 'workspace.py')


def _load_workspace(name):
    spec = importlib.util.spec_from_file_location(name, WORKSPACE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class WorkspaceSessionAuthContextTests(unittest.TestCase):
    def setUp(self):
        self.ws = _load_workspace('kernel_workspace_session_test')
        self.orig_load_orgs = self.ws.load_orgs
        self.ws.load_orgs = lambda: {
            'organizations': {
                'org_a': {
                    'id': 'org_a',
                    'slug': 'a',
                    'name': 'A',
                    'owner_id': 'user_owner',
                    'members': [
                        {'user_id': 'user_owner', 'role': 'owner'},
                        {'user_id': 'user_m', 'role': 'member'},
                    ],
                },
            }
        }

    def tearDown(self):
        self.ws.load_orgs = self.orig_load_orgs

    def test_session_auth_context_from_claims(self):
        sa = self.ws._session_authority
        token = sa.issue('org_a', 'user_owner', 'owner')
        claims = sa.validate(token)
        ctx = self.ws._resolve_auth_context_from_session(claims, 'org_a')
        self.assertTrue(ctx['enabled'])
        self.assertEqual(ctx['mode'], 'session_bound')
        self.assertEqual(ctx['org_id'], 'org_a')
        self.assertEqual(ctx['user_id'], 'user_owner')
        self.assertEqual(ctx['role'], 'owner')
        self.assertEqual(ctx['actor_source'], 'session')
        self.assertIn('session_id', ctx)

    def test_session_auth_context_rejects_wrong_org(self):
        sa = self.ws._session_authority
        token = sa.issue('org_other', 'user_1', 'member')
        claims = sa.validate(token)
        with self.assertRaises(ValueError):
            self.ws._resolve_auth_context_from_session(claims, 'org_a')

    def test_session_auth_context_uses_live_membership_role(self):
        """If a member's role changed since session issuance, use the current role."""
        sa = self.ws._session_authority
        # Issue as owner but the member list says user_m is 'member'
        token = sa.issue('org_a', 'user_m', 'owner')
        claims = sa.validate(token)
        ctx = self.ws._resolve_auth_context_from_session(claims, 'org_a')
        # Live membership says 'member', not 'owner'
        self.assertEqual(ctx['role'], 'member')

    def test_session_auth_context_returns_none_role_for_removed_member(self):
        """A session for a removed user gets role=None (blocks mutations)."""
        sa = self.ws._session_authority
        token = sa.issue('org_a', 'user_removed', 'member')
        claims = sa.validate(token)
        ctx = self.ws._resolve_auth_context_from_session(claims, 'org_a')
        self.assertIsNone(ctx['role'])

    def test_permission_snapshot_includes_session_paths(self):
        auth = {'enabled': True, 'role': 'admin'}
        perms = self.ws._permission_snapshot(auth)['mutation_paths']
        self.assertIn('/api/session/issue', perms)
        self.assertIn('/api/session/revoke', perms)
        self.assertTrue(perms['/api/session/issue']['allowed'])
        self.assertTrue(perms['/api/session/revoke']['allowed'])

    def test_member_can_issue_but_not_revoke(self):
        auth = {'enabled': True, 'role': 'member'}
        perms = self.ws._permission_snapshot(auth)['mutation_paths']
        self.assertTrue(perms['/api/session/issue']['allowed'])
        self.assertFalse(perms['/api/session/revoke']['allowed'])

    def test_session_authority_exists_at_module_level(self):
        """Workspace module creates a process-level SessionAuthority."""
        sa = self.ws._session_authority
        self.assertIsNotNone(sa)
        # Should be able to issue and validate
        token = sa.issue('org_test', 'user_test', 'member')
        claims = sa.validate(token)
        self.assertIsNotNone(claims)
        self.assertEqual(claims.org_id, 'org_test')


class WorkspaceSessionTokenFlowTests(unittest.TestCase):
    """End-to-end session token lifecycle via workspace module functions."""

    def setUp(self):
        self.ws = _load_workspace('kernel_workspace_session_flow_test')
        self.orig_load_orgs = self.ws.load_orgs
        self.ws.load_orgs = lambda: {
            'organizations': {
                'org_a': {
                    'id': 'org_a',
                    'slug': 'a',
                    'name': 'A',
                    'owner_id': 'user_owner',
                    'members': [
                        {'user_id': 'user_owner', 'role': 'owner'},
                    ],
                },
            }
        }

    def tearDown(self):
        self.ws.load_orgs = self.orig_load_orgs

    def test_issue_validate_revoke_lifecycle(self):
        sa = self.ws._session_authority
        # Issue
        token = sa.issue('org_a', 'user_owner', 'owner')
        # Validate
        claims = sa.validate(token, expected_org_id='org_a')
        self.assertIsNotNone(claims)
        self.assertEqual(claims.user_id, 'user_owner')
        self.assertEqual(claims.role, 'owner')
        # Auth context from session
        ctx = self.ws._resolve_auth_context_from_session(claims, 'org_a')
        self.assertEqual(ctx['mode'], 'session_bound')
        self.assertEqual(ctx['role'], 'owner')
        # Mutation authorization should pass for owner-level paths
        required = self.ws._enforce_mutation_authorization(ctx, 'org_a', '/api/treasury/contribute')
        self.assertEqual(required, 'owner')
        # Revoke
        sa.revoke(claims.session_id)
        self.assertIsNone(sa.validate(token))

    def test_session_mutation_auth_blocks_insufficient_role(self):
        """Session-derived auth context correctly blocks mutations above the actor's role."""
        self.ws.load_orgs = lambda: {
            'organizations': {
                'org_a': {
                    'id': 'org_a',
                    'slug': 'a',
                    'name': 'A',
                    'owner_id': 'user_owner',
                    'members': [
                        {'user_id': 'user_member', 'role': 'member'},
                    ],
                },
            }
        }
        sa = self.ws._session_authority
        token = sa.issue('org_a', 'user_member', 'member')
        claims = sa.validate(token)
        ctx = self.ws._resolve_auth_context_from_session(claims, 'org_a')
        with self.assertRaises(PermissionError):
            self.ws._enforce_mutation_authorization(ctx, 'org_a', '/api/authority/kill-switch')


if __name__ == '__main__':
    unittest.main()
