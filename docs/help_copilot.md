# Help Copilot

Help Copilot is a simple role-aware explainer inside Telegram.

It helps team members answer:

- What does this mean?
- How do I do this?
- Where do I go?

## Sprint 18 Behavior

The first version is deterministic and safe:

- reads the user's role context.
- answers common workflow questions, including creator intake, opportunity assignment, result recording, and access confusion.
- points to the next useful Agency OS screen.
- can explain key opportunity screens through "Explain This Screen" shortcuts.
- audits a safe `help_copilot.answered` event.

It does not call an external AI provider yet and does not expose secrets or raw internal diagnostics.

## Example Answers

For a Chatter asking how to complete an opportunity:

1. Open My Opportunities.
2. Pick the assigned item.
3. Review suggested strategies.
4. Take the human-approved action outside Agency OS.
5. Record the result manually.

For availability:

1. Open Availability.
2. Set on shift, away, vacation, or unavailable.
3. Agency OS uses that state for routing and digest behavior.

For opportunity result recording:

1. Open the opportunity.
2. Tap Record Result.
3. Choose Posted, Skipped, Rejected, or Failed.
4. Add safe notes and optional clicks/conversions.
5. Agency OS updates learning memory.

## Future

Future versions can search docs, screen context, and permissions more deeply. Any AI-powered version must avoid secrets and must keep action execution human-approved.
