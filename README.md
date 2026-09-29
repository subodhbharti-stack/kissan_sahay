# KisanSahay – Financial Policy Discovery & Eligibility Assistant v2.0

> **Applicant-centric Progressive Web App (PWA)** for low-income citizens and farmers to discover government scheme eligibility instantly.

## Features

### 5-Layer Architecture
| Layer | Implementation |
|-------|---------------|
| **Input** | Multi-lingual UI (EN/HI/MR), Web Speech API voice input, document upload, adaptive 6-step quiz |
| **Extraction** | Client-side OCR text parsing, DPDP-compliant Aadhaar masking, fuzzy name matching, blur alerts |
| **Matching Engine** | Deterministic JSON rule engine (ELIGIBLE / INELIGIBLE / UNKNOWN 3-way classifier) |
| **Explanation** | Template-based plain-language summaries with near-miss margins and document roadmaps |
| **Dashboard** | Glassmorphism Tailwind CSS UI, summary cards, PDF export, CSC-printable 1-page sheet |

### 21 Schemes Covered
1. PM-KISAN – Rs 6,000/year direct income support
2. Namo Shetkari Maha Sanman Nidhi – Rs 6,000/year (Maharashtra)
3. PMFBY – Crop insurance at Rs 1 token premium
4. Kisan Credit Card (KCC) – Crop loan up to Rs 3 lakh @ 4% p.a.
5. Magel Tyala Shet Tale – Farm pond subsidy up to Rs 50,000
6. Bhausaheb Fundkar Orchard Planting – 100% subsidy for fruit orchards
7. PM-KUSUM – Up to 90% subsidy for solar agricultural pumps
8. Gopinath Munde Shetkari Apghat Vima – Rs 2 lakh accident insurance
9. Mahatma Jotirao Phule Karjmukti Yojana – Loan waiver up to Rs 2 lakh
10. eNAM – National electronic agriculture market
11. PoCRA (Nanaji Deshmukh) – 50-75% micro-irrigation subsidy
12. Dr. Babasaheb Ambedkar Krishi Swavalamban – SC/ST farmer support
13. PKVY – Rs 50,000/hectare for organic farming (3 years)
14. Agriculture Infrastructure Fund (AIF) – Post-harvest infrastructure
15. PMKSY – 80% subsidy for marginal farmers on micro-irrigation
16. SMAM – Subsidies up to Rs 1 lakh for tractors
17. Soil Health Card (RKVY) – Free soil testing and advisory
18. Mukhyamantri Krishi ani Anna Prakriya Yojana – Food processing grants
19. Namo Drone Didi – Drone-based precision agriculture
20. Maha Krishi Samrudhi Yojana – Agro-processing finance
21. Maha Agri-Machinery Rental Scheme – Equipment rental via CHC

## Running the App

### Frontend Only (Open in Browser)
```
Open index.html directly in Chrome/Edge/Firefox
```
Loads schemes.json from the same directory automatically.

### Full Stack (FastAPI Backend)
```bash
pip install fastapi uvicorn python-multipart
uvicorn main:app --reload --port 8000
```
Then open http://localhost:8000

## File Structure
```
files/
  index.html      ← Complete PWA frontend (single file, ~87KB)
  schemes.json    ← 21-scheme deterministic rule database
  rule_engine.py  ← Python deterministic 3-way classifier
  main.py         ← FastAPI backend with 5-layer architecture
  manifest.json   ← PWA manifest for installability
  sw.js           ← Service worker for offline support
  README.md       ← This file
```

## Key Design Decisions

- **Zero hallucinations**: Eligibility is 100% deterministic. LLM is only used for plain-language *explanations* of rule results, never for decisions.
- **UNKNOWN ≠ INELIGIBLE**: Missing documents trigger UNKNOWN status; applicants are always directed to gather docs rather than being rejected.
- **DPDP Compliance**: Aadhaar auto-masked to last-4 digits on input. No data is stored or transmitted.
- **Offline-first PWA**: Service worker caches assets; works without internet after first load.
- **Near-miss margins**: For INELIGIBLE results, exact numerical gaps are shown (e.g., "Income is Rs 20,000 over the Rs 1,50,000 limit").
