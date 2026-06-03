# Synthesis log — `data/csv/GOLD_fct_pcs_report.csv`

Real Jan 2026 rows were copied unchanged from `input/Archive/inputs/02 Fabric Results in csv format/csv results/`.
Synthetic Dec 2025 and Feb 2026 rows were derived by applying the deliberate transitions documented below, so the period selector tells a coherent month-over-month story.

When real Fabric exports become available for these months, replace `GOLD_fct_pcs_report.csv` here and re-run `csv_to_jsons.py`.

---

### December 2025 (REF_PERIOD=202512)
Generated from Jan 2026 baseline by reversing 1 month of portfolio progression.

- **Scaled YTD spend** × 0.20 (1 month vs 4 months cumulative)
- **2025-00159** 3D HRSG Scanning: RAG_ID 15 → 14 (Green) — became flagged in Jan
- **2025-00127** Steam Turbine Major Inspection: RAG_ID 13 → 14 (Green) — became flagged in Jan
- **2025-00164** TIL001121 Auto Tune System Installation at Thisvi : RAG_ID 13 → 14 (Green) — became flagged in Jan
- **3 completions reverted** (active in Dec, completed in Jan): 2025-00040, 2025-00095, 2025-00063
- **4 active projects rolled back to pending** (newly activated in Jan): 2025-00170, 2025-00150, 2025-00045, 2025-00128

### February 2026 (REF_PERIOD=202602)
Generated from Jan 2026 baseline by projecting 1 month of portfolio progression.

- **Scaled YTD spend** × 1.55 (5 months vs 4)
- **2025-00095** Strategic spare parts  (pending GT turning gear, G: resolved — Red→Green + marked completed
- **2025-00144** ST Hydraulic Pumps Replacement: de-escalated Red→Amber (still flagged)
- **2025-00117** Desuperheaters replacement (HP intermediate and HR: completed in Feb (was Amber, 90% in Jan) — closeout to Green
- **2025-00128** Steam Turbine Generator complete rewinding (stator: NEW Amber flag (€3000k budget)
- **2025-00067** DERMS: NEW Amber flag (€265k budget)
