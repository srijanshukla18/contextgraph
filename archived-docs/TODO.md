  ---
  The Core Problem with "A Dashboard"

  A traditional UI for DecisionRecords is fundamentally wrong because:

  1. It's another destination — Users don't want to visit contextgraph.company.com to understand why something happened. They want the answer where they already are.
  2. Decision context is consumed reactively — Nobody browses decisions. They investigate when something goes wrong, when a customer complains, when audit asks, or when approving an action.
  3. One-size-fits-none — Compliance needs different views than Ops, who needs different views than Finance, who needs different views than the engineer debugging an agent.
  4. Dashboards are pull, but decisions are push — The value is in surfacing the right context at the right moment, not in building a searchable archive.

  ---
  Who Actually Consumes This Data?

  | Persona      | Trigger            | Question                              | Context          |
  |--------------|--------------------|---------------------------------------|------------------|
  | Support lead | Customer complaint | "Why did we only give 10%?"           | The ticket       |
  | Finance      | Monthly close      | "All credits > $10k needing sign-off" | Time period      |
  | Compliance   | Audit request      | "Trace the approval chain"            | Policy + entity  |
  | Ops/SRE      | Incident           | "What did the agent do at 3:42am?"    | Agent run        |
  | Manager      | Approval request   | "Should I approve this exception?"    | Pending decision |
  | Executive    | Board prep         | "Exception rate trending up?"         | Aggregates       |
  | Engineer     | Debugging          | "Why did my agent take this path?"    | Code + run       |

  None of these personas want a dashboard. They want answers in their workflow.

  ---
  The North Star: The Decision Fabric

  Instead of a UI, build a decision fabric — invisible infrastructure that surfaces decision context exactly when and where it's needed.

  ┌─────────────────────────────────────────────────────────────────────┐
  │                        DECISION FABRIC                               │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐        │
  │   │  Slack   │   │  CRM     │   │  CLI     │   │ Mobile   │        │
  │   │   Bot    │   │ Sidebar  │   │  Tool    │   │  App     │        │
  │   └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘        │
  │        │              │              │              │               │
  │        └──────────────┴──────────────┴──────────────┘               │
  │                              │                                       │
  │                    ┌─────────▼─────────┐                            │
  │                    │   AI Query Layer   │                            │
  │                    │  (Natural Language)│                            │
  │                    └─────────┬─────────┘                            │
  │                              │                                       │
  │                    ┌─────────▼─────────┐                            │
  │                    │    GraphQL API    │                            │
  │                    │   + Subscriptions │                            │
  │                    └─────────┬─────────┘                            │
  │                              │                                       │
  │                    ┌─────────▼─────────┐                            │
  │                    │  DecisionRecords  │                            │
  │                    └───────────────────┘                            │
  │                                                                      │
  └─────────────────────────────────────────────────────────────────────┘

  ---
  The 7 Surfaces (Not 1 Dashboard)

  1. The Conversational Interface (Primary)

  Most interactions should be conversational. The data is structured — perfect for LLM-powered querying.

  ┌─────────────────────────────────────────────────────────────┐
  │  #support-exceptions                                         │
  ├─────────────────────────────────────────────────────────────┤
  │                                                              │
  │  Sarah Chen                                         10:42 AM │
  │  /why SUP-4312                                               │
  │                                                              │
  │  ContextGraph                                       10:42 AM │
  │  ┌─────────────────────────────────────────────────────────┐│
  │  │ 📋 Decision: Service Credit for Acme Corp               ││
  │  │                                                         ││
  │  │ What happened:                                          ││
  │  │ Agent approved a 20% credit ($8,333) after 3 SEV-1      ││
  │  │ incidents caused 14.5 hours of downtime.                ││
  │  │                                                         ││
  │  │ Why exception was needed:                               ││
  │  │ Requested 20% exceeded 10% standard cap.                ││
  │  │ Qualified via service_impact_exception route            ││
  │  │ (≥3 SEV-1s in 30 days).                                 ││
  │  │                                                         ││
  │  │ Approved by: finance-lead@ourcompany.com                ││
  │  │ Reason: "Service impact justified per policy"           ││
  │  │                                                         ││
  │  │ [View Full Audit Trail]  [Similar Precedents]           ││
  │  └─────────────────────────────────────────────────────────┘│
  │                                                              │
  │  Sarah Chen                                         10:43 AM │
  │  Show me all credits over 15% this month                     │
  │                                                              │
  │  ContextGraph                                       10:43 AM │
  │  Found 3 credits above 15% in December:                      │
  │                                                              │
  │  1. Acme Corp - 20% ($8,333) - SEV-1 impact                 │
  │  2. Globex - 18% ($2,160) - Churn risk                      │
  │  3. Initech - 15% ($750) - At cap, no exception             │
  │                                                              │
  │  Total: $11,243 across 3 accounts                           │
  │  [Export to CSV]  [Generate Report]                         │
  │                                                              │
  └─────────────────────────────────────────────────────────────┘

  Key interactions:
  - /why <ticket-id> — Instant explanation
  - /approve — Pending approvals queue
  - /watch service_credit — Subscribe to real-time stream
  - Free-form questions answered by LLM over structured data

  ---
  2. The Contextual Sidebar (Zero-Click Context)

  When viewing any entity in Salesforce/Zendesk/JIRA, a sidebar surfaces related decisions without asking.

  ┌────────────────────────────────────────┬──────────────────────────┐
  │                                        │                          │
  │  ZENDESK - Ticket SUP-4312             │  ContextGraph            │
  │                                        │                          │
  │  ┌──────────────────────────────────┐  │  Decision History        │
  │  │ Subject: Service credit request  │  │  ─────────────────────   │
  │  │                                  │  │                          │
  │  │ Customer: Acme Corporation       │  │  ✓ Credit Issued         │
  │  │ Priority: High                   │  │    20% • $8,333          │
  │  │ Status: Solved                   │  │    Today 10:30 AM        │
  │  │                                  │  │    [Explain]             │
  │  │ ───────────────────────────────  │  │                          │
  │  │                                  │  │  ✓ Finance Approved      │
  │  │ Description:                     │  │    Exception route       │
  │  │ We've experienced significant    │  │    Today 10:28 AM        │
  │  │ downtime over the past month...  │  │                          │
  │  │                                  │  │  ⚠ Policy Check          │
  │  │                                  │  │    Exceeded 10% cap      │
  │  │                                  │  │    Today 10:25 AM        │
  │  │                                  │  │                          │
  │  │                                  │  │  ─────────────────────   │
  │  │                                  │  │                          │
  │  │                                  │  │  Similar Precedents (3)  │
  │  │                                  │  │  ─────────────────────   │
  │  │                                  │  │  • Globex - 18% ✓        │
  │  │                                  │  │  • Wayne Ent - 22% ✓     │
  │  │                                  │  │  • Stark Ind - 25% ✗     │
  │  │                                  │  │    (denied, no SEV-1s)   │
  │  │                                  │  │                          │
  │  │                                  │  │  [Full Timeline]         │
  │  └──────────────────────────────────┘  │                          │
  │                                        │                          │
  └────────────────────────────────────────┴──────────────────────────┘

  Key features:
  - Auto-loads when viewing related entities
  - Progressive disclosure: summary → timeline → full record
  - Precedent comparison inline
  - No navigation required

  ---
  3. The CLI Tool (For Engineers)

  Engineers live in the terminal. Give them first-class access.

  $ cg explain dec_3f35d5ee

  ┌─ Decision: dec_3f35d5ee ─────────────────────────────────────┐
  │                                                               │
  │  Outcome: COMMITTED                                           │
  │  Run: exception_desk_agent • SUP-4312                        │
  │  Time: 2025-01-15 10:30:00 UTC                               │
  │                                                               │
  │  EVIDENCE ─────────────────────────────────────────────────  │
  │  • ticket: SUP-4312 (20% credit request)                     │
  │  • account: Acme Corp (enterprise, ARR $500k, churn: high)   │
  │  • incidents: 3 SEV-1, 2 SEV-2 (14.5h downtime)             │
  │                                                               │
  │  POLICY ───────────────────────────────────────────────────  │
  │  • service_credit v1.0 → exception_required                  │
  │    Route: service_impact_exception (≥3 SEV-1)               │
  │                                                               │
  │  APPROVAL ─────────────────────────────────────────────────  │
  │  • finance-lead@ourcompany.com → APPROVED                    │
  │    "Service impact per policy"                               │
  │                                                               │
  │  ACTION ───────────────────────────────────────────────────  │
  │  • billing.create_credit($8,333.40) → success               │
  │    Credit ID: CREDIT-71564                                   │
  │                                                               │
  └───────────────────────────────────────────────────────────────┘

  $ cg search --policy service_credit --since 30d --min-amount 5000

  Found 7 decisions:

    ID              ACCOUNT         AMOUNT    OUTCOME    APPROVED BY
    dec_3f35d5ee    Acme Corp       $8,333    committed  finance-lead
    dec_a1b2c3d4    Globex Inc      $2,160    committed  finance-lead
    dec_e5f6g7h8    Stark Ind       $12,500   denied     —
    ...

  $ cg watch --policy service_credit --outcome denied

  Watching for denied service_credit decisions... (Ctrl+C to stop)

  [10:45:23] dec_xyz789 | Wayne Ent | $15,000 | denied | Exceeded max exception cap
  [10:52:01] dec_abc012 | Oscorp    | $8,000  | denied | No qualifying incidents

  $ cg report --format pdf --period 2025-Q1 --output audit-q1.pdf

  Generating Q1 2025 Audit Report...
  ✓ 342 decisions analyzed
  ✓ 28 exceptions flagged
  ✓ Compliance summary generated
  → Saved to audit-q1.pdf

  Key commands:
  - cg explain <id> — Full decision breakdown
  - cg search — Query with filters
  - cg watch — Real-time streaming
  - cg report — Generate audit packages
  - cg approve — Interactive approval flow

  ---
  4. The Mobile Approval Flow

  Approvals should be async and mobile-first. Don't make managers open a laptop.

  ┌─────────────────────────────────────┐
  │ ◀ ContextGraph            ⋮        │
  ├─────────────────────────────────────┤
  │                                     │
  │  🔔 Approval Required               │
  │                                     │
  │  ┌───────────────────────────────┐  │
  │  │                               │  │
  │  │  Service Credit Exception     │  │
  │  │  ─────────────────────────    │  │
  │  │                               │  │
  │  │  Acme Corporation             │  │
  │  │  $8,333.40 (20%)              │  │
  │  │                               │  │
  │  │  ───────────────────────────  │  │
  │  │                               │  │
  │  │  Why exception needed:        │  │
  │  │  • 3 SEV-1 incidents (30d)    │  │
  │  │  • 14.5 hours downtime        │  │
  │  │  • High churn risk account    │  │
  │  │                               │  │
  │  │  Policy route:                │  │
  │  │  service_impact_exception     │  │
  │  │                               │  │
  │  │  ───────────────────────────  │  │
  │  │                               │  │
  │  │  [View Full Context]          │  │
  │  │  [Compare to Precedent]       │  │
  │  │                               │  │
  │  └───────────────────────────────┘  │
  │                                     │
  │  ┌───────────────┐ ┌─────────────┐  │
  │  │               │ │             │  │
  │  │    DENY       │ │   APPROVE   │  │
  │  │               │ │             │  │
  │  └───────────────┘ └─────────────┘  │
  │                                     │
  │  Or add a note...                   │
  │                                     │
  └─────────────────────────────────────┘

  Key features:
  - Push notification with decision context
  - One-tap approve/deny
  - Voice query: "What's the customer's ARR?"
  - Full context expandable (but summary is enough 80% of time)
  - Batch approve for trusted patterns

  ---
  5. The Narrative Report Generator

  Compliance doesn't want JSON. They want prose.

  ┌─────────────────────────────────────────────────────────────────────┐
  │                                                                      │
  │  CONTEXTGRAPH AUDIT REPORT                                          │
  │  Q1 2025 • Service Credit Exceptions                                │
  │                                                                      │
  │  ═══════════════════════════════════════════════════════════════    │
  │                                                                      │
  │  EXECUTIVE SUMMARY                                                   │
  │  ─────────────────                                                   │
  │  During Q1 2025, the Exception Desk Agent processed 342 service     │
  │  credit requests totaling $127,450. Of these:                       │
  │                                                                      │
  │  • 286 (84%) were within standard policy limits                     │
  │  • 41 (12%) required exception approval                             │
  │  • 15 (4%) were denied                                              │
  │                                                                      │
  │  All exceptions followed documented approval chains. No policy      │
  │  violations were detected.                                          │
  │                                                                      │
  │  ─────────────────────────────────────────────────────────────────  │
  │                                                                      │
  │  EXCEPTION DETAILS                                                   │
  │  ─────────────────                                                   │
  │                                                                      │
  │  Case #1: Acme Corporation                                          │
  │  Decision ID: dec_3f35d5ee                                          │
  │  Date: January 15, 2025                                             │
  │                                                                      │
  │  On January 15, the agent approved a 20% service credit ($8,333)    │
  │  for Acme Corporation (enterprise tier, $500,000 ARR). The request  │
  │  exceeded the standard 10% cap but qualified for the service        │
  │  impact exception due to:                                           │
  │                                                                      │
  │    • 3 SEV-1 incidents within the past 30 days                      │
  │    • 14.5 cumulative hours of service downtime                      │
  │    • Account flagged as high churn risk                             │
  │                                                                      │
  │  The exception was approved by finance-lead@ourcompany.com per      │
  │  policy section 4.2.1 (Service Impact Exception).                   │
  │                                                                      │
  │  Evidence chain:                                                     │
  │    1. Ticket SUP-4312 (Zendesk)                                     │
  │    2. Account record ACC-001 (Salesforce)                           │
  │    3. Incident reports INC-2001, INC-2015, INC-2023 (PagerDuty)    │
  │                                                                      │
  │  [Continue for all 41 exceptions...]                                │
  │                                                                      │
  │  ─────────────────────────────────────────────────────────────────  │
  │                                                                      │
  │  APPENDIX A: Full Decision Records (JSON)                           │
  │  APPENDIX B: Policy Version History                                 │
  │  APPENDIX C: Approver Activity Log                                  │
  │                                                                      │
  └─────────────────────────────────────────────────────────────────────┘

  Key features:
  - LLM-generated narrative from structured data
  - Executive summary + detailed breakdown
  - Evidence chain citations
  - Multiple formats: PDF, DOCX, HTML
  - Scheduled generation (monthly, quarterly)

  ---
  6. The Anomaly Detection Feed

  Push, don't pull. Alert on patterns, not individual records.

  ┌─────────────────────────────────────────────────────────────────────┐
  │                                                                      │
  │  📊 ContextGraph Insights • Dec 31, 2025                            │
  │                                                                      │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  🚨 ANOMALY DETECTED                                        2h ago  │
  │  ───────────────────────────────────────────────────────────────    │
  │  Exception rate spiked to 23% (baseline: 12%)                       │
  │                                                                      │
  │  Contributing factors:                                               │
  │  • 8 credits for "infrastructure issues" in 2 hours                 │
  │  • All from same region: us-east-1                                  │
  │  • Pattern matches incident INC-3042 (ongoing)                      │
  │                                                                      │
  │  Recommendation: Consider blanket credit policy while               │
  │  incident is active to reduce approval overhead.                    │
  │                                                                      │
  │  [View Affected Decisions]  [Acknowledge]  [Create Policy]          │
  │                                                                      │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  ⚠️ POLICY DRIFT                                            1d ago  │
  │  ───────────────────────────────────────────────────────────────    │
  │  Approver "finance-lead" approved 12 consecutive exceptions         │
  │  over past 7 days (historical avg: 3/week)                          │
  │                                                                      │
  │  This may indicate:                                                  │
  │  • Policy too restrictive for current conditions                    │
  │  • Approver fatigue (rubber-stamping)                               │
  │  • Legitimate spike in qualifying cases                             │
  │                                                                      │
  │  [Review Decisions]  [Schedule Policy Review]  [Dismiss]            │
  │                                                                      │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  📈 WEEKLY DIGEST                                           Weekly  │
  │  ───────────────────────────────────────────────────────────────    │
  │  • 89 decisions committed (↑12% vs last week)                       │
  │  • $34,250 in credits issued                                        │
  │  • 7 exceptions approved, 2 denied                                  │
  │  • Avg time-to-approval: 4.2 min                                    │
  │  • Top policy triggered: service_credit (67%)                       │
  │                                                                      │
  │  [Full Report]                                                       │
  │                                                                      │
  └─────────────────────────────────────────────────────────────────────┘

  Key features:
  - Statistical anomaly detection on decision patterns
  - Correlation with external signals (incidents, time of day)
  - Actionable recommendations
  - Digests (daily/weekly/monthly)
  - Alert routing to appropriate channels

  ---
  7. The Deep Investigation View (Rare Use)

  This is the only "dashboard-like" surface — used for deep forensic investigation.

  ┌─────────────────────────────────────────────────────────────────────┐
  │  ContextGraph • Investigation Mode                                   │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  Entity: Acme Corporation (ACC-001)                                 │
  │  Time Range: 2024-01-01 to 2025-01-15                               │
  │                                                                      │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │                    DECISION TIMELINE                         │    │
  │  │                                                              │    │
  │  │  2024                                         2025           │    │
  │  │  ─────────────────────────────────────────────────           │    │
  │  │  │    │    │    │    │    │    │    │    │    │    │    │    │    │
  │  │  J    F    M    A    M    J    J    A    S    O    N    D    J    │
  │  │       ●              ●    ●              ●         ●    ●    │    │
  │  │       │              │    │              │         │    │    │    │
  │  │       │              │    │              │         │    └─ 20% credit
  │  │       │              │    │              │         └─ 5% credit
  │  │       │              │    │              └─ 8% credit            │
  │  │       │              │    └─ Policy warning                      │
  │  │       │              └─ 10% credit (at cap)                      │
  │  │       └─ First interaction                                       │
  │  │                                                              │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  │                                                                      │
  │  ┌─────────────────────────┐ ┌─────────────────────────────────┐    │
  │  │ TOTAL VALUE             │ │ DECISION BREAKDOWN              │    │
  │  │                         │ │                                 │    │
  │  │ $47,833                 │ │  ██████████░░░░░░░ 62% Auto    │    │
  │  │ 6 decisions             │ │  ████░░░░░░░░░░░░░ 25% Exception│    │
  │  │                         │ │  ██░░░░░░░░░░░░░░░ 13% Denied   │    │
  │  └─────────────────────────┘ └─────────────────────────────────┘    │
  │                                                                      │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │ DECISION DETAILS                                             │    │
  │  │                                                              │    │
  │  │  Jan 15, 2025 • dec_3f35d5ee                                │    │
  │  │  ────────────────────────────────────────────────────────   │    │
  │  │  20% credit ($8,333) • COMMITTED                            │    │
  │  │                                                              │    │
  │  │  Evidence:                                                   │    │
  │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │    │
  │  │  │ Ticket   │──│ Account  │──│Incidents │                  │    │
  │  │  │ SUP-4312 │  │ ACC-001  │  │ 3×SEV-1  │                  │    │
  │  │  └──────────┘  └──────────┘  └──────────┘                  │    │
  │  │        │              │             │                        │    │
  │  │        └──────────────┴─────────────┘                        │    │
  │  │                       │                                      │    │
  │  │                       ▼                                      │    │
  │  │               ┌──────────────┐                              │    │
  │  │               │    Policy    │                              │    │
  │  │               │ service_credit│                              │    │
  │  │               │   → exception │                              │    │
  │  │               └──────┬───────┘                              │    │
  │  │                      │                                      │    │
  │  │                      ▼                                      │    │
  │  │               ┌──────────────┐                              │    │
  │  │               │   Approval   │                              │    │
  │  │               │ finance-lead │                              │    │
  │  │               │  → APPROVED  │                              │    │
  │  │               └──────┬───────┘                              │    │
  │  │                      │                                      │    │
  │  │                      ▼                                      │    │
  │  │               ┌──────────────┐                              │    │
  │  │               │    Action    │                              │    │
  │  │               │ create_credit│                              │    │
  │  │               │   $8,333.40  │                              │    │
  │  │               └──────────────┘                              │    │
  │  │                                                              │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  │                                                                      │
  │  [Export]  [Compare to Precedent]  [Generate Report]                │
  │                                                                      │
  └─────────────────────────────────────────────────────────────────────┘

  This is for rare, deep-dive investigations — not daily use.

  ---
  Summary: The Anti-Dashboard Philosophy

  | Traditional Dashboard | Decision Fabric        |
  |-----------------------|------------------------|
  | Destination           | Layer                  |
  | Pull (visit to see)   | Push (comes to you)    |
  | One view for all      | Right view for context |
  | Filter → Find         | Ask → Answer           |
  | Data tables           | Narratives             |
  | Real-time charts      | Anomaly alerts         |
  | Login required        | Embedded everywhere    |

  ---
  Implementation Priority

  If I were building this:

  Phase 1: The 80% Solution
  1. Slack/Teams bot with /why and natural language
  2. CLI tool for engineers
  3. Webhook API for integrations

  Phase 2: Contextual Embedding
  4. CRM/Ticketing sidebar widgets (Salesforce, Zendesk)
  5. Mobile approval flow (PWA)
  6. Email digests

  Phase 3: Intelligence Layer
  7. Anomaly detection + alerts
  8. Narrative report generator
  9. Precedent similarity search

  Phase 4: Deep Investigation (Only if needed)
  10. Visual investigation tool

  ---
  ★ Insight ─────────────────────────────────────
  1. The best audit system is invisible — Users shouldn't "use" ContextGraph; they should get answers where they already work. Every context switch to a separate tool is adoption friction.
  2. LLMs transform structured data consumption — DecisionRecords are perfectly structured for LLM querying. Natural language becomes the query language, and narratives replace data tables.
  3. Push beats pull for compliance — Anomaly detection that finds problems is infinitely more valuable than a dashboard you might check. Compliance wants to be alerted, not to hunt.
  ─────────────────────────────────────────────────





-------------------------------------------------

  ---
  The Hard Truth About the Original Suggestions

  | Suggestion         | User Value  | Revenue Potential | Verdict              |
  |--------------------|-------------|-------------------|----------------------|
  | Slack Bot          | High        | Low               | Free tier hook       |
  | CLI Tool           | High (devs) | None              | Adoption driver      |
  | AI Query Interface | High        | High              | Premium feature      |
  | CRM Sidebar        | Medium      | Low               | Distribution channel |
  | Mobile Approvals   | High        | Medium            | Engagement driver    |
  | Narrative Reports  | Very High   | Very High         | Core revenue         |
  | Anomaly Detection  | High        | High              | Enterprise feature   |
  | Investigation UI   | Medium      | Low               | Table stakes         |

  Core insight: The decision data is not the product. The INTELLIGENCE on top of the data is the product.

  ---
  The Real Product: Compliance Intelligence Platform

  Positioning: "The audit trail your AI agents need. The compliance reports your auditors want."

  Why Compliance is the Wedge

  1. Budget exists — Compliance has dedicated budget. "Cool observability tool" doesn't.
  2. Non-optional — SOC2, SOX, HIPAA, GDPR require audit trails. It's not a nice-to-have.
  3. Pain is acute — Audit prep takes weeks. Automate it and you're a hero.
  4. Buyer is clear — Compliance officer, CISO, CFO. Not "whoever thinks agents are cool."
  5. Timing is now — AI governance is a hot topic. Regulators are asking "what are your agents doing?"

  ---
  The Business Model: Open Core + Usage + Compliance Packages

  ┌─────────────────────────────────────────────────────────────────────┐
  │                                                                      │
  │                    CONTEXTGRAPH BUSINESS MODEL                       │
  │                                                                      │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  OPEN SOURCE (Adoption Funnel)                                      │
  │  ────────────────────────────────────────────────────────────────   │
  │  • SDK for all frameworks (OpenAI, Claude, LangGraph)               │
  │  • Self-hosted server                                               │
  │  • Basic API (ingest + query)                                       │
  │  • CLI tool                                                         │
  │  • 30-day retention                                                 │
  │                                                                      │
  │  Goal: Get into every company building with AI agents               │
  │                                                                      │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  CLOUD PLATFORM (Usage Revenue)                                     │
  │  ────────────────────────────────────────────────────────────────   │
  │  • Managed hosting (no ops burden)                                  │
  │  • Usage-based: $0.001 - $0.01 per decision                        │
  │  • Integrations (Slack, Salesforce, Zendesk)                        │
  │  • Team features (SSO, roles, org management)                       │
  │  • Extended retention (1 year, 7 years for compliance)              │
  │                                                                      │
  │  Goal: Convert OSS users to paid cloud                              │
  │                                                                      │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  AI INTELLIGENCE LAYER (Premium Revenue)                            │
  │  ────────────────────────────────────────────────────────────────   │
  │  • Natural language queries ("Show me all exceptions last month")   │
  │  • Anomaly detection + alerts                                       │
  │  • Risk scoring per agent                                           │
  │  • Precedent similarity search                                      │
  │  • Narrative generation                                             │
  │                                                                      │
  │  Goal: Justify premium pricing via AI costs + value                 │
  │                                                                      │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  COMPLIANCE PACKAGES (Enterprise Revenue)                           │
  │  ────────────────────────────────────────────────────────────────   │
  │  • SOC2 Package: Automated evidence collection + audit reports      │
  │  • SOX Package: Financial controls documentation                    │
  │  • HIPAA Package: Healthcare audit trails                           │
  │  • GDPR Package: Data processing records                            │
  │  • Custom: Work with your compliance team                           │
  │                                                                      │
  │  Goal: $50k-500k enterprise contracts                               │
  │                                                                      │
  └─────────────────────────────────────────────────────────────────────┘

  ---
  Pricing Structure

  Tier Matrix

  |                     | Free      | Team          | Business  | Enterprise    |
  |---------------------|-----------|---------------|-----------|---------------|
  | Price               | $0        | $299/mo       | $999/mo   | Custom        |
  | Decisions/mo        | 5,000     | 50,000        | 500,000   | Unlimited     |
  | Retention           | 30 days   | 1 year        | 3 years   | 7 years       |
  | Users               | 2         | 10            | Unlimited | Unlimited     |
  | Integrations        | CLI only  | Slack, 2 CRMs | All       | Custom        |
  | AI Queries          | ✗         | 100/mo        | Unlimited | Unlimited     |
  | Anomaly Detection   | ✗         | ✗             | ✓         | ✓             |
  | Report Generator    | ✗         | ✗             | Basic     | Full + Custom |
  | Compliance Packages | ✗         | ✗             | Add-on    | Included      |
  | SSO/SAML            | ✗         | ✗             | ✓         | ✓             |
  | SLA                 | None      | 99.9%         | 99.95%    | 99.99%        |
  | Support             | Community | Email         | Priority  | Dedicated CSM |

  Compliance Package Add-Ons

  | Package               | What You Get                                                                               | Price     |
  |-----------------------|--------------------------------------------------------------------------------------------|-----------|
  | SOC2                  | Automated evidence collection, Control mapping, Audit-ready reports, Auditor portal access | $500/mo   |
  | SOX                   | Financial controls documentation, Approval chain verification, Quarterly reports           | $750/mo   |
  | HIPAA                 | PHI access logging, BAA compliance reports, Breach notification support                    | $750/mo   |
  | GDPR                  | Data processing records, Right-to-explain reports, Cross-border transfer logs              | $500/mo   |
  | Full Compliance Suite | All packages + quarterly compliance review call                                            | $2,000/mo |

  ---
  The Product Surfaces, Reframed for Revenue

  1. The Free Tier Experience (Adoption Funnel)

  Goal: Get developers hooked, create organizational dependency.

  # The free experience is CLI-first
  $ pip install contextgraph

  $ cg init  # Sets up local server or connects to cloud
  Initialized ContextGraph. Free tier: 5,000 decisions/month.

  $ cg status
  Decisions this month: 1,247 / 5,000
  Retention: 30 days (upgrade for longer)

  Upgrade triggers:
  - "You've hit 80% of your monthly limit"
  - "Decision dec_xyz will expire in 3 days. Upgrade for longer retention"
  - "Your team member tried to access but you're at 2/2 seats"

  ---
  2. The Slack Bot (Freemium Upsell)

  Free: Basic commands work
  Paid: AI-powered queries require subscription

  ┌─────────────────────────────────────────────────────────────────────┐
  │  #ops-decisions                                                      │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  Sarah Chen                                              10:42 AM   │
  │  /cg why SUP-4312                                                   │
  │                                                                      │
  │  ContextGraph                                            10:42 AM   │
  │  ┌───────────────────────────────────────────────────────────────┐  │
  │  │ Decision: 20% credit for Acme Corp                            │  │
  │  │ Evidence: 3 SEV-1 incidents, 14.5h downtime                   │  │
  │  │ Policy: Exceeded cap, qualified via service_impact_exception  │  │
  │  │ Approved by: finance-lead@company.com                         │  │
  │  │                                                               │  │
  │  │ [View Full Details]                                           │  │
  │  └───────────────────────────────────────────────────────────────┘  │
  │                                                                      │
  │  Sarah Chen                                              10:43 AM   │
  │  Show me all credits over 15% this quarter                          │
  │                                                                      │
  │  ContextGraph                                            10:43 AM   │
  │  ┌───────────────────────────────────────────────────────────────┐  │
  │  │ 🔒 AI Query (Premium Feature)                                 │  │
  │  │                                                               │  │
  │  │ Natural language queries require a Business plan or higher.   │  │
  │  │                                                               │  │
  │  │ Your plan: Team                                               │  │
  │  │                                                               │  │
  │  │ [Upgrade Now]  [Use Filters Instead]                          │  │
  │  └───────────────────────────────────────────────────────────────┘  │
  │                                                                      │
  └─────────────────────────────────────────────────────────────────────┘

  ---
  3. The Compliance Report Generator (Core Revenue Driver)

  This is the killer feature for enterprise sales.

  ┌─────────────────────────────────────────────────────────────────────┐
  │  ContextGraph • Compliance Center                                    │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  ACTIVE COMPLIANCE PACKAGES                                         │
  │  ───────────────────────────────────────────────────────────────    │
  │                                                                      │
  │  ✓ SOC2 Type II                    Status: Audit Ready              │
  │    Last generated: Dec 30, 2025                                     │
  │    Coverage: 99.2% of AI agent decisions                            │
  │    [Generate Report] [Share with Auditor] [View Evidence]           │
  │                                                                      │
  │  ✓ SOX Section 404                 Status: Audit Ready              │
  │    Last generated: Dec 28, 2025                                     │
  │    Financial controls: 47/47 documented                             │
  │    [Generate Report] [Export Controls Matrix]                       │
  │                                                                      │
  │  ───────────────────────────────────────────────────────────────    │
  │                                                                      │
  │  UPCOMING AUDIT                                                      │
  │  ───────────────────────────────────────────────────────────────    │
  │                                                                      │
  │  SOC2 Annual Audit • Jan 15, 2026                                   │
  │  Auditor: Deloitte                                                  │
  │                                                                      │
  │  Preparation status:                                                │
  │  ████████████████████░░░░ 85% Complete                              │
  │                                                                      │
  │  ✓ Decision audit trails (complete)                                 │
  │  ✓ Policy documentation (complete)                                  │
  │  ✓ Approval chain records (complete)                                │
  │  ◐ Exception justifications (12 pending review)                     │
  │  ○ Auditor portal access (not yet shared)                           │
  │                                                                      │
  │  [Complete Remaining Items] [Preview Report] [Share Portal Link]    │
  │                                                                      │
  └─────────────────────────────────────────────────────────────────────┘

  The Auditor Portal (huge enterprise value):

  ┌─────────────────────────────────────────────────────────────────────┐
  │  ContextGraph • Auditor Portal                                       │
  │  Acme Corp SOC2 Audit • Q1 2026                                     │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  Welcome, auditor@deloitte.com                                      │
  │  Access expires: Feb 15, 2026                                       │
  │                                                                      │
  │  ───────────────────────────────────────────────────────────────    │
  │                                                                      │
  │  AUDIT SCOPE                                                        │
  │                                                                      │
  │  • AI Agent Decisions: 45,231 records                               │
  │  • Period: Jan 1, 2025 - Dec 31, 2025                              │
  │  • Agents covered: 12                                               │
  │  • Policies evaluated: 847,293 times                                │
  │                                                                      │
  │  ───────────────────────────────────────────────────────────────    │
  │                                                                      │
  │  CONTROL EVIDENCE                                                    │
  │                                                                      │
  │  CC6.1 - Logical Access Controls                                    │
  │  ┌───────────────────────────────────────────────────────────────┐  │
  │  │ Evidence: All agent actions require policy evaluation before   │  │
  │  │ execution. 100% of write operations have audit trails.        │  │
  │  │                                                               │  │
  │  │ Sample: 50 randomly selected decisions                        │  │
  │  │ [View Sample] [Export Full Dataset]                           │  │
  │  └───────────────────────────────────────────────────────────────┘  │
  │                                                                      │
  │  CC7.2 - System Operations                                          │
  │  ┌───────────────────────────────────────────────────────────────┐  │
  │  │ Evidence: Anomaly detection alerts on 23 occasions.           │  │
  │  │ All alerts were investigated within SLA (avg: 4.2 hours).     │  │
  │  │                                                               │  │
  │  │ [View Alert Log] [View Response Records]                      │  │
  │  └───────────────────────────────────────────────────────────────┘  │
  │                                                                      │
  │  [Download Full Report (PDF)] [Request Additional Evidence]         │
  │                                                                      │
  └─────────────────────────────────────────────────────────────────────┘

  This is worth $50k-500k/year to enterprises. Audit prep that took weeks now takes minutes.

  ---
  4. The Anomaly Detection Engine (Enterprise Retention)

  Free/Team: None
  Business: Pre-built alerts
  Enterprise: Custom ML models + dedicated support

  ┌─────────────────────────────────────────────────────────────────────┐
  │  ContextGraph • Risk Dashboard                                       │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  AGENT RISK SCORES                                                  │
  │  ───────────────────────────────────────────────────────────────    │
  │                                                                      │
  │  exception-desk-agent              Risk: 32 (Low)     ████░░░░░░    │
  │  • 2,341 decisions this month                                       │
  │  • 4.2% exception rate (baseline: 5%)                               │
  │  • 0 policy violations                                              │
  │                                                                      │
  │  customer-support-agent            Risk: 67 (Medium)  ██████░░░░    │
  │  • 8,923 decisions this month                                       │
  │  • 12% exception rate (baseline: 8%) ⚠️                             │
  │  • 3 policy violations (investigated)                               │
  │                                                                      │
  │  billing-automation-agent          Risk: 89 (High)    █████████░    │
  │  • 1,204 decisions this month                                       │
  │  • 23% exception rate (baseline: 5%) 🚨                             │
  │  • 12 policy violations (7 pending review)                          │
  │  • [Investigate] [Pause Agent] [Adjust Policies]                    │
  │                                                                      │
  │  ───────────────────────────────────────────────────────────────    │
  │                                                                      │
  │  ACTIVE ALERTS                                                       │
  │                                                                      │
  │  🚨 HIGH  Billing agent exception rate 4x baseline      2h ago      │
  │           12 consecutive exceptions approved                         │
  │           [View Decisions] [Investigate]                             │
  │                                                                      │
  │  ⚠️ MED   Unusual approval pattern detected             1d ago      │
  │           Same approver for 89% of exceptions this week             │
  │           [View Pattern] [Acknowledge]                               │
  │                                                                      │
  │  ℹ️ LOW   New policy version deployed                    3d ago      │
  │           service_credit v1.1 - monitoring for drift                │
  │           [View Policy] [Set Alert Thresholds]                       │
  │                                                                      │
  └─────────────────────────────────────────────────────────────────────┘

  Why this retains enterprise customers:
  - Creates dependency on the risk insights
  - Justifies ongoing subscription ("we caught 12 issues this quarter")
  - Provides ammunition for internal champions ("look what we prevented")

  ---
  5. The AI Query Layer (Premium Differentiator)

  This is where LLM costs justify premium pricing.

  ┌─────────────────────────────────────────────────────────────────────┐
  │  ContextGraph • Intelligence                                         │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  Ask anything about your decisions...                               │
  │  ┌───────────────────────────────────────────────────────────────┐  │
  │  │ Which customers received credits above policy limits, and     │  │
  │  │ what was the business justification for each?                 │  │
  │  └───────────────────────────────────────────────────────────────┘  │
  │                                                                      │
  │  ───────────────────────────────────────────────────────────────    │
  │                                                                      │
  │  Found 7 credits above policy limits in the past 90 days:          │
  │                                                                      │
  │  1. **Acme Corporation** - 20% ($8,333)                            │
  │     Justification: 3 SEV-1 incidents caused 14.5 hours of          │
  │     downtime. Customer threatened churn. Approved via              │
  │     service_impact_exception route.                                 │
  │     → Approver: finance-lead@company.com                           │
  │                                                                      │
  │  2. **Globex Industries** - 18% ($2,160)                           │
  │     Justification: High churn risk account (health score: 35).     │
  │     Proactive retention effort during renewal period.               │
  │     → Approver: vp-sales@company.com                               │
  │                                                                      │
  │  3. **Stark Industries** - 25% ($12,500) ⚠️                        │
  │     Justification: CEO escalation after public complaint.          │
  │     Note: This exceeded max exception cap (20%). Manual override.   │
  │     → Approver: cfo@company.com                                    │
  │                                                                      │
  │  [Continue...] [Export to PDF] [Create Report]                      │
  │                                                                      │
  │  ───────────────────────────────────────────────────────────────    │
  │                                                                      │
  │  Follow-up questions:                                               │
  │  • "What's the total cost of these exceptions?"                     │
  │  • "How does this compare to last quarter?"                         │
  │  • "Show me the approval chain for Stark Industries"                │
  │                                                                      │
  └─────────────────────────────────────────────────────────────────────┘

  Pricing justification: LLM inference costs + high perceived value = premium feature.

  ---
  6. The Policy Marketplace (Platform Revenue)

  New revenue stream: Let customers buy/sell policies.

  ┌─────────────────────────────────────────────────────────────────────┐
  │  ContextGraph • Policy Marketplace                                   │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  FEATURED POLICIES                                                  │
  │  ───────────────────────────────────────────────────────────────    │
  │                                                                      │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │ 💰 Financial Services Compliance Pack              $299/mo  │    │
  │  │                                                             │    │
  │  │ 15 pre-built policies for fintech:                         │    │
  │  │ • Transaction limits with tiered approval                  │    │
  │  │ • AML/KYC verification requirements                        │    │
  │  │ • Suspicious activity detection                            │    │
  │  │ • Regulatory reporting triggers                            │    │
  │  │                                                             │    │
  │  │ Used by: 47 companies                                      │    │
  │  │ Rating: ★★★★★ (4.9)                                        │    │
  │  │                                                             │    │
  │  │ [Preview] [Install]                                        │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  │                                                                      │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │ 🏥 Healthcare HIPAA Policy Pack                    $199/mo  │    │
  │  │                                                             │    │
  │  │ 12 policies for healthcare AI:                             │    │
  │  │ • PHI access logging                                       │    │
  │  │ • Minimum necessary principle                              │    │
  │  │ • Breach notification triggers                             │    │
  │  │ • Patient consent verification                             │    │
  │  │                                                             │    │
  │  │ Used by: 23 companies                                      │    │
  │  │ Rating: ★★★★☆ (4.7)                                        │    │
  │  │                                                             │    │
  │  │ [Preview] [Install]                                        │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  │                                                                      │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │ 🌐 GDPR Data Processing Pack                        Free    │    │
  │  │ By: ContextGraph Team                                      │    │
  │  │                                                             │    │
  │  │ [Preview] [Install]                                        │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  │                                                                      │
  │  [Browse All] [Submit Your Policy]                                  │
  │                                                                      │
  └─────────────────────────────────────────────────────────────────────┘

  Revenue model:
  - ContextGraph takes 30% of marketplace sales
  - Creates ecosystem lock-in
  - Drives vertical specialization without ContextGraph building everything

  ---
  7. Benchmark Data (Network Effect Revenue)

  New feature: Anonymized, aggregated insights across customers.

  ┌─────────────────────────────────────────────────────────────────────┐
  │  ContextGraph • Industry Benchmarks                                  │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                      │
  │  YOUR METRICS VS. INDUSTRY                                          │
  │  ───────────────────────────────────────────────────────────────    │
  │                                                                      │
  │  Exception Rate                                                      │
  │  ─────────────────────────────────────────────────────────────      │
  │                                                                      │
  │  You:        ████████░░░░░░░░░░░░  8.2%                             │
  │  Industry:   ██████░░░░░░░░░░░░░░  6.1%                             │
  │  Top 10%:    ███░░░░░░░░░░░░░░░░░  3.2%                             │
  │                                                                      │
  │  ⚠️ Your exception rate is 34% above industry average.              │
  │  [See recommendations]                                               │
  │                                                                      │
  │  ─────────────────────────────────────────────────────────────      │
  │                                                                      │
  │  Approval Latency (median)                                          │
  │  ─────────────────────────────────────────────────────────────      │
  │                                                                      │
  │  You:        ████████████░░░░░░░░  4.2 hours                        │
  │  Industry:   ████████████████░░░░  6.8 hours                        │
  │  Top 10%:    ████░░░░░░░░░░░░░░░░  1.1 hours                        │
  │                                                                      │
  │  ✓ You're 38% faster than industry average!                         │
  │                                                                      │
  │  ─────────────────────────────────────────────────────────────      │
  │                                                                      │
  │  Policy Violation Rate                                              │
  │  ─────────────────────────────────────────────────────────────      │
  │                                                                      │
  │  You:        █░░░░░░░░░░░░░░░░░░░  0.3%                             │
  │  Industry:   ████░░░░░░░░░░░░░░░░  1.8%                             │
  │                                                                      │
  │  ✓ Excellent! You're in the top 5% for policy compliance.           │
  │                                                                      │
  └─────────────────────────────────────────────────────────────────────┘

  Why this matters:
  - Creates network effect (more customers = better benchmarks)
  - Justifies premium pricing ("see how you compare")
  - Provides defensible competitive moat
  - Drives behavior change ("we need to improve our exception rate")

  ---
  Go-To-Market Strategy

  Phase 1: Developer-Led Growth (Months 1-6)

  Open Source SDK → Developer Adoption → Team Upgrades
       ↓                    ↓                  ↓
    GitHub stars        CLI users         $299/mo ARR

  Tactics:
  - Publish SDK on PyPI/npm
  - Great docs + quickstarts
  - Conference talks ("Observability for AI Agents")
  - Integrations with popular frameworks
  - Free tier is genuinely useful

  Metrics: GitHub stars, SDK downloads, free tier signups

  Phase 2: Compliance-Led Sales (Months 6-12)

  Compliance Pain Point → Demo Report Generator → Enterprise Contract
           ↓                       ↓                      ↓
    "Audit is coming"      "This saves weeks"       $50k-500k ARR

  Tactics:
  - Target regulated industries (fintech, healthcare, insurance)
  - Lead with audit prep pain point
  - Partner with compliance consultants
  - SOC2/SOX/HIPAA content marketing
  - Case studies: "How X passed their audit with ContextGraph"

  Metrics: Enterprise pipeline, ACV, compliance package attach rate

  Phase 3: Platform Expansion (Months 12-24)

  Policy Marketplace → Vertical Specialization → Platform Lock-in
          ↓                      ↓                      ↓
    30% rev share        "ContextGraph for X"    High switching costs

  Tactics:
  - Launch policy marketplace
  - Recruit vertical experts to build policy packs
  - Partner with AI framework vendors (OpenAI, Anthropic, LangChain)
  - Build ecosystem of integrations
  - Benchmark data as competitive moat

  Metrics: Marketplace GMV, partner count, benchmark coverage

  ---
  Unit Economics

  Assumptions (Year 1)

  | Metric                  | Value  |
  |-------------------------|--------|
  | Free users              | 10,000 |
  | Free → Team conversion  | 5%     |
  | Team customers          | 500    |
  | Team → Business upgrade | 20%    |
  | Business customers      | 100    |
  | Enterprise customers    | 10     |

  Revenue Model

  | Tier               | Customers | MRR/Customer | MRR      |
  |--------------------|-----------|--------------|----------|
  | Team               | 500       | $299         | $149,500 |
  | Business           | 100       | $999         | $99,900  |
  | Enterprise         | 10        | $8,333       | $83,330  |
  | Compliance Add-ons | 50        | $750         | $37,500  |
  | Total MRR          |           |              | $370,230 |
  | ARR                |           |              | $4.4M    |

  Cost Structure

  | Cost                        | % of Revenue |
  |-----------------------------|--------------|
  | Infrastructure (cloud, LLM) | 15%          |
  | Engineering                 | 40%          |
  | Sales & Marketing           | 25%          |
  | G&A                         | 10%          |
  | Gross Margin                | 60%          |

  ---
  Competitive Moat Summary

  | Moat                 | How It Works                                             |
  |----------------------|----------------------------------------------------------|
  | Integration Depth    | Once you're the audit layer, switching is painful        |
  | Compliance Expertise | Templates, reports, auditor portals are domain knowledge |
  | Benchmark Data       | More customers = better benchmarks = network effect      |
  | Policy Marketplace   | Ecosystem of policies creates lock-in                    |
  | AI Layer             | Proprietary models trained on decision data              |

  ---
  What I'd Build First

  If I were doing this as a funded startup:

  Quarter 1: Foundation
  - Open source SDK (all 3 frameworks)
  - Cloud service (ingest + basic query)
  - CLI tool
  - Free + Team tiers
  - Target: 1,000 free users, 50 Team customers

  Quarter 2: Enterprise Hooks
  - Slack integration
  - SSO/SAML
  - Basic compliance reports (SOC2 template)
  - Business tier launch
  - Target: 200 Team, 20 Business, 2 Enterprise pilots

  Quarter 3: Compliance Push
  - Full compliance report generator
  - Auditor portal
  - SOX/HIPAA packages
  - Enterprise sales team hire
  - Target: 5 Enterprise contracts ($50k+ ACV)

  Quarter 4: Intelligence Layer
  - AI query interface
  - Anomaly detection
  - Benchmark data
  - Policy marketplace MVP
  - Target: $300k ARR, 10 Enterprise customers

  ---
  Summary: The Money Filter

  | Original Suggestion      | Revenue Verdict        | What Changes                   |
  |--------------------------|------------------------|--------------------------------|
  | Slack Bot                | Free hook → Premium AI | Basic free, NL queries paid    |
  | CLI Tool                 | Free forever           | Adoption driver only           |
  | AI Query Interface       | Core premium           | Business tier+ only            |
  | CRM Sidebar              | Distribution channel   | Free, drives awareness         |
  | Mobile Approvals         | Team+ feature          | Engagement/retention           |
  | Narrative Reports        | Enterprise core        | Compliance package centerpiece |
  | Anomaly Detection        | Business+ feature      | Risk management upsell         |
  | Investigation UI         | Table stakes           | Include in all paid tiers      |
  | NEW: Compliance Packages | $500-2k/mo add-ons     | SOC2/SOX/HIPAA bundles         |
  | NEW: Policy Marketplace  | 30% rev share          | Platform play                  |
  | NEW: Benchmark Data      | Network effect moat    | Premium feature                |

  ---
  ★ Insight ─────────────────────────────────────

  1. Compliance is the wedge, not observability — "Pass your SOC2 audit" has budget. "Better visibility into agents" doesn't. Lead with compliance, expand to operations.
  2. Open source is a funnel, not the product — The OSS SDK drives adoption. The SaaS intelligence layer is the product. Don't monetize the data layer; monetize the insight layer.
  3. AI features justify premium pricing — LLM costs are real, so charging for AI queries is defensible. But more importantly, natural language over structured data feels magical and is worth paying for.
  4. Benchmark data creates network effects — "Your exception rate vs. industry" requires aggregated data across customers. More customers = better benchmarks = more value = more customers. This is the path to defensibility.
  5. Vertical specialization beats horizontal — "ContextGraph for Fintech" with pre-built SOX policies and banking-specific reports commands 3-5x the price of generic ContextGraph. Verticalization is the pricing moat.
