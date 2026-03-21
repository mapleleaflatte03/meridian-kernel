"""
Institution-owned state capsule -- isolation boundary for governed institutions.

Each institution owns a capsule: a directory containing all of its governance
state (ledger, revenue, authority queue, court records, metering, transactions,
policies, phase state).  The capsule is the unit of multi-tenant isolation.

When org_id is None, paths resolve to the legacy shared economy/ directory
for backward compatibility with single-tenant deployments.
"""

import os

# -- Path layout -------------------------------------------------------------
# Capsules live under <workspace>/capsules/<org_id>/
# The economy/ directory at workspace root is the "default capsule" for
# single-tenant backward compatibility.

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKSPACE = os.path.dirname(_THIS_DIR)
ECONOMY_DIR = os.path.join(_WORKSPACE, 'economy')
CAPSULES_DIR = os.path.join(_WORKSPACE, 'capsules')

# Files every capsule contains
CAPSULE_FILES = (
    'ledger.json',
    'revenue.json',
    'authority_queue.json',
    'court_records.json',
    'metering.jsonl',
    'transactions.jsonl',
    'policies.json',
    'phase_state.json',
)


def capsule_path(org_id, filename):
    """Resolve a state file path for an institution.

    If *org_id* is ``None``, returns the legacy path under economy/ so that
    existing single-tenant code keeps working unchanged.  Otherwise returns
    the path inside the institution's capsule directory.
    """
    if org_id is None:
        return os.path.join(ECONOMY_DIR, filename)
    return os.path.join(CAPSULES_DIR, org_id, filename)


def capsule_dir(org_id):
    """Return the capsule directory for an institution (or ECONOMY_DIR if None)."""
    if org_id is None:
        return ECONOMY_DIR
    return os.path.join(CAPSULES_DIR, org_id)


def ensure_capsule(org_id):
    """Create the capsule directory for *org_id* if it does not exist.

    Returns the capsule directory path.  Does nothing for org_id=None
    (legacy mode uses the existing economy/ directory).
    """
    if org_id is None:
        return ECONOMY_DIR
    target = os.path.join(CAPSULES_DIR, org_id)
    os.makedirs(target, exist_ok=True)
    return target
