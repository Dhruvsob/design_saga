# GAMAA ERP: UI and UX review (releases `504a2c3`, `74aff6e`, `1cdac8c`, 2026-11-20)

Customer branding and the shared design tokens are unchanged (no colour
changes). Screenshots and documents use synthetic data only. Earlier
screen-by-screen work: `docs/ux/FRONTEND_UX_STATUS.md`,
`IMPROVEMENT_FINDINGS_2026-11-16.md`.

## 1. Screen decisions

| Screen | Difficulty a person had | Pattern adapted (reference) | Verified by |
|---|---|---|---|
| Drawing register (site) | A newer revision issued "for review" superseded the GFC sheet, so a supervisor on site saw an unapproved draft as the drawing | The construction set stays the site copy; the row says "On site: rev B (For construction)" in text, with a link, and the ⋮ menu has "Open site copy"; the issue form says what will happen before issuing (Autodesk transmittals: an issue records the specific version) | `drawings.spec` site-copy test; `test_drawings.py` |
| Project → Design → Selections (new) | Which finish did the client approve for the kitchen, and what is still open before buying? | Room-grouped list; status in words ("To send", "Waiting for client", "Approved", "Client asked for changes"); who approved and when; library picker; one-step send to the portal (Programa: specification and client decisions by room) | `selections.spec` (desktop and phone) |
| Purchase order form | No project field at all, no specification per line; buyers could order unapproved finishes | Project picker; "N selections are not approved by the client yet" warning; "Add the approved selections as lines" | `selections.spec` |
| Quotation builder | "Mark approved" was the only record of client acceptance | "Send to client for acceptance" and a status line ("Accepted by Anita Mehta on 20/11/2026: version 1, ₹…") | `selections.spec` |
| Client portal | — | New request kinds read "Material or finish" and "Quotation"; the quotation opens as its PDF | `selections.spec` |
| Client approvals tab | An approved variation stayed a total on the tab; billing it meant retyping it as a milestone | "Add to fee milestones" on the approved variation (amount and approver carried over, optional due date), then "In fee milestones" in its place | `selections.spec` |
| New employee / new project forms | Placeholders only (gone once you type), an unlabelled joining date; server errors as a passing toast | Visible labels; an error summary at the top that takes focus, lists each problem and jumps to the field; typed input kept (GOV.UK error summary; WCAG 2.2 3.3.1, 3.3.2) | `errorItems` unit test; lint; build |
| Top bar at tablet width | At 768 px the bell and lock were pushed 8-91 px off the screen on 20 pages | Breadcrumb truncates; section name only on wide screens (WCAG 1.4.10 Reflow) | sweep at 768/1024 px: 0 findings |
| Calendar, Google connection | Message shown twice, cut off on phones, no date, no reason, no way to disconnect | One status with a text label, date, reason, consequence and both actions (WCAG 1.4.1) | browser screenshots |
| Notification bell (phones) | Panel started 22-45 px off the left edge | Full width under the top bar on small screens | measured bounds |
| Projects list | "No projects yet" while loading, after a failure, and for restricted roles | Separate loading / empty / failed states with Try again (IBM Carbon data-table states) | `ux.spec` restricted-role test |

## 2. References

| Reference | Used? | Where |
|---|---|---|
| W3C WCAG 2.2 | Yes: 1.4.1, 1.4.10, 3.3.1, 3.3.2 | status labels, reflow, error summary, labels |
| GOV.UK error summary | Yes | new project and new employee forms |
| IBM Carbon data tables | Yes: loading/empty/error states | Projects |
| Programa specification tools | Yes: room-wise specification and client decision | Selections |
| Autodesk transmittals | Yes: a specific issued version stays identifiable | Drawing site copy |
| Monograph, Fieldwire, ERPNext | Not applied in these releases (their workflows already exist: project financials, snags, payment entry) | — |

The reference pages themselves were not re-opened in this session; the
patterns above are the ones named in the release brief.

## 3. Generated documents (PDF)

`backend/scripts/pdf_inspection.py` builds a 45-line quotation BOQ, a 40-line
invoice, a 30-line purchase order and a payslip in a fresh workspace and checks
them with pypdf: A4 portrait on every page, the column header repeated on every
table page, every long description printed in full, no "undefined/NaN/None",
totals equal to the screen with Indian grouping. **37/37 checks pass.**

The same synthetic quotation and purchase order rendered by the previous
release and by `74aff6e`:

| Check | Before (`504a2c3`) | After (`74aff6e`) |
|---|---|---|
| Margin column ("Mgn%") shown to the client | **yes** | no |
| Base cost rate (1,850) shown as the rate | **yes** | no |
| Selling rate (2,127.50 = 1,850 + 15%) shown | no | yes |
| Long description printed to the end (quotation) | **no** (cut at 55 characters) | yes |
| Supplier specification printed to the end (PO) | **no** (cut at 58 characters) | yes |

Amounts use "Rs." because the built-in PDF font has no ₹ glyph; switching to ₹
needs a bundled Unicode font (not done).

## 4. Accessibility checks performed

| Check | Scope | Result |
|---|---|---|
| axe-core WCAG 2.0/2.1 A and AA | every primary page and create form (`a11y.spec`) | pass |
| Widths 320, 360, 390, 683 (200% zoom of 1366), 768, 1366, 1920 px | every page, Admin and Employee | 0 findings after the 768 px fix |
| Keyboard (partial) | Enter to submit, arrows in pickers, Escape to close (`forms.spec`, `ux.spec`) | pass |
| Error summary focus | summary takes focus on a failed save; each entry moves focus to its field | implemented; the error list is unit-tested, the focus behaviour was not exercised in a browser |
| Phone layouts | `smoke`, `navigation`, `ux`, `forms`, `selections`, `phases` on the mobile project | 27 passed |

Not performed (needs a person or device): screen reader (NVDA/VoiceOver),
touch on a real phone, rotation, iOS Safari. **Status: NOT YET VERIFIED.**

## 5. Unresolved usability issues

| Issue | Where | Suggested next step |
|---|---|---|
| Error summary only on the new-project and new-employee forms | invoice, BOQ, other long forms | Apply `ErrorSummary` as those forms are touched |
| Owner Drawings shows as a negative number in its ledger | Accounting ledger | Correct (it reduces equity); a "reduces equity" hint would help owners |
| A calendar paused before 20 Nov cannot show its pause date | Calendar | Resolves after the next reconnect |
| Reminders reach only an open browser tab | all | `FEATURE_RECOMMENDATIONS_FOR_APPROVAL.md` #1 |
