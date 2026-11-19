Closes #

## Brief
<!-- Read docs/BRIEF_CAPSTONE.md first (and docs/BRIEF_SPRINT3.md or docs/BRIEF.md when the PR changes something they cover). Name each item by its number there, or write "none". -->
- Capstone (`docs/BRIEF_CAPSTONE.md`): <Case 2 step n | Case 4 step n | E n (letter) | R | presentation point n> | none
- Sprint 3 (`docs/BRIEF_SPRINT3.md`): <core n | Easy, Medium or Hard n | evaluation item | Sprint 2 review point n | Sprint 3 review point n> | none
- Sprint 2 (`docs/BRIEF.md`): <core n | Easy, Medium or Hard n | evaluation item> | none
- Or, when no brief covers it: beyond the brief (owner's request)
- [ ] Checked against the Capstone brief (and an earlier brief it touches), `docs/PRD.md` and the copyright policy: no contradiction, and no change to what the product does that the owner has not approved

## Changes
-

## Acceptance criteria
- [ ] <criterion> - verified by <test name or manual check>

## Testing
- `ruff check .` / `ruff format --check .` / `python -m pytest -q`:
- Manual checks:
- `compliance-reviewer` (`.claude/rules/workflow.md`): <run on SHA: verdict, what each finding led to> | not needed: <reason>

## Sources and copyright
- [ ] No new content, or every new source is an Approved row in `docs/SOURCES.md` and `ATTRIBUTION.md` is updated
- [ ] No secrets, personal data or raw source documents committed

## Records
- [ ] Entry added: a file in `docs/progress/` and its line at the top of `docs/PROGRESS.md`
- [ ] Ticket status updated in its file in `docs/tickets/` and in the order table of `docs/IMPLEMENTATION_PLAN.md`; ticket ID in the PR title and commits
