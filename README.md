# CAR-T v11 — Evidence-first budgeting workflow

## Quick start
1. Open **CAR_T_Costing_v11_Colab.ipynb** in Google Colab.
2. Run all cells. No input file upload required. Search up to all 136 items, including SKU-first public product search.
3. Inspect **CAR_T_Budget_v11.xlsx**: Catalog classification, Search diagnostics, Web price evidence, RFQ register, FX rates, Budget scenarios, Line item costs, Approved quotes, Audit.
4. Do NOT mark extracted prices approved without checking grade, SKU, pack size, shipping, VAT, currency, purchasing region, and quote validity.
5. Fill **approved_quotes.csv** with evidence-backed prices, quote ID, approver, and price scope UNIT/PACK. Rerun section 4 without web search.

## Important model assumptions
- Goal: 12 successful infused patients with 90% chance of reaching target (screening count via binomial survival function).
- Default scenarios: both screening and manufacturing-release probabilities are 50%, 70%, 90%. Optional collection-to-start and release-to-infusion probabilities default to 1.0. Actual stage rates should replace them.
- Screening starts use planning n; downstream run costs use expected event counts. This is an **expected-cost planning approximation**, not a 90th percentile cash requirement.
- Costs separated by drivers: per screened, collection, start, completed, released, infused, vector lot, program, month, year. Please assess if any release test is triggered per attempted batch vs successful release.
- PACK prices use ceiling(total project use / pack quantity). This assumes pooled stock, no expiry/waste/MOQ; validate independently.
- All candidate prices remain CANDIDATE_REVIEW; only manually APPROVED entries with evidence and approver contribute to priced subtotal. Missing prices = INCOMPLETE total, never zero.
- Currency conversion uses live available reference FX date from Frankfurter API. On FX failure conversions remain blank; do not silently substitute a stale rate. FX rates are indicative; procurement card/bank spreads are excluded.
- An infectious-disease item under release-associated donor/patient safety remains separately identified as donor/patient screening, **not final-product sterility or release testing**.
- Data anonymity: general program and provider types; no named clinical manufacturing institution.

## Limitations and next audit steps
- Public search engines block scraping unpredictably. Bing RSS and Google HTML search are best-effort only, not guaranteed production-grade price APIs. Consider licensed provider APIs or vendor price catalog exports when available.
- Candidate price regex has false-positive risk even with SKU check. Candidate sources must be manually verified.
- Quoted costs may be local, confidential, VAT excluded, or non-GMP; never treat website retail prices as GMP contractual prices.
- Full budget excludes unresolved line items and price risk until they are approved. No false project total is shown.
- Phase classification and event drivers must be validated against process SOPs and executed agreements.

## Run outside Colab
`pip install pandas requests beautifulsoup4 scipy xlsxwriter openpyxl`
`python cost_engine.py`
Set `ONLINE=0` for an offline model-only verification; `SEARCH_LIMIT=10` for short online smoke tests.

## Files
- `CAR_T_Costing_v11_Colab.ipynb`: standalone notebook embeds code and 136-item source CSV.
- `cost_engine.py`: equivalent command line engine.
- `timeline_cost_catalog.csv`: original generalized BOM with 136 items.
- `CAR_T_Budget_v11.xlsx`: **offline preview** (unquoted, incomplete), not a price-validated cost estimate.
