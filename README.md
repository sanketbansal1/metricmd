# MetricMD

**The diagnosis layer for business metrics.** Dashboards report WHAT changed. MetricMD tells you WHY, tests its own answer against a control group, refuses to guess when the evidence is thin, and comes back later to check whether its own prescription worked.

Team Phoenix, IIT Kanpur. Accenture Innovation Challenge 2026, Round 2, Track 3 (BusinessIntelligence.ai).

Built by Kalpak Agrawal, Sanket Bansal, Karmanya Goyal.


## The one number that matters

We do not ask you to trust the engine. We measured it. `harness.py` plants **73 labeled runs** (8 mechanisms, 3 random seeds, weak signals, a two-cause world, a sparse-history world, 12 clean series) and scores the engine blind:

| Metric | Result | Meaning |
|---|---|---|
| Detection recall on planted movements | **88.5%** (54/61) | material movements caught |
| Diagnosis accuracy, top 1 named cause | **80.0%** (44/55) | the fingerprint named is the planted one |
| False alarm rate on clean series | **0.0%** (0/12) | tuned so a quiet dashboard stays quiet |
| Correct honest UNKNOWN rate | **83.3%** (5/6) | novel causes get UNKNOWN, not a guess |
| Wrong but confident answers | **1 of 73 runs (1.4%)** | the failure mode that destroys trust |

Every miss has a name: 8 of 12 failures are the engine staying QUIET on deliberately weak signals (the price we pay for a zero false alarm rate), 3 are safe UNKNOWNs, 1 is a genuine error. Reproduce it yourself: `python harness.py`.

## The truth boundary (the brief's core mandate, implemented)

> "The LLM should not be treated as the source of quantitative truth."

In MetricMD this is architecture, not a slogan. The pipeline is six deterministic stages, and the LLM is legal in exactly one place:

| Stage | Method | LLM allowed? |
|---|---|---|
| DETECT | day-of-week seasonal baseline + robust z on residuals (statistics) | No |
| LOCALIZE | contribution decomposition across contract dimensions (SQL + algebra) | No |
| DIAGNOSE | feature probes matched against a fingerprint library (business rules) | No |
| FALSIFY | control-group test across untouched regions (statistics) | No |
| VERIFY | post-action recheck against the expected band (statistics) | No |
| NARRATE | phrase the evidence list, cite every sentence | **Yes, phrasing only** |

Every fact carries an evidence id (E1, E2, ...) with its method and source system. The narrative layer may only phrase facts that exist in that list. By default the prototype ships with a deterministic template narrator (zero keys, zero cost); set `METRICMD_LLM=1` to route the same evidence JSON through a model under the phrase-only instruction. Either way, every number exists before the narrator is loaded.

## Quick start (3 commands, 1 dependency)

```bash
pip install pyyaml
python harness.py     # regenerate data, run all 62 scored scenarios
python demo.py        # the four-story walkthrough below
python dashboard.py   # renders the same run as dashboard.html, open it in a browser
python export_frontend.py && python api.py   # JSON API on :8000 for the React console
```

`dashboard.html` is the product face: the four diagnosis cards with sparklines drawn from the actual generated data, confidence bars, evidence chips with method and source, the entitlement block and live telemetry. Every string and number on it is engine output; the engine writes the page.

Pure Python standard library everywhere except YAML parsing. No API keys required.

## The four-story demo

`demo.py` builds one simulated quarter with four planted realities and walks them end to end:

1. **The dip with a cause in no table** (North / Dairy). Revenue drops 9%. No sales column explains it. The engine pulls avg delivery time from POS (11 to 18 min), retrieves ticket text citing rider delays from the ops system, diagnoses `delivery_degradation` at 0.72, prescribes the contract playbook, then **rechecks 10 days later and reports RESOLVED, diagnosis confirmed**. No rival engine audits its own advice.
2. **The slow bleed** (West / Beverages). Minus 2% a week, never a single-day alarm. Trajectory classification catches the slide, the control test proves it is local to West, diagnosis `competitor_entry` at 0.80.
3. **The win, explained** (East / Household). A +7% lift gets the same treatment: `discount_launch`, price evidence cited, promo ROI action. Wins deserve explanations too.
4. **The honest unknown** (South / Household). A shock no fingerprint fits. Best score 0.45, below the confidence floor. The engine says UNKNOWN, routes a question to the nearest human, and the answer becomes a new fingerprint. Refusing to guess is a feature.

Plus: an entitlement block (Priya, contract-scoped to North, asks about West and is refused with an audit log), executive vs analyst narrative depth, and runtime telemetry (83 ms full pipeline, token and INR cost meters).

## Rubric coverage, checkboxed

| Round 2 minimum expectation | Where |
|---|---|
| 3 to 5 connected KPIs, 2 to 3 sources, different grains and cadences | `contracts/contract.yaml`: net_revenue, units_sold, avg_delivery_min over daily POS, weekly marketing, event-grain tickets |
| Lightweight semantic contract (definitions, drivers, thresholds, lineage, access) | `contracts/contract.yaml`, the engine knows nothing outside it |
| Two personas with different narratives and actions | regional_head (executive, lever-scoped) vs central_analyst (full depth) |
| One multi-factor movement with known drivers | harness `double-cause` world (delivery degradation + price rise together) |
| One low-confidence abstention scenario | Story D plus 6 UNKNOWN harness runs |
| One sparse-history scenario | harness `sparse-1`: 40 days of history, contract floor is 42, engine abstains by rule |
| One role-based security scenario | entitlement block in `demo.py`, enforced from the contract |
| Evidence with freshness, method, contribution, confidence, lineage | every evidence id carries method + source; confidence is a scored blend |
| Clear LLM vs non-LLM breakdown | table above, enforced in `narrate.py` |
| Runtime telemetry: latency, model calls, tokens, cost | `Telemetry` class, printed in every demo run |

## Repository layout

```
contracts/contract.yaml   semantic contract, the single source of truth
metricmd/datagen.py       three mismatched source systems, plantable mechanisms
metricmd/engine.py        the deterministic core, six stages, zero LLM
metricmd/narrate.py       the only file where an LLM may appear, RBAC, feedback
harness.py                62-scenario blind evaluation, the scorecard
dashboard.py              renders the engine's output as a styled HTML dashboard
export_frontend.py        runs the engine, exports data/frontend_data.json
api.py                    zero dependency JSON API with server side entitlements,
                          evidence masking, and feedback that persists mechanism
                          priors and draft fingerprints (POST /api/feedback)
docs/LOVABLE_PROMPT.md    the full prompt used to build the React console
demo.py                   the four-story walkthrough
docs/ARCHITECTURE.md      system diagram and design decisions
docs/BUSINESS_PROPOSAL.md problem, market, pricing, roadmap, risks
ASSUMPTIONS.md            every assumption, stated as the brief requires
```

## What is honestly simulated vs real

Real and running: multi-source SQL reconciliation, seasonal detection, contribution analysis, fingerprint diagnosis, control-group falsification, post-action verification, abstention, RBAC, feedback capture, telemetry, and the 62-case measurement of all of it. Simulated: the business data itself (three generated source systems, as the brief instructs) and the LLM call is an optional hook so the repo runs with zero keys. The fingerprint library ships with 8 mechanisms; the production vision is roughly 30, grown by the UNKNOWN-to-fingerprint loop.
