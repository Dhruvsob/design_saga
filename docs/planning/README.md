# Design Saga ERP Product Transformation Audit

Audit date: 2026-10-17 (Asia/Kolkata)

This directory is the planning output requested in the Design Saga master brief. It is an audit and decision pack, not an implementation claim. No production code, data, services, or paid subscriptions were changed while producing it.

## Reading the evidence

| Label | Meaning |
|---|---|
| Verified production | The existing repair records include a live production check and deployment commit. |
| Code present | The repository contains UI/API/model logic, but this audit did not prove the complete live workflow. |
| Historical claim | An older PRD or test report says it worked; that claim was not independently re-run in this planning phase. |
| Proposed | A researched recommendation, not implemented. |
| Pending local fix | An uncommitted change existed before this planning brief; it is neither approved nor deployed. |

`Fully implemented` is used only when both implementation and end-to-end evidence are available. A page or endpoint alone is not proof.

## Reports

1. [Existing ERP Audit](01-existing-erp-audit.md)
2. [Architecture Industry Problem Library](02-industry-problem-library.md)
3. [Integration Opportunity Matrix](03-integration-opportunity-matrix.md)
4. [Existing Module Enhancement Plan](04-existing-module-enhancement-plan.md)
5. [New Module Proposal](05-new-module-proposal.md)
6. [Multi-Tenant SaaS Architecture](06-multi-tenant-saas-architecture.md)
7. [Cost and Infrastructure Plan](07-cost-and-infrastructure-plan.md)
8. [Prioritized Implementation Roadmap](08-prioritized-implementation-roadmap.md)
9. [User Journey and Workflow Matrix](09-user-journey-workflow-matrix.md)
10. [Executive Decision Summary](10-executive-decision-summary.md)
11. [Persistent Progress Record](PROGRESS.md)

## Scope and method

- Inspected repository structure, 322 API route declarations, 29 frontend page files, 28 backend test files, models, shared security controls, deployment composition, current Git state, historical PRD/test records, repair tracker, and production risk register.
- Compared the product with official workflow documentation from Autodesk Forma/Build, Newforma Project Center, and BQE CORE.
- Checked current official integration documentation and pricing pages where available. Prices are dated snapshots, exclude GST unless stated, and must be rechecked before procurement.
- Did not run destructive tests, touch production data, deploy, restart services, or purchase/enable a paid service.
- Did not assert the aspirational 95-98% coverage target. Report 9 defines measurable workflow acceptance instead.

## Current source register

Research checked on 2026-10-17. Official sources are preferred; a vendor's own pricing is evidence of its terms, not an endorsement.

- AECO workflows: [Newforma Project Center](https://www.newforma.com/newforma-project-center/), [Autodesk RFIs](https://help.autodesk.com/cloudhelp/ENU/Build-Rfis/files/Work_RFIs.html), [Autodesk Submittals](https://help.autodesk.com/cloudhelp/ENU/Build-Submittals/files/Work_Submittals.html), [BQE project accounting](https://www.bqe.com/features/project-accounting).
- Google: [OAuth sensitive-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification), [Calendar errors and quotas](https://developers.google.com/workspace/calendar/api/guides/errors), [Drive limits](https://developers.google.com/workspace/drive/api/guides/limits), [Maps India pricing](https://developers.google.com/maps/billing-and-pricing/india), [Firebase pricing](https://firebase.google.com/pricing).
- Microsoft/Slack: [Microsoft Graph throttling](https://learn.microsoft.com/en-us/graph/throttling), [Graph service limits](https://learn.microsoft.com/en-us/graph/throttling-limits), [Slack API limits](https://api.slack.com/apis/rate-limits).
- Infrastructure and delivery: [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/), [Amazon SES pricing](https://aws.amazon.com/ses/pricing/), [GitHub pricing](https://github.com/pricing), [n8n pricing](https://n8n.io/pricing/).
- Payments/signature: [Razorpay pricing](https://razorpay.com/pricing/), [Stripe India pricing](https://stripe.com/in/pricing), [DocuSign pricing](https://ecom.docusign.com/plans-and-pricing/esignature).

## Planning assumptions

- Currency conversion for non-INR list prices: planning-only assumption of `USD 1 = INR 90` and `EUR 1 = INR 100`; use the invoice exchange rate at purchase.
- Target customer sizes: 10, 150, 1,000, and 3,000 active users across 1, 10, 50, and 100 tenants.
- Uploaded files and drawings must move to object storage before serious multi-tenant scale.
- Google Calendar remains opt-in and per user. Calendar scopes are sensitive, so public rollout depends on Google verification.
- The current database is PostgreSQL via FerretDB's Mongo-compatible interface. It is not MongoDB Atlas.
