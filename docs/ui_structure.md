# UI Structure

Fortuna OS should be understandable without knowing the database.

## Simple Map

```text
Agency
  -> Models / Brands
      -> Accounts + Team
      -> Tasks + Incidents + Opportunities
      -> Reports + Intelligence + Automations
```

## Plain-English Meaning

- Agency: the whole company operating system.
- Models / Brands: the central business objects.
- Accounts: Instagram, X, OnlyFans, Email, or Other account records attached to a model.
- Team: managers, chatters, VAs, and viewers assigned to a model.
- Tasks: work that must be done.
- Incidents: problems that need attention.
- Opportunities: manual, human-approved chances to engage or follow up.
- Reports: daily briefings, accountability, production status, and operational summaries.
- Intelligence: things to watch, recurring problems, trends, and recommendations.
- Automations: internal operations rules that must simulate and pass approval gates before running.

## Clarity Rules

- Every screen needs a clear title.
- Empty states explain the next step.
- Back and Home/Main Menu should be available.
- Technical internals stay hidden from non-admin roles.
- Help Copilot should point users to exact paths, not vague concepts.
- No screen should imply that Fortuna OS posts, comments, scrapes, or bypasses platform security.
