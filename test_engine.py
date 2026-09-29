"""
KisanSahay Test Suite v2.0
Tests the deterministic 3-way classifier against known ground truth.
Run: python test_engine.py
"""
import sys
import json
from pathlib import Path

# Add parent to path for rule_engine import
sys.path.insert(0, str(Path(__file__).parent))
from rule_engine import load_schemes, evaluate_scheme

def parse_currency(raw):
    if not raw: return None
    import re
    raw = raw.lower().replace(",","").strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac|l)?", raw)
    if not m: return None
    return float(m.group(1)) * (100000 if m.group(2) else 1)

def parse_land(raw):
    if not raw: return None
    import re
    raw = raw.lower().replace(",","").strip()
    m = re.search(r"(\d+(?:\.\d+)?)", raw)
    return float(m.group(1)) if m else None

TEST_CASES = [
    ("Clearly eligible farmer – PM-KISAN",
     { "occupation":"farmer","occupation_code":"farmer","annual_income":150000,"land_holding":1.2,"is_taxpayer":False },
     "PM-KISAN", "ELIGIBLE"),
    ("Missing land record – PM-KISAN UNKNOWN",
     { "occupation":"farmer","occupation_code":"farmer","annual_income":150000,"land_holding":None,"is_taxpayer":False },
     "PM-KISAN", "UNKNOWN"),
    ("Income-tax payer excluded – PM-KISAN INELIGIBLE",
     { "occupation":"farmer","occupation_code":"farmer","annual_income":150000,"land_holding":1.2,"is_taxpayer":True },
     "PM-KISAN", "INELIGIBLE"),
    ("High income MJPKY ineligible",
     { "occupation":"farmer","occupation_code":"farmer","annual_income":300000,"land_holding":1.2,"is_taxpayer":False },
     "MJPKY", "INELIGIBLE"),
    ("Low income MJPKY eligible",
     { "occupation":"farmer","occupation_code":"farmer","annual_income":120000,"land_holding":1.2,"is_taxpayer":False },
     "MJPKY", "ELIGIBLE"),
    ("Small land – farm pond ineligible (0.3 ha < 0.6 ha)",
     { "occupation":"farmer","occupation_code":"farmer","annual_income":100000,"land_holding":0.3,"is_taxpayer":False },
     "SHET-TALE", "INELIGIBLE"),
    ("Adequate land – farm pond eligible (1.0 ha >= 0.6 ha)",
     { "occupation":"farmer","occupation_code":"farmer","annual_income":100000,"land_holding":1.0,"is_taxpayer":False },
     "SHET-TALE", "ELIGIBLE"),
    ("SC/ST farmer – Ambedkar scheme UNKNOWN (missing caste cert)",
     { "occupation":"farmer","occupation_code":"farmer","annual_income":100000,"land_holding":1.0,"is_taxpayer":False },
     "AMBEDKAR-KRISHI", "UNKNOWN"),
    ("SC/ST farmer – Ambedkar scheme ELIGIBLE",
     { "occupation":"farmer","occupation_code":"farmer","annual_income":100000,"land_holding":1.0,"is_taxpayer":False,"caste_category":"sc_st" },
     "AMBEDKAR-KRISHI", "ELIGIBLE"),
    ("SMAM income-eligible farmer",
     { "occupation":"farmer","occupation_code":"farmer","annual_income":300000,"land_holding":1.0,"is_taxpayer":False },
     "SMAM", "ELIGIBLE"),
    ("SMAM income too high (> Rs 6 lakh)",
     { "occupation":"farmer","occupation_code":"farmer","annual_income":700000,"land_holding":1.0,"is_taxpayer":False },
     "SMAM", "INELIGIBLE"),
]

def run_tests():
    data = load_schemes()
    schemes_map = {s["scheme_id"]: s for s in data["schemes"]}
    passed = 0
    failed = 0
    print("\n" + "="*70)
    print("KisanSahay Rule Engine – Test Suite v2.0")
    print("="*70)
    for name, profile, sid, expected in TEST_CASES:
        scheme = schemes_map.get(sid)
        if not scheme:
            print(f"  SKIP  {name} – scheme {sid} not found")
            continue
        result = evaluate_scheme(scheme, profile)
        actual = result["status"]
        ok = actual == expected
        icon = "PASS" if ok else "FAIL"
        near = result.get("near_miss", [])
        near_str = ""
        if near:
            nm = near[0]
            near_str = f" | gap: Rs {nm['gap']:,.0f}"
        print(f"  [{icon}] {name}")
        print(f"         Expected: {expected} | Got: {actual}{near_str}")
        if not ok:
            for c in result["checks"]:
                if c["result"] != "PASS":
                    print(f"         >> {c['result']}: {c['rule']} (applicant={c['applicant_value']}, limit={c['limit']})")
        if ok: passed += 1
        else: failed += 1
    print("="*70)
    print(f"Results: {passed}/{passed+failed} passed | {failed} failed")
    print("="*70)
    return failed == 0

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
