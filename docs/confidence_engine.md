# Confidence Engine

The confidence engine tracks why Fortuna OS trusts or distrusts an operational suggestion.

Confidence is not magic and is not LLM-generated. Sprint 15 uses small deterministic adjustments based on outcomes and feedback.

## Subjects

Confidence records may reference:

- recommendation.
- playbook.
- automation.
- proxy.
- opportunity.
- intelligence_signal.
- issue_pattern.

## Confidence Increases

Confidence can rise when:

- a playbook succeeds.
- a recommendation is resolved or marked useful.
- an automation succeeds.
- a proxy repair succeeds.
- an opportunity records positive manual results.

## Confidence Decreases

Confidence can fall when:

- a playbook fails.
- an automation fails.
- a recommendation is dismissed, marked not useful, or marked wrong.
- an opportunity fails or has weak results.
- proxy repairs repeatedly fail.

## Records

Every confidence change creates a `confidence_records` row with:

- subject type and ID.
- previous score.
- new score.
- safe reason.
- safe evidence.

## Operator Feedback

Recommendation and playbook screens support:

- Useful.
- Not Useful.
- Wrong.
- Needs Review.

Feedback creates a learning event, updates outcome memory, adjusts confidence lightly, and audits a safe summary.
