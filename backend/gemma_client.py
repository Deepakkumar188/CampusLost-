"""Gemma 4 client wrapper using the official google-genai SDK.

Rules enforced here:
1. API key (`GEMINI_API_KEY`) and model name (`GEMMA_MODEL`) are read ONLY from
   environment variables loaded from `.env`. No model IDs or keys are hardcoded.
2. Every Gemma call retries twice (3 attempts total), strips markdown code fences,
   validates JSON output with Pydantic, and falls back to a safe deterministic
   default so a bad response or missing API key never crashes the app.
3. Gemma extracts features, writes one-sentence match explanations, and performs
   fuzzy claim verification only as a fallback after exact normalised matching.
   Gemma NEVER produces the final match score.
"""

import base64
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar
from dotenv import load_dotenv
from pydantic import BaseModel

from backend.privacy import is_sensitive_item, redact_pii
from backend.schemas import (
    ExplanationOutput,
    ExtractedFeatures,
    VerificationOutput,
)

load_dotenv()

T = TypeVar("T", bound=BaseModel)

CODE_FENCE_RE = re.compile(r"^```(?:json|JSON)?\s*|\s*```$", re.MULTILINE)


def strip_code_fences(raw_text: str) -> str:
    """Remove markdown ```json ... ``` fences and extract the JSON object if wrapped in prose."""
    if not raw_text:
        return ""
    cleaned = CODE_FENCE_RE.sub("", raw_text.strip()).strip()
    # If the model included leading/trailing text around a JSON object, slice the outermost { ... }
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return cleaned[first_brace : last_brace + 1]
    return cleaned


def _get_env_credentials() -> Tuple[str, str]:
    """Read GEMINI_API_KEY and GEMMA_MODEL strictly from environment (.env)."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_id = os.getenv("GEMMA_MODEL", "").strip()
    return api_key, model_id


def _invoke_gemma_raw(
    prompt: str,
    image_bytes: Optional[bytes] = None,
    mime_type: str = "image/jpeg",
) -> str:
    """Call Gemma 4 through the google-genai SDK.

    Supports both `client.interactions.create` (google-genai >= 2.x) and
    `client.models.generate_content` so whichever SDK version is installed works.

    # TODO: Verify multimodal image input support for your selected GEMMA_MODEL
    # endpoint in the Gemini API. If the chosen Gemma 4 endpoint rejects image
    # inputs, we automatically retry with the text prompt only.
    """
    api_key, model_id = _get_env_credentials()
    if not api_key or api_key == "your_gemini_api_key_here" or not model_id:
        raise RuntimeError(
            "GEMINI_API_KEY or GEMMA_MODEL is not configured in .env; using safe fallback."
        )

    from google import genai  # Imported lazily so tests without network still run fast

    client = genai.Client(api_key=api_key)

    def _call(with_image: bool) -> str:
        # Prefer the modern Interactions API if present on the installed google-genai SDK
        if hasattr(client, "interactions"):
            try:
                if with_image and image_bytes:
                    b64_img = base64.b64encode(image_bytes).decode("utf-8")
                    interaction = client.interactions.create(
                        model=model_id,
                        input=[
                            {"type": "text", "text": prompt},
                            {"type": "image", "data": b64_img, "mime_type": mime_type},
                        ],
                    )
                else:
                    interaction = client.interactions.create(
                        model=model_id,
                        input=prompt,
                    )
                if getattr(interaction, "output_text", None):
                    return str(interaction.output_text)
            except Exception:
                # Fall through to client.models.generate_content if interactions isn't enabled for this model
                pass

        # Standard models.generate_content call
        if with_image and image_bytes:
            from google.genai import types

            contents: Any = [
                prompt,
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ]
        else:
            contents = prompt

        response = client.models.generate_content(
            model=model_id,
            contents=contents,
        )
        return str(getattr(response, "text", "") or "")

    if image_bytes:
        try:
            return _call(with_image=True)
        except Exception:
            # Automatic fallback to text-only if the selected Gemma model rejects image parts
            return _call(with_image=False)
    return _call(with_image=False)


def call_gemma_validated(
    prompt: str,
    schema_cls: Type[T],
    fallback_fn: Callable[[], T],
    image_bytes: Optional[bytes] = None,
    max_retries: int = 2,
) -> T:
    """Execute a Gemma 4 call with `max_retries` (2 retries = 3 attempts total).

    On every attempt:
    1. Call Gemma 4 via google-genai
    2. Strip markdown code fences
    3. Parse JSON and validate with `schema_cls` (Pydantic)
    If all attempts fail, return `fallback_fn()` so the app never crashes.
    """
    total_attempts = max_retries + 1
    for _attempt in range(total_attempts):
        try:
            raw = _invoke_gemma_raw(prompt=prompt, image_bytes=image_bytes)
            cleaned = strip_code_fences(raw)
            parsed = json.loads(cleaned)
            return schema_cls.model_validate(parsed)
        except Exception:
            continue
    return fallback_fn()


# ---------------------------------------------------------------------------
# Safe deterministic fallbacks (bilingual English / Hindi / Hinglish aware)
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "bottle": ["bottle", "thermos", "flask", "milton", "cello", "botal", "paani", "sipper", "thermosteel"],
    "bag": ["bag", "backpack", "rucksack", "laptop bag", "wildcraft", "skybags", "american tourister", "jhola", "tote"],
    "calculator": ["calculator", "casio", "fx-991", "fx991", "scientific calc", "calc"],
    "id_card": ["id card", "identity card", "student id", "icard", "i-card", "id-card", "institute id"],
    "wallet": ["wallet", "purse", "batua", "cardholder", "pouch"],
    "electronics": ["earbuds", "airpods", "headphones", "charger", "adapter", "mouse", "laptop", "phone", "pendrive", "powerbank", "tws"],
    "keys": ["key", "keys", "chabi", "chaabi", "keychain", "keyring", "lock"],
    "book": ["book", "notebook", "register", "copy", "textbook", "diary", "kitaab"],
    "eyewear": ["glasses", "spectacles", "chashma", "sunglasses", "specs", "lenskart"],
    "umbrella": ["umbrella", "chhata", "chatri"],
    "clothing": ["hoodie", "jacket", "sweater", "cap", "scarf", "shirt"],
}

COLOUR_KEYWORDS: Dict[str, List[str]] = {
    "black": ["black", "kala", "kaala", "matte black", "charcoal"],
    "blue": ["blue", "neela", "navy", "navy blue", "sky blue", "teal"],
    "silver": ["silver", "steel", "metallic", "chrome", "chandi"],
    "red": ["red", "laal", "maroon", "crimson"],
    "white": ["white", "safed", "cream"],
    "green": ["green", "hara", "olive"],
    "grey": ["grey", "gray", "slate"],
    "brown": ["brown", "bhura", "tan", "leather"],
    "yellow": ["yellow", "peela", "gold", "golden"],
    "pink": ["pink", "gulabi"],
    "orange": ["orange", "narangi"],
    "purple": ["purple", "violet"],
}

KNOWN_BRANDS = [
    "Milton",
    "Cello",
    "Casio",
    "Wildcraft",
    "Skybags",
    "American Tourister",
    "HP",
    "Dell",
    "Lenovo",
    "Apple",
    "Samsung",
    "OnePlus",
    "boAt",
    "Sony",
    "Logitech",
    "Lenskart",
    "Titan",
    "Fastrack",
    "Classmate",
    "Nataraj",
]


def fallback_extract_features(text: str, report_type: str = "lost") -> ExtractedFeatures:
    """Deterministic bilingual feature extractor used if Gemma API is unavailable."""
    clean_text = redact_pii(text or "")
    lower = clean_text.lower()

    # 1. Category
    detected_cat = "other"
    for cat, words in CATEGORY_KEYWORDS.items():
        if any(w in lower for w in words):
            detected_cat = cat
            break

    # 2. Colours
    colours: List[str] = []
    for canonical, words in COLOUR_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(w)}\b", lower) for w in words):
            colours.append(canonical)

    # 3. Brand
    detected_brand = ""
    for b in KNOWN_BRANDS:
        if re.search(rf"\b{re.escape(b.lower())}\b", lower):
            detected_brand = b
            break

    # 4. Distinguishing marks
    marks: List[str] = []
    mark_patterns = [
        r"(?:dent|scratch|sticker|keychain|charm|tag|strap|zip|zipper|ribbon|cover|case|name|engraved|broken|crack)[^.,;\n]{0,35}",
        r"fx[\-\s]?\d+[a-z]*",
        r"\b\d+\s*(?:ml|l|gb|tb|w)\b",
    ]
    for pat in mark_patterns:
        for m in re.findall(pat, lower):
            val = m.strip()
            if val and val not in marks:
                marks.append(val)

    # 5. Sensitive check
    sensitive = is_sensitive_item(detected_cat, False, clean_text)

    # 6. Summary
    colour_str = " ".join(colours).title()
    brand_str = f" {detected_brand}" if detected_brand else ""
    cat_label = detected_cat.replace("_", " ").title()
    summary = f"{colour_str}{brand_str} {cat_label}".strip()
    if not summary or summary == "Other":
        summary = clean_text[:72].strip() or "Campus item"

    # 7. Verification question & answer for found reports
    verify_q = None
    verify_a = None
    if report_type == "found":
        if marks:
            verify_q = "What distinguishing mark, sticker, keychain, or model detail is on this item?"
            verify_a = ", ".join(marks)
        elif detected_brand:
            verify_q = f"What is the brand or specific detail inside/on this {cat_label.lower()}?"
            verify_a = detected_brand
        else:
            verify_q = f"Describe one specific identifying detail (brand, sticker, or inside content) of this {cat_label.lower()}."
            verify_a = summary

    return ExtractedFeatures(
        category=detected_cat,
        colours=colours,
        brand=detected_brand,
        marks=marks,
        summary=summary,
        sensitive=sensitive,
        verify_question=verify_q,
        verify_answer=verify_a,
    )


def extract_features_with_gemma(
    text: str,
    report_type: str = "lost",
    image_bytes: Optional[bytes] = None,
) -> ExtractedFeatures:
    """Use Gemma 4 to extract structured features from English/Hindi/Hinglish text + optional photo."""
    redacted_text = redact_pii(text or "")
    prompt = f"""You are an AI assistant for IIT Bhilai's CampusLost+ system.
Extract structured item features from this {report_type.upper()} report (which may be in English, Hindi, or Hinglish).
Return ONLY a valid JSON object matching this exact schema (no markdown fences, no commentary):
{{
  "category": "one of: bottle, bag, calculator, electronics, id_card, wallet, keys, book, eyewear, umbrella, clothing, other",
  "colours": ["lowercase english colour names, e.g. black, blue, silver"],
  "brand": "brand name if present or empty string",
  "marks": ["distinguishing marks, stickers, dents, model numbers, keychain details"],
  "summary": "concise one-line English summary of the item",
  "sensitive": true or false (true for id_card, wallet, bank/identity cards),
  "verify_question": "if FOUND report: a question asking the claimant about a non-obvious/hidden detail to verify ownership; null if LOST report",
  "verify_answer": "if FOUND report: short expected answer to verify_question; null if LOST report"
}}

Report type: {report_type}
Report text: {redacted_text}
"""
    extracted = call_gemma_validated(
        prompt=prompt,
        schema_cls=ExtractedFeatures,
        fallback_fn=lambda: fallback_extract_features(redacted_text, report_type=report_type),
        image_bytes=image_bytes,
        max_retries=2,
    )

    # Always enforce privacy & sensitive item guardrails on extracted output
    extracted.summary = redact_pii(extracted.summary)
    extracted.sensitive = is_sensitive_item(
        extracted.category, extracted.sensitive, redacted_text
    )
    if report_type == "found" and not extracted.verify_question:
        fb = fallback_extract_features(redacted_text, report_type="found")
        extracted.verify_question = fb.verify_question
        extracted.verify_answer = fb.verify_answer
    return extracted


def fallback_explain_match(
    lost_report: Dict[str, Any],
    found_report: Dict[str, Any],
    score_data: Dict[str, Any],
) -> ExplanationOutput:
    """Deterministic one-sentence explanation when Gemma API is offline."""
    cat = (found_report.get("category") or "item").replace("_", " ")
    shared_colours = set(lost_report.get("colours", [])) & set(found_report.get("colours", []))
    colour_phrase = f"matching {'/'.join(sorted(shared_colours))} " if shared_colours else ""
    brand = found_report.get("brand") or lost_report.get("brand") or ""
    brand_phrase = f"{brand} " if brand else ""
    zone_chip = score_data.get("chips", {}).get("Zone", "nearby campus zone")
    time_chip = score_data.get("chips", {}).get("Time", "compatible timeframe")
    sentence = (
        f"Both reports describe a {colour_phrase}{brand_phrase}{cat} in {zone_chip.lower()} "
        f"within a {time_chip.lower()}."
    )
    return ExplanationOutput(explanation=sentence)


def explain_match_with_gemma(
    lost_report: Dict[str, Any],
    found_report: Dict[str, Any],
    score_data: Dict[str, Any],
) -> str:
    """Ask Gemma 4 for a single-sentence explanation of why two reports matched."""
    prompt = f"""You are explaining a Lost & Found match at IIT Bhilai.
Write ONE concise sentence (max 28 words) explaining why these two reports match based on their shared attributes, campus zone, and timing.
Never mention probabilities or reveal secret verification answers.
Return ONLY valid JSON: {{"explanation": "One sentence reason."}}

Lost item summary: {lost_report.get('summary')} (Zone: {lost_report.get('zone')}, Colours: {lost_report.get('colours')}, Brand: {lost_report.get('brand')}, Marks: {lost_report.get('marks')})
Found item summary: {found_report.get('summary')} (Zone: {found_report.get('zone')}, Colours: {found_report.get('colours')}, Brand: {found_report.get('brand')}, Marks: {found_report.get('marks')})
Match score: {score_data.get('match_score')}/100 | Chips: {score_data.get('chips')}
"""
    result = call_gemma_validated(
        prompt=prompt,
        schema_cls=ExplanationOutput,
        fallback_fn=lambda: fallback_explain_match(lost_report, found_report, score_data),
        max_retries=2,
    )
    return redact_pii(result.explanation)


# ---------------------------------------------------------------------------
# Ownership Verification: Exact normalised match FIRST, Gemma fuzzy fallback
# ---------------------------------------------------------------------------

STOP_WORDS = {
    "a", "an", "the", "is", "it", "has", "with", "on", "in", "near", "at",
    "my", "there", "and", "or", "of", "to", "hai", "ke", "ka", "ki", "me", "pe",
}


def _normalise_answer_tokens(text: str) -> Tuple[str, List[str]]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    collapsed = " ".join(cleaned.split())
    tokens = [t for t in collapsed.split() if t not in STOP_WORDS and len(t) > 1]
    return collapsed, tokens


def exact_normalised_verify(expected: str, candidate: str) -> bool:
    """Fast deterministic check before calling Gemma.

    Returns True if normalised strings match or if the claimant's answer contains
    all key non-stopword tokens of the expected answer (or >=60% token overlap for
    multi-word descriptions).
    """
    exp_str, exp_tokens = _normalise_answer_tokens(expected)
    cand_str, cand_tokens = _normalise_answer_tokens(candidate)
    if not exp_str or not cand_str:
        return False
    if exp_str == cand_str or exp_str in cand_str or (len(cand_str) >= 4 and cand_str in exp_str):
        return True
    if not exp_tokens or not cand_tokens:
        return False
    overlap = set(exp_tokens) & set(cand_tokens)
    # If expected has 1-2 tokens, require at least 1 exact key token match
    if len(exp_tokens) <= 2:
        return len(overlap) >= 1
    return (len(overlap) / float(len(set(exp_tokens)))) >= 0.6


def verify_ownership_answer(
    question: str, expected_answer: str, user_answer: str
) -> Tuple[bool, str, str]:
    """Verify claimant's answer:
    1. Exact normalised match first.
    2. Gemma 4 fuzzy semantic check only as fallback.

    Returns (verified_bool, method_used, reason).
    """
    if exact_normalised_verify(expected_answer, user_answer):
        return True, "exact_normalised", "Answer matched the recorded identifying detail."

    # Fallback: Gemma 4 semantic fuzzy check
    def _fallback_fuzzy() -> VerificationOutput:
        # Synonym-aware fallback if Gemma API is offline
        synonym_groups = [
            {"dent", "dented", "pichka", "bent", "ding"},
            {"sticker", "decal", "badge", "logo"},
            {"blue", "neela", "navy"},
            {"black", "kala", "kaala"},
            {"keychain", "keyring", "chabi", "charm"},
            {"casio", "fx991", "fx991cw", "991cw"},
        ]
        _, exp_toks = _normalise_answer_tokens(expected_answer)
        _, usr_toks = _normalise_answer_tokens(user_answer)
        exp_set = set(exp_toks)
        usr_set = set(usr_toks)
        matches = len(exp_set & usr_set)
        for group in synonym_groups:
            if (exp_set & group) and (usr_set & group):
                matches += 1
        ok = matches >= 1 and len(usr_toks) > 0
        return VerificationOutput(
            matched=ok,
            reason="Verified via semantic keyword equivalence." if ok else "Answer did not match the hidden verification detail.",
        )

    prompt = f"""You are verifying ownership of a found campus item at IIT Bhilai.
Question asked to claimant: {question}
Expected answer recorded from item: {expected_answer}
Claimant's answer (may be in English, Hindi, or Hinglish): {user_answer}

Decide if the claimant's answer refers to the same identifying detail as the expected answer.
Return ONLY valid JSON: {{"matched": true or false, "reason": "brief 1-line explanation"}}
"""
    res = call_gemma_validated(
        prompt=prompt,
        schema_cls=VerificationOutput,
        fallback_fn=_fallback_fuzzy,
        max_retries=2,
    )
    return res.matched, "gemma_fuzzy", res.reason
