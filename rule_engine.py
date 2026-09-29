"""
KisanSahay Deterministic Eligibility Engine v2.0
No LLM involvement – same input ALWAYS gives same output.
Implements 3-Way Classifier: ELIGIBLE | INELIGIBLE | UNKNOWN
"""
import json
import operator
import re
from pathlib import Path
from difflib import SequenceMatcher

# ─── Operator map ──────────────────────────────────────────────────────────
OPS = {
    ">":  operator.gt,
    ">=": operator.ge,
    "<":  operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}

# ─── Fuzzy name matching ───────────────────────────────────────────────────
def fuzzy_name_match(a: str, b: str, threshold: float = 0.82) -> dict:
    """Returns match result with score for DPDP-compliant name reconciliation."""
    if not a or not b:
        return {"matched": False, "score": 0.0, "note": "One or both names missing"}
    a_clean = re.sub(r"[^\w\s]", "", a.lower().strip())
    b_clean = re.sub(r"[^\w\s]", "", b.lower().strip())
    score = SequenceMatcher(None, a_clean, b_clean).ratio()
    matched = score >= threshold
    return {
        "matched": matched,
        "score": round(score, 3),
        "note": "Names reconciled (fuzzy match)" if matched else f"Name mismatch (score {score:.2f} < {threshold})",
    }

# ─── Aadhaar masking (DPDP compliance) ───────────────────────────────────
def mask_aadhaar(raw: str) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 4:
        return "XXXX XXXX " + digits.ljust(4, "X")
    return "XXXX XXXX " + digits[-4:]

# ─── Data loading ──────────────────────────────────────────────────────────
_SCHEMES_CACHE: dict | None = None

def load_schemes(path: str | None = None) -> dict:
    global _SCHEMES_CACHE
    if _SCHEMES_CACHE and not path:
        return _SCHEMES_CACHE
    p = Path(path) if path else Path(__file__).parent / "schemes.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    if not path:
        _SCHEMES_CACHE = data
    return data

# ─── Gap calculation ──────────────────────────────────────────────────────
def _compute_gap(req: dict, val) -> float | None:
    """Returns how far the applicant is from satisfying the rule (near-miss margin)."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return None
    d = val - req["value"]
    if req["operator"] in ("<", "<=") and d > 0:
        return round(d, 2)      # Over the limit by this much
    if req["operator"] in (">", ">=") and d < 0:
        return round(-d, 2)     # Short by this much
    return None

# ─── Single requirement evaluation ───────────────────────────────────────
def evaluate_requirement(req: dict, profile: dict) -> dict:
    val = profile.get(req["field"])
    base = {
        "id": req["id"],
        "rule": req["label"],
        "field": req["field"],
        "operator": req["operator"],
        "limit": req["value"],
        "applicant_value": val,
        "doc_label": req.get("doc_label"),
        "doc_cost": req.get("doc_cost"),
        "doc_days": req.get("doc_days"),
        "portal": req.get("portal"),
    }

    # Missing value → UNKNOWN (not INELIGIBLE!)
    if val is None:
        return {
            **base,
            "result": "UNKNOWN",
            "missing_document": req.get("doc_label"),
            "why_required": req.get("why_required", ""),
            "reason": f"Cannot verify '{req['label']}' – required document not provided.",
            "gap": None,
        }

    # Unknown operator → UNKNOWN
    if req["operator"] not in OPS:
        return {**base, "result": "UNKNOWN", "reason": "Unknown operator in rule; manual review required.", "gap": None}

    # Evaluate rule
    ok = OPS[req["operator"]](val, req["value"])
    gap = None if ok else _compute_gap(req, val)

    return {
        **base,
        "result": "PASS" if ok else "FAIL",
        "gap": gap,
        "reason": None,
    }

# ─── Benefit estimate ─────────────────────────────────────────────────────
def compute_benefit(benefit_cfg: dict, status: str, land_holding: float | None = None) -> dict | None:
    if status != "ELIGIBLE":
        return None
    b = benefit_cfg
    t = b.get("type")
    if t == "fixed":
        return {
            "label": "Estimated annual benefit",
            "type": t,
            "amount": b.get("amount"),
            "frequency": b.get("period", "annual"),
            "estimated_annual": b.get("amount"),
            "description": b.get("description"),
        }
    if t == "fixed_per_hectare" and land_holding:
        annual = b.get("amount", 0) * land_holding
        return {
            "label": "Estimated annual benefit (per hectare)",
            "type": t,
            "amount": b.get("amount"),
            "frequency": b.get("period"),
            "estimated_annual": round(annual, 2),
            "description": b.get("description"),
        }
    if t in ("subsidy", "loan_waiver", "composite"):
        return {
            "label": "Maximum subsidy / assistance",
            "type": t,
            "amount": b.get("amount"),
            "frequency": b.get("period"),
            "estimated_annual": None,
            "description": b.get("description"),
        }
    return {
        "label": "Benefit available",
        "type": t,
        "amount": b.get("amount"),
        "frequency": b.get("period"),
        "estimated_annual": None,
        "description": b.get("description"),
    }

# ─── Scheme evaluation ───────────────────────────────────────────────────
def evaluate_scheme(scheme: dict, profile: dict) -> dict:
    checks = [evaluate_requirement(r, profile) for r in scheme.get("requirements", [])]
    fails = [c for c in checks if c["result"] == "FAIL"]
    unknowns = [c for c in checks if c["result"] == "UNKNOWN"]

    # Core 3-way classification logic
    # INELIGIBLE only when at least one rule explicitly FAILS
    # UNKNOWN when no fails but some checks can't be verified
    # ELIGIBLE only when all checks PASS
    if fails:
        status = "INELIGIBLE"
    elif unknowns:
        status = "UNKNOWN"
    else:
        status = "ELIGIBLE"

    missing_docs = []
    seen = set()
    for c in unknowns:
        doc = c.get("missing_document")
        if doc and doc not in seen:
            missing_docs.append({
                "doc": doc,
                "why": c.get("why_required", ""),
                "portal": c.get("portal"),
                "cost": c.get("doc_cost"),
                "days": c.get("doc_days"),
            })
            seen.add(doc)

    land_holding = profile.get("land_holding")
    benefit_est = compute_benefit(scheme.get("benefit", {}), status, land_holding)

    # Near-miss summary for INELIGIBLE
    near_miss_summary = []
    for f in fails:
        if f.get("gap") is not None:
            near_miss_summary.append({
                "rule": f["rule"],
                "gap": f["gap"],
                "applicant_value": f["applicant_value"],
                "limit": f["limit"],
                "operator": f["operator"],
            })

    return {
        "scheme": scheme["scheme_id"],
        "scheme_name": scheme["scheme_name"],
        "category": scheme.get("category"),
        "government": scheme.get("government"),
        "status": status,
        "checks": checks,
        "failed_rules": fails,
        "near_miss": near_miss_summary,
        "missing_documents": missing_docs,
        "benefit_estimate": benefit_est,
        "portal_links": scheme.get("portal_links", []),
        "application_cost": scheme.get("application_cost", 0),
        "processing_days": scheme.get("processing_days"),
        "source": {
            "document": scheme.get("source_document"),
            "section": scheme.get("source_section"),
            "url": scheme.get("official_url"),
        },
        "tags": scheme.get("tags", []),
    }

# ─── Evaluate all schemes ─────────────────────────────────────────────────
def evaluate_all(profile: dict, data: dict | None = None) -> list[dict]:
    data = data or load_schemes()
    return [evaluate_scheme(s, profile) for s in data["schemes"]]

# ─── Rank schemes by relevance ────────────────────────────────────────────
def rank_schemes(profile: dict, data: dict | None = None) -> list[dict]:
    data = data or load_schemes()
    occupation = (profile.get("occupation") or "").lower()
    out = []
    for s in data["schemes"]:
        occ_list = s.get("relevance", {}).get("occupations", [])
        if not occupation:
            rel = "Unknown"
        elif occupation in occ_list:
            rel = "High"
        else:
            rel = "Low"
        out.append({"scheme_id": s["scheme_id"], "relevance": rel, "tags": s.get("tags", [])})
    return out

# ─── Summary stats ────────────────────────────────────────────────────────
def summary_stats(results: list[dict]) -> dict:
    eligible = [r for r in results if r["status"] == "ELIGIBLE"]
    unknown = [r for r in results if r["status"] == "UNKNOWN"]
    ineligible = [r for r in results if r["status"] == "INELIGIBLE"]
    total_fixed_benefit = sum(
        r["benefit_estimate"]["estimated_annual"]
        for r in eligible
        if r.get("benefit_estimate") and r["benefit_estimate"].get("estimated_annual")
    )
    return {
        "total_schemes": len(results),
        "eligible_count": len(eligible),
        "unknown_count": len(unknown),
        "ineligible_count": len(ineligible),
        "estimated_annual_benefit": total_fixed_benefit,
        "eligible_schemes": [{"id": r["scheme"], "name": r["scheme_name"], "benefit": r.get("benefit_estimate")} for r in eligible],
    }
