use meridian_kernel_rs_explore::{
    commit_spend, evaluate_action, ActionRequest, DecisionStatus, TreasuryState,
};

fn base_request() -> ActionRequest {
    ActionRequest {
        org_id: "org_demo".to_string(),
        agent_id: "agent_atlas".to_string(),
        capability: "loom.terminal.exec.v1".to_string(),
        estimated_cost_cents: 75,
        warrant_bound: true,
        authority_ok: true,
        court_ok: true,
    }
}

#[test]
fn allows_action_when_governance_and_treasury_checks_pass() {
    let request = base_request();
    let treasury = TreasuryState {
        balance_cents: 400,
        reserve_floor_cents: 250,
    };
    let decision = evaluate_action(&request, &treasury);
    assert_eq!(decision.status, DecisionStatus::Allow);
    assert_eq!(decision.reason, "governance_checks_passed");
    assert_eq!(decision.proof.schema_version, "meridian.kernel.rs.explore.proof.v1");
}

#[test]
fn denies_action_when_reserve_floor_would_be_breached() {
    let request = base_request();
    let treasury = TreasuryState {
        balance_cents: 300,
        reserve_floor_cents: 260,
    };
    let decision = evaluate_action(&request, &treasury);
    assert_eq!(decision.status, DecisionStatus::Deny);
    assert_eq!(decision.reason, "treasury_reserve_floor_breach");
}

#[test]
fn denies_action_when_warrant_is_missing() {
    let mut request = base_request();
    request.warrant_bound = false;
    let treasury = TreasuryState {
        balance_cents: 500,
        reserve_floor_cents: 100,
    };
    let decision = evaluate_action(&request, &treasury);
    assert_eq!(decision.status, DecisionStatus::Deny);
    assert_eq!(decision.reason, "warrant_missing");
}

#[test]
fn commit_spend_reduces_balance_without_underflow() {
    let treasury = TreasuryState {
        balance_cents: 80,
        reserve_floor_cents: 40,
    };
    let updated = commit_spend(&treasury, 75);
    assert_eq!(updated.balance_cents, 5);
    let clamped = commit_spend(&updated, 200);
    assert_eq!(clamped.balance_cents, 0);
}

