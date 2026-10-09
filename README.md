# Cart-GMP-Budget v4 — single-construct, single-planned-lot policy

**Fixed program architecture:** ONE retroviral CAR vector construct, ONE planned GMP vector production lot, and multiple patient-specific autologous CAR-T manufacturing batches to target 12 successful infusions. Vector development and tech transfer are charged once. Vector manufacturing and lot-release QC are charged per actual attempted lot, initially one. **No scenario automatically adds vector lots.**

## Capacity control
Low/base/high assumptions retain illustrative nominal vector capacity per released lot (16/12/8 CAR-T manufacturing starts); these are NOT vendor-confirmed. The model calculates a `vector_demand_gap` and `vector_capacity_warning` instead of silently buying more lots. If one lot is insufficient, obtain actual titer, usable volume, transduction consumption per patient, release yield, reserve and expiry evidence, then explicitly authorize any additional lot via `vector_extra_lots_authorized`. Even if nominal capacity passes, one-lot sufficiency is **not verified** without CDMO evidence; one-lot release failure remains a material risk.

## Files and running
- `GMP_CAR_T_Budget_v4.xlsx`: prior v3 workbook preserved and revised with single-lot policy sheet; v3 patient-funnel calculations remain illustrative.
- `src/model.py`: probability-assured screened-patient planning and fixed vector lot policy.
- `config/scenarios.json`: editable scenario assumptions and lot authorization.
- `tests/`: automated checks.
Run `python src/model.py` and `python -m unittest discover -s tests -v`.

**No supplier prices are verified. No budget total is approved.** Hospital costs remain separate from GMP manufacturing.
