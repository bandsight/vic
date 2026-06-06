# Feature Answer Builder Doctrine

Feature Cards are evidence candidates, not final governed facts.

Every Feature Card must immediately carry an answer-building contract. The contract exists because semantic reasoning belongs before deterministic governance. The machine should first decide what the extracted span actually means, then deterministic gates should decide whether the structured answer is safe enough to promote.

The standard flow is:

1. Create Feature Card from source evidence.
2. Attach `answer_builder` contract at creation time.
3. Build a structured answer candidate by resolving entitlement meaning, value type, cohort, timeframe, condition, paid status, and normal-value alignment.
4. Repair blockers from source context where possible.
5. Promote only resolved answers through the deterministic Entitlement Card gate.

Blocked is not an end state. It is a work queue for answer-building, repair, or source research.

Deterministic code should validate schema, provenance, required fields, unresolved blockers, review status, and source support. It should not be the primary layer that decides what a clause means.
