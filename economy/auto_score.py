#!/usr/bin/env python3
"""
Auto-scorer for epoch results.
Reads actual cron outcomes and pipeline artifacts. Scores agents.
Advances epoch. Runs as system cron after delivery.

Usage:
  python3 auto_score.py           # run scoring
  python3 auto_score.py --dry-run # show what would be scored, no writes
"""
import json, sys, os, glob, random, datetime, argparse

ECONOMY_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE   = os.path.dirname(ECONOMY_DIR)

# Optional: import brief_quality from examples if available
_assess_brief_content = None
try:
    _examples_dir = os.path.join(WORKSPACE, 'examples', 'intelligence')
    sys.path.insert(0, _examples_dir)
    from brief_quality import assess_brief_content
    _assess_brief_content = assess_brief_content
except ImportError:
    pass

# Configurable paths -- override via environment variables
CRON_JOBS   = os.environ.get('MERIDIAN_CRON_JOBS', os.path.expanduser('~/.openclaw/cron/jobs.json'))
NS_DIR      = os.environ.get('MERIDIAN_NS_DIR', os.path.join(WORKSPACE, 'night-shift'))
LEDGER      = os.path.join(ECONOMY_DIR, 'ledger.json')
TRANSACTIONS = os.path.join(ECONOMY_DIR, 'transactions.jsonl')
LOG         = os.path.join(ECONOMY_DIR, 'auto_score.log')

# Per-outcome, per-role: (rep_base, auth_base)
OUTCOME_DELTAS = {
    'deliver_success': {
        'main': (15, 10), 'quill': (8, 6), 'aegis': (8, 6),
        'forge': (5, 4),  'atlas': (5, 4), 'sentinel': (5, 4), 'pulse': (3, 2),
    },
    'deliver_fail': {
        'main': (-10, -8),
    },
    'qa_sentinel_pass': {
        'sentinel': (8, 6),
    },
    'qa_sentinel_fail': {
        'sentinel': (0, -5),
    },
    'qa_aegis_accept': {
        'aegis': (10, 8),
    },
    'qa_aegis_reject': {
        'aegis': (-5, -4),
    },
    'write_accepted': {
        'quill': (10, 8),
    },
    'execute_completed': {
        'forge': (8, 6),
    },
    'research_delivered': {
        'atlas': (8, 6),
    },
    'remediation_completed': {
        'sentinel': (3, 3),
    },
}

# Outcomes that bypass the participation filter (allow blocked agents to earn recovery credit)
RECOVERY_OUTCOMES = {'remediation_completed'}

# Max AUTH gain per scoring event for zero_authority agents on recovery outcomes
RECOVERY_AUTH_CAP = 2

RAND_CAP = {'rep': 3, 'auth': 4}

# -- helpers ------------------------------------------------------------------

def now_ts():
    return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))

def load_ledger():
    with open(LEDGER) as f:
        return json.load(f)

def save_ledger(data):
    data['updatedAt'] = now_ts()
    with open(LEDGER, 'w') as f:
        json.dump(data, f, indent=2)

def append_tx(entry):
    entry['ts'] = now_ts()
    with open(TRANSACTIONS, 'a') as f:
        f.write(json.dumps(entry) + '\n')

def log(msg):
    line = f"[{now_ts()}] {msg}"
    print(line)
    with open(LOG, 'a') as f:
        f.write(line + '\n')

# -- outcome detection --------------------------------------------------------

def read_cron_jobs():
    try:
        with open(CRON_JOBS) as f:
            return json.load(f).get('jobs', [])
    except Exception as e:
        log(f"WARN: cannot read cron jobs: {e}")
        return []

def latest_report():
    """Return (path, text) for the most recently MODIFIED report file."""
    reports = glob.glob(os.path.join(NS_DIR, 'reports', '*.md'))
    if not reports:
        return '', ''
    reports.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    path = reports[0]
    with open(path) as f:
        return path, f.read()

def latest_brief():
    briefs = glob.glob(os.path.join(NS_DIR, 'brief-*.md'))
    if not briefs:
        return '', ''
    briefs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    with open(briefs[0]) as f:
        return briefs[0], f.read()

def detect_outcomes(jobs, report_text, brief_text):
    """Return list of (outcome_key, evidence) based on real artifacts."""
    outcomes = []
    lo_report = report_text.lower()
    lo_brief  = brief_text.lower()
    brief_audit = None

    if brief_text and _assess_brief_content:
        brief_audit = _assess_brief_content(brief_text, brief_date=_today())

    # 1. Deliver job
    deliver = next((j for j in jobs if j.get('name') == 'night-shift-deliver'), None)
    if deliver:
        status = deliver.get('state', {}).get('lastRunStatus', '')
        if status == 'ok' and deliver.get('state', {}).get('lastDelivered'):
            outcomes.append(('deliver_success',
                             f"night-shift-deliver ok+delivered at {deliver['state'].get('lastRunAtMs','')}"))
        elif status == 'error':
            err = deliver.get('state', {}).get('lastError', 'unknown error')
            outcomes.append(('deliver_fail', f"night-shift-deliver error: {err[:120]}"))

    # 2. QA outcomes from report
    if report_text:
        if 'sentinel' in lo_report:
            sentinel_blocked = any(kw in lo_report for kw in [
                'blocked-by-sanctions', 'blocked by sanctions',
                'sentinel: blocked', 'sentinel blocked',
            ])
            if sentinel_blocked:
                if any(kw in lo_report for kw in ['remediat', 'remediation']):
                    outcomes.append(('remediation_completed',
                                     'Sentinel blocked but remediation confirmed in report'))
            elif any(kw in lo_report for kw in ['sentinel: pass', 'sentinel pass', 'sentinel result: pass']):
                outcomes.append(('qa_sentinel_pass', 'Sentinel PASS in report'))
            elif any(kw in lo_report for kw in [
                'sentinel: fail', 'sentinel fail', 'sentinel result: fail',
                'no parseable', 'fail-to-parse', 'no auditable', 'weak',
                'cannot verify',
            ]):
                outcomes.append(('qa_sentinel_fail', 'Sentinel FAIL/weak in report'))

        if 'aegis' in lo_report:
            if any(kw in lo_report for kw in ['aegis: accept', 'aegis accept', 'accept\n', '\naccept']):
                if brief_audit and brief_audit['passed']:
                    outcomes.append(('qa_aegis_accept', 'Aegis ACCEPT in report and brief passed quality gate'))
                else:
                    log('WARN: Aegis ACCEPT present but brief failed quality gate')
            elif any(kw in lo_report for kw in ['aegis: reject', 'aegis reject', 'reject\n', '\nreject']):
                outcomes.append(('qa_aegis_reject', 'Aegis REJECT in report'))

        if brief_audit and brief_audit['passed']:
            outcomes.append(('write_accepted', 'brief passed local quality gate'))
        elif brief_text and len(brief_text) > 50:
            log('WARN: brief exists but did not earn write_accepted because quality gate failed')

        if 'forge' in lo_report and any(kw in lo_report for kw in ['execution:', 'exec:', 'completed', 'no-exec']):
            if 'no-exec' not in lo_report:
                outcomes.append(('execute_completed', 'Forge execution recorded in report'))

        if any(kw in lo_report for kw in ['finding', 'research', 'atlas']):
            if os.path.exists(os.path.join(NS_DIR, 'findings-' + _today() + '.md')):
                outcomes.append(('research_delivered', 'findings file present for today'))

    return outcomes

def _today():
    return datetime.datetime.utcnow().strftime('%Y-%m-%d')

# -- scoring ------------------------------------------------------------------

def apply_delta(agent, rep_delta, auth_delta, is_recovery=False):
    """Apply delta with bounded randomness."""
    old_rep  = agent['reputation_units']
    old_auth = agent['authority_units']

    rand_rep  = random.randint(0, RAND_CAP['rep'])  if rep_delta  > 0 else 0
    rand_auth = random.randint(0, RAND_CAP['auth']) if auth_delta > 0 else 0

    if agent.get('zero_authority') and auth_delta + rand_auth > 0:
        if is_recovery:
            auth_delta = min(auth_delta, RECOVERY_AUTH_CAP)
            rand_auth = 0
        else:
            auth_delta, rand_auth = 0, 0
    if agent.get('probation') and rep_delta + rand_rep > 0:
        rep_delta  = rep_delta // 2
        rand_rep   = 0

    actual_rep  = rep_delta  + rand_rep
    actual_auth = auth_delta + rand_auth

    return clamp(old_rep + actual_rep), clamp(old_auth + actual_auth), actual_rep, actual_auth

# -- epoch advance ------------------------------------------------------------

def advance_epoch(data, scored_agents, dry_run=False):
    epoch = data['epoch']
    decayed = []
    for aid, agent in data['agents'].items():
        if agent.get('zero_authority'):
            continue
        last = agent.get('last_scored_at', '')
        if last and last < epoch['started_at'] and aid not in scored_agents:
            old = agent['authority_units']
            if not dry_run:
                agent['authority_units'] = clamp(old - epoch['auth_decay_per_epoch'])
            decayed.append((aid, old, agent['authority_units']))
    for aid, old, new in decayed:
        log(f"  AUTH decay: {aid} {old} -> {new}")

    new_epoch = epoch['number'] + 1
    if not dry_run:
        epoch['number']     = new_epoch
        epoch['started_at'] = now_ts()
    log(f"Epoch {'would advance' if dry_run else 'advanced'} to {new_epoch}")
    return new_epoch

# -- main ---------------------------------------------------------------------

def already_scored(jobs):
    """Return True if the current deliver run was already scored."""
    deliver = next((j for j in jobs if j.get('name') == 'night-shift-deliver'), None)
    if not deliver:
        return False
    deliver_ms = deliver.get('state', {}).get('lastRunAtMs', 0)
    if not deliver_ms:
        return False
    try:
        with open(TRANSACTIONS) as f:
            for line in f:
                tx = json.loads(line.strip())
                if tx.get('type') == 'epoch_advance':
                    tx_ms = int(datetime.datetime.strptime(
                        tx['ts'], '%Y-%m-%dT%H:%M:%SZ').timestamp() * 1000)
                    if tx_ms > deliver_ms:
                        return True
    except Exception:
        pass
    return False

def run(dry_run=False):
    log(f"=== auto_score start (dry_run={dry_run}) ===")

    jobs         = read_cron_jobs()
    rpath, rtxt  = latest_report()
    bpath, btxt  = latest_brief()

    if not dry_run and already_scored(jobs):
        log("Already scored this deliver run -- skipping. (dedup guard)")
        return

    outcomes = detect_outcomes(jobs, rtxt, btxt)
    if not outcomes:
        log("No scoreable outcomes detected -- check report files and cron state.")
        return

    log(f"Detected {len(outcomes)} outcome(s):")
    for key, evidence in outcomes:
        log(f"  [{key}] {evidence}")

    if dry_run:
        log("DRY RUN -- no writes")
        return

    data = load_ledger()
    scored = set()

    participating = set()
    for aid, agent in data['agents'].items():
        if not agent.get('zero_authority') and not agent.get('remediation_only'):
            participating.add(aid)
        elif aid == 'main':
            participating.add(aid)

    for outcome_key, evidence in outcomes:
        deltas = OUTCOME_DELTAS.get(outcome_key, {})
        is_recovery = outcome_key in RECOVERY_OUTCOMES
        for agent_id, (rd, ad) in deltas.items():
            if agent_id not in data['agents']:
                continue
            if agent_id not in participating and rd > 0 and not is_recovery:
                log(f"  {agent_id}: SKIPPED (blocked/non-participating) -- no positive score from {outcome_key}")
                continue
            agent    = data['agents'][agent_id]
            old_rep  = agent['reputation_units']
            old_auth = agent['authority_units']

            new_rep, new_auth, actual_rep, actual_auth = apply_delta(agent, rd, ad, is_recovery=is_recovery)
            agent['reputation_units'] = new_rep
            agent['authority_units']  = new_auth
            agent['last_scored_at']   = now_ts()
            agent['last_score_reason'] = f"auto:{outcome_key} | {evidence[:80]}"

            append_tx({
                'type':       'agent_score',
                'agent':      agent_id,
                'event':      f'auto_{outcome_key}',
                'rep_before': old_rep,  'rep_after':  new_rep,  'rep_delta':  actual_rep,
                'auth_before': old_auth, 'auth_after': new_auth, 'auth_delta': actual_auth,
                'note':       f"auto: {evidence[:100]}",
                'randomized': (actual_rep != rd or actual_auth != ad),
            })
            scored.add(agent_id)
            log(f"  {agent_id}: REP {old_rep}->{new_rep} ({actual_rep:+}) | AUTH {old_auth}->{new_auth} ({actual_auth:+})")

    new_epoch = advance_epoch(data, scored, dry_run=False)
    append_tx({'type': 'epoch_advance', 'new_epoch': new_epoch,
               'note': f'auto-advance. scored: {sorted(scored)}'})

    save_ledger(data)
    log(f"Done. Scored {len(scored)} agent(s). Epoch={new_epoch}.")

    # Auto-apply/lift sanctions based on new scores
    try:
        import sanctions as sanctions_mod
        data2 = load_ledger()
        sanctions_mod.check_auto_sanctions(data2, dry_run=False)
        save_ledger(data2)
        log("Auto-sanction check complete.")
    except Exception as e:
        log(f"WARN: auto-sanction check failed: {e}")

    # Sync scores to agent registry (kernel integration)
    try:
        kernel_dir = os.path.join(WORKSPACE, 'kernel')
        sys.path.insert(0, kernel_dir)
        from agent_registry import sync_from_economy
        sync_from_economy()
        log("Agent registry synced from economy ledger.")
    except Exception as e:
        log(f"WARN: agent registry sync failed: {e}")

    # Court auto-review
    try:
        kernel_dir = os.path.join(WORKSPACE, 'kernel')
        sys.path.insert(0, kernel_dir)
        from court import auto_review as court_auto_review
        violations = court_auto_review()
        if violations:
            log(f"Court auto-review created {len(violations)} violation(s).")
        else:
            log("Court auto-review: no new violations.")
    except Exception as e:
        log(f"WARN: court auto-review failed: {e}")

def main():
    p = argparse.ArgumentParser(description='Auto-scorer for epoch results')
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    run(dry_run=args.dry_run)

if __name__ == '__main__':
    main()
