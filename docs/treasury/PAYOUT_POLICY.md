# Payout Policy

Rules governing the payout proposal lifecycle, evidence requirements, and authority.

---

## 1. Payout Proposal Lifecycle

Every payout follows a six-state lifecycle:

```
draft -> submitted -> under_review -> approved -> dispute_window -> executed
                  \              \
                   -> cancelled    -> rejected
```

| State | Description | Who Acts |
|-------|-------------|----------|
| `draft` | Proposal created, not yet submitted | Proposer |
| `submitted` | Proposal submitted for review | System |
| `under_review` | Reviewer is evaluating evidence | Reviewer |
| `approved` | Reviewer and approver accept the proposal | Owner / delegated authority |
| `dispute_window` | 72-hour window for objections before execution | Anyone |
| `executed` | Payout sent to recipient wallet | System / owner |
| `rejected` | Proposal rejected at any review stage | Reviewer / owner |
| `cancelled` | Proposal withdrawn by proposer | Proposer |

---

## 2. Evidence Requirements

Every proposal must include evidence appropriate to its contribution type:

| Contribution Type | Required Evidence |
|-------------------|-------------------|
| `code` | PR URL(s), commit hash(es), merged status |
| `documentation` | PR URL(s), specific files changed |
| `security_report` | Issue reference, severity assessment, fix verification |
| `bug_report` | Issue reference, reproduction steps, fix PR (if applicable) |
| `design` | Design artifacts, implementation PR (if applicable) |
| `vertical_example` | PR URL, working example verification |
| `test_coverage` | PR URL, coverage diff |
| `review` | Review comments, PR references |
| `community` | Specific activities with links |

Proposals without sufficient evidence are rejected at `under_review`.

---

## 3. Authority Requirements

| Action | Required Authority |
|--------|-------------------|
| Create proposal | Any registered contributor or maintainer |
| Review proposal | Any maintainer who is NOT the contributor |
| Approve proposal | Owner, or agent with delegated `treasury:approve` scope |
| Execute payout | Owner only (no delegation for execution in v1) |
| Cancel proposal | Original proposer, or owner |
| Reject proposal | Reviewer or owner |

Self-review is not allowed. The reviewer must be a different person than the contributor.

---

## 4. Dispute Window

After approval, every proposal enters a 72-hour dispute window before execution.

During this window:
- Any maintainer or contributor may raise an objection
- Objections must include specific grounds (evidence insufficiency, duplicate claim, etc.)
- An objection pauses execution and returns the proposal to `under_review`
- Owner may override and execute during dispute window if the objection is frivolous

---

## 5. Wallet Requirements

The recipient wallet must:
- Be registered in `treasury/wallets.json`
- Have verification Level 3 (`self_custody_verified`) or Level 4 (`multisig_controlled`)
- Be in `active` status

Payouts to Level 0, 1, or 2 wallets are blocked. This protects against sending funds to exchange addresses or unverified wallets.

---

## 6. Current Status

- Treasury balance: $0.00
- Payouts executed: 0
- Proposals created: 0
- Payout-eligible wallets: 0

This policy is live infrastructure awaiting its first use. No payouts can occur until:
1. Treasury has funds above reserve floor
2. At least one Level 3+ wallet is registered
3. A valid contribution exists with evidence
