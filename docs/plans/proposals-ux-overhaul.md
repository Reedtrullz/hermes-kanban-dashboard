# Proposals UX Overhaul - Implemented State

This document records the implemented proposal-first redesign. Earlier draft directions that implied automatic processing or a live worker connection have been superseded.

## Implemented Product Model

- `/proposals` is a proposal inbox with a visible creation form, review filters, guided demo action, and honest worker setup guidance.
- `/proposals/{id}` exposes proposal context, acceptance criteria, review notes, decisions, activity, execution guidance, and quieter advanced metadata.
- `/proposals/projects` groups real work into initiatives and provides locally derived next-step recommendations.
- New real proposals begin at `waiting`, rendered as **Waiting for worker**.
- `processing` remains compatible for an external worker that explicitly reports active execution.
- Pending proposal approvals are presented as **Needs decision** without introducing a contradictory stored status.

## Execution Boundary

The dashboard records and reviews proposals locally in SQLite. It does not automatically invoke a model or claim a worker is connected.

- Creating a real proposal writes its id to `$HERMES_HOME/proposals_trigger`.
- Approving a real proposal writes `APPROVED:<id>`.
- Assigned non-Hermes executors may write `$HERMES_HOME/proposals_trigger_executor`.
- Demo records never write live execution triggers.

## First-Run Flow

1. Open the proposal inbox.
2. Use **Try demo** to practice notes and decisions with removable sample records.
3. Create a project for an active initiative.
4. Submit a real proposal attached to that project.
5. Configure an external Hermes or CLI worker before expecting execution.

## Browser And API Contract

- Visible proposal submission posts to `POST /proposals` and redirects to the new detail page.
- Notes post to `POST /proposals/{id}/notes` and redirect back to detail.
- The JSON-compatible `POST /api/proposals` route remains available for integrations.
- User-entered note markup is escaped before limited formatting is rendered.

## Visual Reference

The primary inbox and detail pages use the approved dark proposal-first visual system: structured navigation, high-contrast content panels, visible primary actions, status badges, review context, and responsive stacking for narrow screens.
