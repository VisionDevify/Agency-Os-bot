# Approval Workflows

Automation approval protects live operations from accidental or risky execution.

## Rules

- A valid simulation must exist before approval.
- Expired simulations cannot be approved.
- Low and medium risk automations can be approved by Owner/Admin with automation permission.
- High and critical risk automations require Owner approval.
- Proxy Repair Assistant requires Owner approval.
- Automations with mutation actions require approval before activation.

## Records

Approvals are stored in `automation_approvals` with:

- automation rule.
- requesting user.
- deciding user.
- status.
- approval or rejection note.
- created, decided, and expiry timestamps.

## Telegram Flow

Automations -> Rule Detail:

- Run Simulation.
- Review Impact Preview.
- Request Approval.
- Pending Approvals.
- Approve or Reject.
- Activate only after approval.

Denied approvals and blocked activations are audited with safe reason metadata.
