# MetricMD Business Proposal
### Team Phoenix, IIT Kanpur. Accenture Innovation Challenge 2026, Round 2, BusinessIntelligence.ai

## 1. Problem framing

Every operating review in India runs on the same broken loop. A dashboard turns red on Monday. An analyst is assigned on Tuesday. SQL is written, five source systems disagree, a marketing calendar is checked by hand, and by Friday a slide says "revenue fell 8%, likely due to supply issues", with no evidence trail and no way to know if "likely" meant 90% or 40%. Snowflake paid roughly 250 million dollars for Sisu in 2023 to attack exactly this gap, and the diagnostic-analytics category it validated remains unsolved for mid-market India: metric monitoring tools (Anomalo, Metaplane, Monte Carlo) tell you THAT something moved, and BI copilots write fluent prose about WHAT moved, but nobody ships the WHY with evidence, a falsification test, and a follow-up.

The cost is concrete. A regional business head managing a 120 crore INR quarter loses 3 to 4 days per unexplained movement, and the wrong explanation is worse than none: acting on "it is a demand problem" when the cause was delivery degradation spends promo budget to fix a logistics fault. The brief's own golden rule names the trap precisely: an LLM asked "why did revenue fall" will always produce a confident paragraph, and that is the problem, not the solution.

## 2. Solution design

MetricMD is the diagnosis layer that sits between the warehouse and the executive. Six deterministic stages (DETECT, LOCALIZE, DIAGNOSE, FALSIFY, VERIFY, NARRATE) run against a semantic contract that declares every KPI, threshold, persona, entitlement and playbook. The distinctive assets:

- **The fingerprint library.** Business failure modes have shapes in data: a stockout is a cliff with a rebound, a competitor is a slow geo-bounded slide, a campaign end is a spike that returns. MetricMD ships 8 machine-checkable fingerprints (production vision roughly 30), each carrying its corroborating probes, its playbook, its owner and its expected recovery horizon.
- **Falsification.** Every localized diagnosis is attacked with a control-group test across untouched regions before it reaches a human. Explanations that fail die in the engine, not in a meeting.
- **Verification.** Every playbook has a recovery horizon; after it passes, the engine rechecks its own diagnosis and reports RESOLVED or NOT RESOLVED. MetricMD is the only entrant whose product audits its own advice.
- **Honest abstention that compounds.** Below the confidence floor the engine says UNKNOWN, routes one question to the nearest owner, and the answer becomes a new fingerprint. The library, and therefore the moat, grows with every deployment week.
- **The truth boundary.** The LLM exists in one file, in phrase-only mode, citing computed evidence ids. The prototype runs fully with the LLM disabled, which is the strongest possible proof that it is not the source of quantitative truth.

Measured, not promised: across 73 blind planted runs the frozen engine scores 88.5% detection recall, 80.0% top-1 diagnosis accuracy, 0.0% false alarms, 83.3% correct abstention, and exactly one wrong-confident answer.

## 3. Target users

Primary: regional and category P&L owners in retail, quick commerce, CPG and D2C (the Priya persona: 120 crore INR quarterly book, no SQL, needs the cause, the action and the owner in one card). Secondary: central analytics teams (the Dev persona: full evidence trail, ambiguity cards with separating tests, feedback controls). The wedge market is India's roughly 400 mid-market retail and consumer companies with 500 to 5,000 crore INR revenue: rich enough to have 5-plus source systems that disagree, too lean to park an analyst on every anomaly.

## 4. Business case

- Pricing: 16 lakh INR per year per business unit (roughly the loaded cost of one junior analyst, replacing the diagnostic toil of several).
- Unit economics: a diagnosis run costs 3 to 5 INR (one LLM narrative call; the deterministic core is compute-trivial at 83 ms per full four-story run). Gross margin above 85% at scale.
- Serviceable market: 400 target firms at an average 2.5 business units gives a 160 crore INR annual India SOM; the global diagnostic analytics category (TAM roughly 35 billion USD, SAM 8 billion USD) is validated by the Sisu acquisition and by every BI vendor's copilot roadmap.
- Break-even at roughly 8 paying business units, inside year one of commercial deployment.
- Moat: the fingerprint library is earned, not scraped. Every honest UNKNOWN converted by a customer's own ops lead becomes proprietary diagnostic knowledge that transfers across customers as priors, the way a physician's casebook compounds.

## 5. Phased roadmap

- Phase 0 (now): this prototype. Simulated sources, 8 fingerprints, measured scorecard.
- Phase 1 (months 1 to 4): first design partner on live warehouse data. Connectors for BigQuery, Snowflake, Postgres. Contract authoring UI. Target: explained-change coverage of 70% on the partner's top 5 KPIs.
- Phase 2 (months 5 to 9): fingerprint library to 30 mechanisms, feedback-weighted priors in production, Slack and email delivery, verification loops on by default.
- Phase 3 (months 10 to 18): multi-tenant SaaS, cross-customer prior transfer with contractual data isolation, SOC 2, marketplace of industry contract templates (grocery, fashion, pharmacy).

North star metric: Explained-Change Coverage, the share of material KPI movements that receive an accepted diagnosis, target at least 70%. Guardrails: wrong-confident rate below 2%, median time-to-explanation under 5 minutes from data landing.

## 6. Risks with mitigations

- **Wrong confident diagnosis erodes trust** (observed once in 73 runs). Mitigation: confidence floors and margins are contract-governed, Flag feedback demotes fingerprint priors regionally, and the wrong-confident rate is itself a tracked guardrail metric.
- **Client data too messy for the contract.** Mitigation: the contract is deliberately lightweight (one YAML file), onboarding starts with 3 KPIs not 300, and the sparse-history rule refuses to diagnose what it cannot support.
- **LLM cost or availability drift.** Mitigation: the product is fully functional in template mode; the LLM is an upgrade, not a dependency, and per-diagnosis token budgets are metered in telemetry.
- **Incumbent BI vendors bundle a copilot.** Mitigation: copilots summarise, MetricMD falsifies and verifies; the library moat and the abstention discipline are years of earned casework, not a feature toggle.
- **Simulation-to-production gap.** Mitigation: Phase 1 is scoped to one design partner precisely to re-tune thresholds on live data, and every threshold lives in the contract where the client can see and govern it.
