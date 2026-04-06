use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ActionRequest {
    pub org_id: String,
    pub agent_id: String,
    pub capability: String,
    pub estimated_cost_cents: u64,
    pub warrant_bound: bool,
    pub authority_ok: bool,
    pub court_ok: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TreasuryState {
    pub balance_cents: u64,
    pub reserve_floor_cents: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RuntimeProofEnvelope {
    pub schema_version: String,
    pub org_id: String,
    pub agent_id: String,
    pub capability: String,
    pub decision: DecisionStatus,
    pub reason: String,
    pub treasury_balance_cents: u64,
    pub treasury_reserve_floor_cents: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum DecisionStatus {
    Allow,
    Deny,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Decision {
    pub status: DecisionStatus,
    pub reason: String,
    pub proof: RuntimeProofEnvelope,
}

pub fn evaluate_action(request: &ActionRequest, treasury: &TreasuryState) -> Decision {
    let (status, reason) = if !request.warrant_bound {
        (DecisionStatus::Deny, "warrant_missing".to_string())
    } else if !request.authority_ok {
        (DecisionStatus::Deny, "authority_rejected".to_string())
    } else if !request.court_ok {
        (DecisionStatus::Deny, "court_restriction".to_string())
    } else if treasury.balance_cents < request.estimated_cost_cents {
        (DecisionStatus::Deny, "treasury_insufficient_balance".to_string())
    } else if treasury.balance_cents.saturating_sub(request.estimated_cost_cents)
        < treasury.reserve_floor_cents
    {
        (DecisionStatus::Deny, "treasury_reserve_floor_breach".to_string())
    } else {
        (DecisionStatus::Allow, "governance_checks_passed".to_string())
    };

    let proof = RuntimeProofEnvelope {
        schema_version: "meridian.kernel.rs.explore.proof.v1".to_string(),
        org_id: request.org_id.clone(),
        agent_id: request.agent_id.clone(),
        capability: request.capability.clone(),
        decision: status.clone(),
        reason: reason.clone(),
        treasury_balance_cents: treasury.balance_cents,
        treasury_reserve_floor_cents: treasury.reserve_floor_cents,
    };

    Decision {
        status,
        reason,
        proof,
    }
}

pub fn commit_spend(treasury: &TreasuryState, amount_cents: u64) -> TreasuryState {
    TreasuryState {
        balance_cents: treasury.balance_cents.saturating_sub(amount_cents),
        reserve_floor_cents: treasury.reserve_floor_cents,
    }
}
