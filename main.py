"""
KisanSahay FastAPI Backend v2.0
5-Layer Architecture: Input → Extraction → Matching → Explanation → Dashboard
DPDP-compliant, deterministic rule engine + LLM explanation layer
"""
import os, re, json
from typing import Optional, Any
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path

# ── Import rule engine ──────────────────────────────────────────────────
from rule_engine import (
    load_schemes, evaluate_all, rank_schemes, summary_stats,
    mask_aadhaar, fuzzy_name_match
)

app = FastAPI(
    title="KisanSahay – Financial Policy Discovery & Eligibility Assistant",
    version="2.0.0",
    description="Decoupled 5-layer PWA for agricultural scheme eligibility. DPDP-compliant.",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── Input normalisation helpers ───────────────────────────────────────────

def parse_currency(raw: str | None) -> float | None:
    if not raw:
        return None
    raw = raw.lower().replace(",", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac|l)?", raw)
    if not m:
        return None
    num = float(m.group(1))
    if m.group(2):
        num *= 100000
    return num

def parse_land(raw: str | None) -> float | None:
    if not raw:
        return None
    raw = raw.lower().replace(",", "").strip()
    # Handle acres to hectares
    m_acre = re.search(r"(\d+(?:\.\d+)?)\s*acre", raw)
    if m_acre:
        return round(float(m_acre.group(1)) * 0.404686, 4)
    m = re.search(r"(\d+(?:\.\d+)?)", raw)
    return float(m.group(1)) if m else None

def parse_yes_no(raw: str | None) -> bool | None:
    if raw is None:
        return None
    v = raw.lower().strip()
    if v in ("yes", "y", "true", "1", "हाँ", "हां", "होय"):
        return True
    if v in ("no", "n", "false", "0", "नहीं", "नाही"):
        return False
    return None

def parse_caste(raw: str | None) -> str | None:
    if not raw:
        return None
    v = raw.lower().strip()
    if any(x in v for x in ["sc", "schedule caste", "दलित", "अनुसूचित जाति"]):
        return "sc_st"
    if any(x in v for x in ["st", "schedule tribe", "आदिवासी", "tribal"]):
        return "sc_st"
    if any(x in v for x in ["obc", "other backward"]):
        return "obc"
    if any(x in v for x in ["general", "open", "खुला"]):
        return "general"
    return raw.lower()

# ─── Pydantic models ──────────────────────────────────────────────────────

class Applicant(BaseModel):
    full_name: Optional[str] = None
    occupation: Optional[str] = None
    annual_income: Optional[str] = None
    land_holding: Optional[str] = None
    is_taxpayer: Optional[str] = None
    aadhaar: Optional[str] = None
    age: Optional[int] = None
    caste_category: Optional[str] = None
    district: Optional[str] = None
    consent: bool = False

def normalize_profile(a: Applicant) -> dict:
    return {
        "full_name": a.full_name,
        "occupation": (a.occupation or "").lower().strip(),
        "occupation_code": "farmer" if "farm" in (a.occupation or "").lower() else (a.occupation or "").lower(),
        "annual_income": parse_currency(a.annual_income),
        "land_holding": parse_land(a.land_holding),
        "is_taxpayer": parse_yes_no(a.is_taxpayer),
        "age": a.age,
        "caste_category": parse_caste(a.caste_category),
        "district": a.district,
    }

# ─── LLM Explanation Layer ────────────────────────────────────────────────

def generate_plain_language_explanation(result: dict, profile: dict, lang: str = "en") -> str:
    """
    Deterministic template-based explanation generator (LLM orchestration hook).
    In production, replace template strings with LLM API calls using the prompts below.
    """
    name = profile.get("full_name") or "Applicant"
    scheme = result["scheme_name"]
    status = result["status"]

    if status == "ELIGIBLE":
        benefit = result.get("benefit_estimate", {})
        desc = benefit.get("description", "") if benefit else ""
        explanation = {
            "en": f"Good news! {name} qualifies for {scheme}. {desc}. All eligibility conditions have been verified and met. Please apply via the official portal linked below.",
            "hi": f"खुशखबरी! {name} {scheme} के लिए पात्र हैं। {desc}। सभी पात्रता शर्तें पूरी होती हैं। कृपया नीचे दिए गए आधिकारिक पोर्टल से आवेदन करें।",
            "mr": f"आनंदाची बातमी! {name} {scheme} साठी पात्र आहेत। {desc}। सर्व पात्रता अटी पूर्ण झाल्या आहेत। कृपया खाली दिलेल्या अधिकृत पोर्टलद्वारे अर्ज करा।",
        }
        return explanation.get(lang, explanation["en"])

    elif status == "INELIGIBLE":
        near_miss = result.get("near_miss", [])
        fails = result.get("failed_rules", [])
        fail_reasons = []
        for f in fails[:3]:
            rule = f.get("rule", "")
            av = f.get("applicant_value")
            limit = f.get("limit")
            op = f.get("operator", "")
            gap = f.get("gap")
            if gap is not None:
                fail_reasons.append(f"{rule}: Your value (₹{av:,.0f}) exceeds the limit (₹{limit:,.0f}) by ₹{gap:,.0f}.")
            else:
                fail_reasons.append(f"{rule}: Condition not met (applicant: {av}, required {op} {limit}).")
        reason_str = " | ".join(fail_reasons) if fail_reasons else "One or more eligibility conditions not met."
        explanation = {
            "en": f"Unfortunately, {name} is not currently eligible for {scheme}. Reason: {reason_str}",
            "hi": f"दुर्भाग्यवश, {name} वर्तमान में {scheme} के लिए पात्र नहीं हैं। कारण: {reason_str}",
            "mr": f"दुर्दैवाने, {name} सध्या {scheme} साठी पात्र नाहीत. कारण: {reason_str}",
        }
        return explanation.get(lang, explanation["en"])

    else:  # UNKNOWN
        missing = result.get("missing_documents", [])
        doc_list = ", ".join(d.get("doc", "") for d in missing[:3])
        explanation = {
            "en": f"Eligibility for {name} in {scheme} cannot be confirmed yet. Missing documents: {doc_list}. Please gather these documents and re-apply. This is NOT a rejection.",
            "hi": f"{name} की {scheme} में पात्रता अभी निश्चित नहीं हो सकती। अनुपलब्ध दस्तावेज़: {doc_list}। कृपया ये दस्तावेज़ प्राप्त करें और पुनः आवेदन करें। यह अस्वीकृति नहीं है।",
            "mr": f"{name} साठी {scheme} मध्ये पात्रता अद्याप निश्चित करता येत नाही. अनुपलब्ध कागदपत्रे: {doc_list}. कृपया ही कागदपत्रे मिळवा आणि पुन्हा अर्ज करा. हे नकार नाही.",
        }
        return explanation.get(lang, explanation["en"])


# LLM Prompt Template (for production LLM integration)
LLM_PROMPT_TEMPLATE = """
You are KisanSahay, an expert assistant for Indian agricultural schemes.
Speak in simple language that a low-literacy farmer can understand.
Language: {lang}

Applicant Profile:
- Name: {name}
- Occupation: {occupation}
- Annual Income: ₹{income}
- Land Holding: {land} hectares
- Income-tax payer: {taxpayer}

Scheme: {scheme_name}
Eligibility Status: {status}
Rule Checks: {checks}
Near-miss Data: {near_miss}
Missing Documents: {missing_docs}

Task:
1. Write a 2-3 sentence plain language summary explaining the eligibility result.
2. If INELIGIBLE: State the EXACT near-miss margin (e.g., "Income is ₹20,000 over the ₹1,50,000 limit").
3. If UNKNOWN: Create a step-by-step roadmap to collect missing documents with portal links, costs, and timelines.
4. If ELIGIBLE: State the estimated benefit clearly (amount, installments, how to apply).
5. NEVER hallucinate. Only cite facts from the rule checks above.
6. Cite the official scheme section: {source_section}

Response format: Plain text, no markdown, under 150 words.
"""

# ─── OCR Extraction (text-based heuristic) ────────────────────────────────

def extract_fields_from_text(text: str) -> dict:
    """Heuristic field extractor from OCR text."""
    fields = {}
    patterns = {
        "full_name": [r"(?:name|नाम|नाव)[:\s]+([A-Za-z\u0900-\u097F ]{3,50})", r"^([A-Z][a-z]+ [A-Z][a-z]+)"],
        "annual_income": [r"(?:income|आय|उत्पन्न)[:\s]*(?:rs\.?|₹)?\s*([\d,]+(?:\s*lakh)?)", r"(?:rs\.?|₹)\s*([\d,]+)"],
        "land_holding": [r"(?:land|area|जमीन|जमिन|क्षेत्र)[:\s]*([\d.]+)\s*(?:hectare|ha|एकर|acre)?", r"([\d.]+)\s*hectare"],
        "is_taxpayer": [r"(?:income.?tax|taxpayer)[:\s]*(yes|no|हाँ|नहीं|होय|नाही)"],
    }
    for field, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
            if m:
                raw_val = m.group(1).strip()
                fields[field] = {"raw": raw_val, "confidence": 0.82}
                break
    return fields

# ─── API Endpoints ────────────────────────────────────────────────────────

@app.get("/api/schemes")
def get_schemes():
    data = load_schemes()
    return {"dataset_label": data["dataset_label"], "version": data.get("version"), "count": len(data["schemes"]), "schemes": data["schemes"]}

@app.get("/api/schemes/{sid}")
def get_scheme(sid: str):
    for s in load_schemes()["schemes"]:
        if s["scheme_id"] == sid:
            return s
    raise HTTPException(404, f"Scheme '{sid}' not found")

@app.post("/api/eligibility/check")
def check_eligibility(a: Applicant, lang: str = "en"):
    if not a.consent:
        raise HTTPException(400, "Consent is required under DPDP Act 2023 to process your information.")
    profile = normalize_profile(a)
    results = evaluate_all(profile)
    ranking = rank_schemes(profile)
    stats = summary_stats(results)

    # Attach plain-language explanations
    for r in results:
        r["explanation"] = generate_plain_language_explanation(r, profile, lang)
        r["llm_prompt"] = LLM_PROMPT_TEMPLATE.format(
            lang=lang,
            name=profile.get("full_name", "Applicant"),
            occupation=profile.get("occupation", "unknown"),
            income=profile.get("annual_income", "unknown"),
            land=profile.get("land_holding", "unknown"),
            taxpayer=profile.get("is_taxpayer", "unknown"),
            scheme_name=r["scheme_name"],
            status=r["status"],
            checks=json.dumps(r["checks"], ensure_ascii=False),
            near_miss=json.dumps(r.get("near_miss", []), ensure_ascii=False),
            missing_docs=json.dumps(r.get("missing_documents", []), ensure_ascii=False),
            source_section=r.get("source", {}).get("section", ""),
        )

    return {
        "profile": profile,
        "aadhaar_masked": mask_aadhaar(a.aadhaar),
        "ranking": ranking,
        "results": results,
        "summary": stats,
    }

@app.post("/api/documents/extract")
async def extract_document(file: UploadFile = File(...)):
    allowed = (".pdf", ".jpg", ".jpeg", ".png", ".txt")
    fname = (file.filename or "").lower()
    if not any(fname.endswith(ext) for ext in allowed):
        raise HTTPException(415, "Unsupported file type. Use PDF, JPG, PNG, or TXT.")
    data = await file.read()
    
    # Blur/quality detection heuristic
    blur_alert = None
    if fname.endswith((".jpg", ".jpeg", ".png")) and len(data) < 20000:
        blur_alert = "Image appears low-resolution. Please re-upload a clearer scan for better OCR accuracy."

    # Text extraction
    if fname.endswith(".txt"):
        text = data.decode("utf-8", errors="ignore")
    else:
        # In production: integrate Tesseract/Google Vision OCR here
        text = data.decode("utf-8", errors="ignore")

    fields = extract_fields_from_text(text)
    
    # DPDP masking: mask Aadhaar in any extracted text
    masked_text = re.sub(r"\b(\d{4})\s*(\d{4})\s*(\d{4})\b", r"XXXX XXXX \3", text)

    if not fields:
        return {
            "fields": {},
            "status": "NEEDS_MANUAL_ENTRY",
            "message": "Could not extract fields automatically. Please enter your details manually.",
            "blur_alert": blur_alert,
            "masked_text_preview": masked_text[:500],
        }

    return {
        "fields": fields,
        "status": "NEEDS_CONFIRMATION",
        "message": "Fields extracted. Please review and confirm the values below before submitting.",
        "blur_alert": blur_alert,
        "dpdp_note": "Aadhaar numbers have been auto-masked per DPDP Act 2023.",
    }

@app.post("/api/name-match")
def name_match(body: dict):
    return fuzzy_name_match(body.get("name1", ""), body.get("name2", ""))

@app.get("/api/test-suite")
def test_suite():
    test_cases = [
        ("Clearly eligible farmer", {"occupation": "farmer", "annual_income": "1.5 lakh", "land_holding": "1.2 hectares", "is_taxpayer": "no"}, "PM-KISAN", "ELIGIBLE"),
        ("Missing land record", {"occupation": "farmer", "annual_income": "1.5 lakh", "is_taxpayer": "no"}, "PM-KISAN", "UNKNOWN"),
        ("High income – ineligible for MJPKY", {"occupation": "farmer", "annual_income": "3 lakh", "land_holding": "1.2 ha", "is_taxpayer": "no"}, "MJPKY", "INELIGIBLE"),
        ("Small land – ineligible for farm pond", {"occupation": "farmer", "annual_income": "1 lakh", "land_holding": "0.3 ha", "is_taxpayer": "no"}, "SHET-TALE", "INELIGIBLE"),
        ("Eligible for farm pond", {"occupation": "farmer", "annual_income": "1 lakh", "land_holding": "1.0 ha", "is_taxpayer": "no"}, "SHET-TALE", "ELIGIBLE"),
        ("Income taxpayer excluded from PM-KISAN", {"occupation": "farmer", "annual_income": "1 lakh", "land_holding": "1.0 ha", "is_taxpayer": "yes"}, "PM-KISAN", "INELIGIBLE"),
        ("Non-farmer – low relevance", {"occupation": "business", "annual_income": "4 lakh", "land_holding": "0"}, "PM-KISAN", "INELIGIBLE"),
    ]
    out = []
    for name, profile_raw, sid, expected in test_cases:
        from rule_engine import evaluate_scheme
        data = load_schemes()
        scheme = next((s for s in data["schemes"] if s["scheme_id"] == sid), None)
        if not scheme:
            continue
        norm_profile = {
            "occupation": profile_raw.get("occupation", ""),
            "occupation_code": "farmer" if "farm" in profile_raw.get("occupation", "") else profile_raw.get("occupation", ""),
            "annual_income": parse_currency(profile_raw.get("annual_income")),
            "land_holding": parse_land(profile_raw.get("land_holding")),
            "is_taxpayer": parse_yes_no(profile_raw.get("is_taxpayer")),
        }
        result = evaluate_scheme(scheme, norm_profile)
        actual = result["status"]
        out.append({
            "case": name,
            "scheme": sid,
            "expected": expected,
            "actual": actual,
            "passed": expected == actual,
            "near_miss": result.get("near_miss", []),
        })
    return out

# ─── Static frontend serving ──────────────────────────────────────────────
_FE = Path(__file__).parent
@app.get("/")
def home():
    return FileResponse(_FE / "index.html")
