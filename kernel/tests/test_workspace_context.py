#!/usr/bin/env python3
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


class WorkspaceContextTests(unittest.TestCase):
    def setUp(self):
        self.workspace = _load_workspace('kernel_workspace_context_test')
        self.orig_workspace_org_id = self.workspace.WORKSPACE_ORG_ID
        self.orig_get_founding_org = self.workspace._get_founding_org
        self.orig_load_orgs = self.workspace.load_orgs
        self.orig_load_workspace_credentials = self.workspace._load_workspace_credentials

    def tearDown(self):
        self.workspace.WORKSPACE_ORG_ID = self.orig_workspace_org_id
        self.workspace._get_founding_org = self.orig_get_founding_org
        self.workspace.load_orgs = self.orig_load_orgs
        self.workspace._load_workspace_credentials = self.orig_load_workspace_credentials

    def test_configured_org_binds_process_context(self):
        self.workspace._load_workspace_credentials = lambda: (None, None, None, None)
        self.workspace.WORKSPACE_ORG_ID = 'org_b'
        self.workspace.load_orgs = lambda: {
            'organizations': {
                'org_a': {'id': 'org_a', 'slug': 'a', 'name': 'A'},
                'org_b': {'id': 'org_b', 'slug': 'b', 'name': 'B'},
            }
        }
        org_id, org, source = self.workspace._resolve_workspace_context()
        self.assertEqual(org_id, 'org_b')
        self.assertEqual(org.get('slug'), 'b')
        self.assertEqual(source, 'configured_org')

    def test_credential_scoped_org_binds_process_context(self):
        self.workspace._load_workspace_credentials = lambda: ('owner', 'secret', 'org_b', None)
        self.workspace.load_orgs = lambda: {
            'organizations': {
                'org_a': {'id': 'org_a', 'slug': 'a', 'name': 'A'},
                'org_b': {'id': 'org_b', 'slug': 'b', 'name': 'B'},
            }
        }
        org_id, org, source = self.workspace._resolve_workspace_context()
        self.assertEqual(org_id, 'org_b')
        self.assertEqual(org.get('slug'), 'b')
        self.assertEqual(source, 'credentials_org')

    def test_credential_scope_conflict_is_rejected(self):
        self.workspace._load_workspace_credentials = lambda: ('owner', 'secret', 'org_a', None)
        self.workspace.WORKSPACE_ORG_ID = 'org_b'
        with self.assertRaises(RuntimeError):
            self.workspace._resolve_workspace_context()

    def test_request_override_must_match_bound_org(self):
        with self.assertRaises(ValueError):
            self.workspace._enforce_request_context(
                urlparse('/api/status?org_id=org_other'),
                _Headers(),
                'org_a',
            )

        context = self.workspace._enforce_request_context(
            urlparse('/api/status?org_id=org_a'),
            _Headers({'X-Meridian-Org-Id': 'org_a'}),
            'org_a',
        )
        self.assertEqual(context['requested_org_id'], 'org_a')
        self.assertEqual(context['bound_org_id'], 'org_a')

    def test_auth_context_reports_credential_binding(self):
        self.workspace._load_workspace_credentials = lambda: ('owner', 'secret', 'org_a', None)
        auth = self.workspace._resolve_auth_context('org_a')
        self.assertEqual(auth['mode'], 'credential_bound')
        self.assertEqual(auth['org_id'], 'org_a')
        self.assertEqual(auth['actor_id'], 'workspace_user:owner')

    def test_auth_context_prefers_explicit_user_id(self):
        self.workspace._load_workspace_credentials = lambda: ('owner', 'secret', 'org_a', 'user_meridian_owner')
        self.workspace.load_orgs = lambda: {
            'organizations': {
                'org_a': {
                    'id': 'org_a',
                    'slug': 'a',
                    'name': 'A',
                    'owner_id': 'user_meridian_owner',
                    'members': [{'user_id': 'user_meridian_owner', 'role': 'owner'}],
                },
            }
        }
        auth = self.workspace._resolve_auth_context('org_a')
        self.assertEqual(auth['actor_id'], 'user_meridian_owner')
        self.assertEqual(auth['actor_source'], 'credentials')
        self.assertEqual(auth['role'], 'owner')

    def test_auth_context_resolves_owner_alias_role(self):
        self.workspace._load_workspace_credentials = lambda: ('owner', 'secret', 'org_a', None)
        self.workspace.load_orgs = lambda: {
            'organizations': {
                'org_a': {
                    'id': 'org_a',
                    'slug': 'a',
                    'name': 'A',
                    'owner_id': 'user_owner',
                    'members': [{'user_id': 'user_owner', 'role': 'owner'}],
                },
            }
        }
        auth = self.workspace._resolve_auth_context('org_a')
        self.assertEqual(auth['user_id'], 'user_owner')
        self.assertEqual(auth['role'], 'owner')
        self.assertEqual(auth['actor_source'], 'owner_alias')

    def test_mutation_authorization_requires_admin_for_kill_switch(self):
        auth = {'enabled': True, 'role': 'member'}
        with self.assertRaises(PermissionError):
            self.workspace._enforce_mutation_authorization(auth, 'org_a', '/api/authority/kill-switch')

    def test_mutation_authorization_allows_member_request(self):
        auth = {'enabled': True, 'role': 'member'}
        required = self.workspace._enforce_mutation_authorization(auth, 'org_a', '/api/authority/request')
        self.assertEqual(required, 'member')


if __name__ == '__main__':
    unittest.main()
