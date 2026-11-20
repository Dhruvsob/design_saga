# GAMAA ERP: UI and UX review (release `504a2c3`, 2026-11-20)

Customer branding and the shared design tokens are unchanged (no colour
changes). Screenshots use synthetic data only. Earlier screen-by-screen work:
`docs/ux/FRONTEND_UX_STATUS.md`, `IMPROVEMENT_FINDINGS_2026-11-16.md`.

## 1. Screen decisions this cycle

| Screen | Difficulty a person had | Pattern adapted (reference) | Verified by |
|---|---|---|---|
| Calendar, Google connection | When Google stopped accepting the grant, the strip showed the same message twice (grey, then red), cut off with "..." on a phone, with no date, no reason and no way to disconnect | One status with a text label ("Paused", not colour alone: WCAG 2.2 1.4.1), the date it stopped, why (7-day Testing-mode limit when that pattern is detected), the consequence ("new and changed ERP items are not reaching your Google Calendar"), what reconnecting does, and both actions | Browser at 435 px and 1254 px; screenshot `screenshots/2026-11-20-calendar-paused-google.jpg` |
| Notification bell (all pages, phones) | The panel opened 22-45 px off the left edge at phone widths, cutting the title, the kind label and the first words of each notice | Panel spans the screen under the top bar on small screens; unchanged on desktop (WCAG 2.2 1.4.10 Reflow) | Measured bounds: before -22 px to 358 px (435 px viewport); after 12 px to 363 px (375 px); desktop 380 px right-anchored. `screenshots/2026-11-20-bell-panel-phone-before.jpg`, `...-after.jpg` |
| Projects list | "No projects yet" showed while loading and after any failure; a restricted Designer saw it permanently | Separate loading, empty and failed states, with Try again (IBM Carbon data table guidance: distinguish empty from error) | `ux.spec` restricted-role test; build |
| Quotations, Invoices, Accounting | A lookup the role may not read (clients, employees) emptied the whole page | Optional lookups: the list shows; only the picker is empty | `ux.spec` restricted-role test |
| Bell notice for a paused calendar | No signal outside the Calendar page | One high-priority notice linking straight to Calendar ("Reminder → notification → source record") | Local bell screenshot; production: 1 notice sent |

## 2. References

| Reference | Used this cycle? | Note |
|---|---|---|
| W3C WCAG 2.2 | Yes: 1.4.1 (status not by colour), 1.4.10 (reflow) | Pages above |
| IBM Carbon data tables | Yes: loading/empty/error states | Projects |
| GOV.UK error summary | Partly, earlier cycle: validation errors now name the field ("Client name: ...") instead of blanking the app; there is no form-level summary with field links yet | `lib/errors.js` (2026-11-20 round 2) |
| Monograph, Autodesk transmittals, Programa, Fieldwire, ERPNext | Not consulted this cycle (no screen in this release maps to them) | Earlier phases: transmittals (P2.7), approvals (P2.6), capacity (P2.5) |

## 3. Accessibility checks performed

| Check | Scope | Result |
|---|---|---|
| axe-core WCAG 2.0/2.1 A and AA | every primary page and create form (`a11y.spec`) | pass (this cycle, desktop) |
| Keyboard (partial) | Enter to submit, arrow keys in the searchable picker, Escape to close dialogs and menus (`forms.spec`, `ux.spec`) | pass; a full keyboard-only journey through a long form was not run |
| Phone width | `smoke`, `navigation`, `ux`, `forms` on the mobile project (Pixel-class emulation) | see `FINAL_TEST_RESULTS.md` |
| Manual at 375 px | bell panel, calendar strip | fixed and verified |

Not performed this cycle (requires a person or a device): screen-reader pass
(NVDA/VoiceOver), 200% browser zoom, 320 px reflow sweep, touch on a real
phone, rotation, iOS Safari. **Status: NOT YET VERIFIED.**

## 4. Unresolved usability issues

| Issue | Where | Suggested next step |
|---|---|---|
| Long forms have no error summary that links to each field | invoice, BOQ, employee forms | Add a GOV.UK-style summary above the form on submit |
| A paused calendar from before this release cannot show its pause date (unknown) | Calendar | Resolves itself after the next reconnect |
| Reminders reach only an open browser tab | all | See `FEATURE_RECOMMENDATIONS_FOR_APPROVAL.md` #2 |
| Owner Drawings shows as a negative number in its ledger | Accounting ledger | Correct (it reduces equity), but a "reduces equity" hint would help owners |
