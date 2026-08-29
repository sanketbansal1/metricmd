# Assumptions

Stated up front, as the brief requires. Anything not listed here is either in the contract or in the code.

## The modeled business
1. UrbanBasket Retail is a simulated quick-commerce grocer: 4 regions (North, South, East, West), 4 categories, 3 channels, roughly 45 lakh INR revenue a day at baseline. Scale chosen so a regional category slice is large enough for statistics and small enough that one mechanism visibly moves it.
2. Demand has weekly seasonality only (weekend lift up to 18%). No annual seasonality or festivals in the simulation window; a production deployment would extend the baseline model, not the architecture.
3. Daily noise is Gaussian at 4.5% of the slice mean. Real retail is heavier-tailed; the robust z on residuals and the isolated-spike filter exist precisely because we assume some days lie.

## Sources and grains
4. POS sales land nightly with a 6 hour lag, marketing spend is weekly with a 72 hour lag, ops tickets stream hourly. The engine never joins across grains silently: weekly marketing evidence is labeled with its grain in the evidence line.
5. Ticket text is realistic but templated. Keyword retrieval thresholds (6 delay mentions, 4 supply mentions in a window) were tuned on the harness, and would be re-tuned per client on two weeks of history.

## Thresholds, all of them
6. z threshold 3.0 per day, window mean gate 1.6, materiality floor 25,000 INR per slice per 14 days, minimum history 42 days, confidence floor for naming a cause 0.50, confident tier at 0.70 with 0.15 margin. Each lives in `contract.yaml`, not in code, because a threshold you cannot see is a threshold you cannot govern.
7. Shape classifier constants (slide slope below minus 1.2 over at least 8 post-onset days, cliff depth below minus 5 with at most 4 deep days) were fixed BEFORE the final harness run and not tuned to it afterward. The scorecard is what the frozen engine measured.

## Mechanisms
8. Price elasticity is 2.0 on rises and 1.8 on discounts, constant across categories. Crude but directionally standard for grocery; the diagnosis logic depends on the sign and the corroborating price evidence, not the exact elasticity.
9. A competitor entry bites 1.8 to 2.6% additional units a day, compounding, capped at 30%. A stockout removes 50 to 80% of a category's units for 2 to 3 days.

## Evaluation
10. The harness plants one world per case and scores blind. Ground truth is the planted label. An AMBIGUOUS verdict that contains the true cause is scored correct for the two-cause world only.
11. Three seeds per case (73 total runs) is enough to expose seed sensitivity but not a full sensitivity study; the seed-3 cluster of weak-signal misses is visible in the results file on purpose.

## LLM and cost
12. Token price assumed 0.35 INR per 1,000 tokens, the current commercial mid-band. The default narrator uses zero tokens; the 3 to 5 INR per diagnosis figure in the proposal assumes one LLM narrative call per confident diagnosis plus retries.
13. The RBAC demo enforces row security at the narrative layer from the contract. A production system would additionally push predicates into the SQL layer; the contract already carries the information needed to do so.
