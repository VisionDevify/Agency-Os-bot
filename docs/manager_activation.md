# Manager Activation

Sprint 18 makes Team Activation operational for managers and admins.

## Team Activation QA

Managers can review:

- users pending approval;
- users without roles;
- users without timezone setup;
- users without availability configured;
- users with no assigned work;
- chatters with no assigned models;
- chatters with no assigned opportunities.

The score is a readiness signal, not a punishment score.

## Manager Opportunity View

Managers can see:

- unassigned opportunities;
- assigned opportunities;
- overdue opportunities;
- completed today;
- high-priority opportunities;
- results by chatter;
- distribution by model;
- distribution by niche;
- top performing angles.

## Activation Actions

Managers should use existing admin flows to:

- approve users;
- assign roles;
- assign models;
- assign opportunities;
- send users to Help Copilot;
- mark onboarding checklist items complete.

## Manager Setup / QA

Sprint 19 adds `Manager QA` so setup gaps are visible in one place:

- models without managers;
- models without chatters;
- accounts without a model;
- opportunities without an assignee;
- tasks without an owner;
- pending users;
- users without timezone;
- users without roles;
- users not onboarded.

The intent is practical cleanup, not performance judgment.

## Notification Discipline

Opportunity events are digestable. Low-priority updates should route through digest behavior where configured, while high-priority opportunities and critical issues may route directly to owner/operations targets.
