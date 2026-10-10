"""Pydantic schemas for Gemma 4 structured outputs and FastAPI endpoints.

We validate every Gemma 4 JSON response with Pydantic so malformed model output
is caught immediately and safely handled.
"""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


VALID_CATEGORIES = {
    "bottle",
    "bag",
    "calculator",
    "electronics",
    "id_card",
    "wallet",
    "keys",
    "book",
    "eyewear",
    "umbrella",
    "clothing",
    "other",
}


class ExtractedFeatures(BaseModel):
    """Structured item features extracted by Gemma 4 from text (EN/HI/Hinglish) + optional photo."""

    category: str = Field(
        default="other",
        description="Canonical item category (bottle, bag, calculator, electronics, id_card, wallet, keys, book, eyewear, umbrella, clothing, other).",
    )
    colours: List[str] = Field(
        default_factory=list,
        description="Lowercase primary colours of the item (e.g., ['black', 'silver']).",
    )
    brand: str = Field(
        default="",
        description="Brand or maker name if mentioned or visible (e.g., 'Milton', 'Casio', 'Wildcraft').",
    )
    marks: List[str] = Field(
        default_factory=list,
        description="Distinguishing marks, stickers, scratches, dents, keychains, or model numbers.",
    )
    summary: str = Field(
        default="Campus item report",
        description="Concise one-line English summary of the item.",
    )
    sensitive: bool = Field(
        default=False,
        description="True for ID cards, wallets, bank cards, or items containing personal identity documents.",
    )
    verify_question: Optional[str] = Field(
        default=None,
        description="For FOUND items: a question asking the owner about a hidden/specific detail not obvious to a casual passerby.",
    )
    verify_answer: Optional[str] = Field(
        default=None,
        description="For FOUND items: the expected short answer to verify_question (stored privately, never returned publicly).",
    )

    @field_validator("category", mode="before")
    @classmethod
    def normalise_category(cls, v: object) -> str:
        if not isinstance(v, str):
            return "other"
        cleaned = v.strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "water_bottle": "bottle",
            "flask": "bottle",
            "thermos": "bottle",
            "backpack": "bag",
            "laptop_bag": "bag",
            "rucksack": "bag",
            "handbag": "bag",
            "tote": "bag",
            "scientific_calculator": "calculator",
            "calc": "calculator",
            "id": "id_card",
            "student_id": "id_card",
            "identity_card": "id_card",
            "card": "id_card",
            "purse": "wallet",
            "pouch": "wallet",
            "earbuds": "electronics",
            "headphones": "electronics",
            "charger": "electronics",
            "laptop": "electronics",
            "phone": "electronics",
            "mouse": "electronics",
            "pendrive": "electronics",
            "key": "keys",
            "keychain": "keys",
            "notebook": "book",
            "textbook": "book",
            "glasses": "eyewear",
            "spectacles": "eyewear",
            "sunglasses": "eyewear",
            "jacket": "clothing",
            "hoodie": "clothing",
        }
        mapped = aliases.get(cleaned, cleaned)
        return mapped if mapped in VALID_CATEGORIES else "other"

    @field_validator("colours", mode="before")
    @classmethod
    def normalise_colours(cls, v: object) -> List[str]:
        if isinstance(v, str):
            v = [p.strip() for p in v.split(",") if p.strip()]
        if not isinstance(v, list):
            return []
        colour_aliases = {
            "kala": "black",
            "kaala": "black",
            "neela": "blue",
            "navy": "blue",
            "navy blue": "blue",
            "laal": "red",
            "safed": "white",
            "hara": "green",
            "peela": "yellow",
            "bhura": "brown",
            "steel": "silver",
            "metallic": "silver",
            "grey": "gray",
        }
        out: List[str] = []
        for item in v:
            if isinstance(item, str) and item.strip():
                c = colour_aliases.get(item.strip().lower(), item.strip().lower())
                if c not in out:
                    out.append(c)
        return out

    @field_validator("marks", mode="before")
    @classmethod
    def normalise_marks(cls, v: object) -> List[str]:
        if isinstance(v, str):
            v = [p.strip() for p in v.split(",") if p.strip()]
        if not isinstance(v, list):
            return []
        return [str(x).strip() for x in v if str(x).strip()]


class ExplanationOutput(BaseModel):
    """Validated one-sentence explanation from Gemma 4."""

    explanation: str = Field(
        description="One concise sentence explaining why these two reports are a likely match."
    )


class VerificationOutput(BaseModel):
    """Validated semantic answer comparison from Gemma 4."""

    matched: bool = Field(
        description="True if the claimant's answer is semantically equivalent to the expected answer."
    )
    reason: str = Field(
        default="",
        description="Short reason for the verification decision.",
    )


class PublicReport(BaseModel):
    """Public-safe view of a Lost or Found report.

    Privacy guarantees:
    - `description` is always PII-redacted.
    - `verify_answer` and `drop_off_point` are NEVER included.
    - If `sensitive` is True (e.g. ID cards, wallets), `photo_url` is None and
      `photo_hidden` is True so the UI renders a blurred privacy shield.
    """

    id: int
    report_type: Literal["lost", "found"]
    description: str
    zone: str
    event_time: str
    category: str
    colours: List[str]
    brand: str
    marks: List[str]
    summary: str
    sensitive: bool
    has_photo: bool
    photo_hidden: bool
    photo_url: Optional[str] = None
    verify_question: Optional[str] = None
    status: str
    created_at: str


class ComponentDetail(BaseModel):
    """Single component inside the 'How was this scored?' panel."""

    raw_ratio: float
    base_weight: float
    effective_weight: float
    points: float
    detail: str


class MatchResult(BaseModel):
    """Ranked candidate match with heuristic Match score, chips, and Gemma 1-sentence reason."""

    candidate: PublicReport
    match_score: float = Field(description="Heuristic Match score (0 to 100). Never called probability.")
    gated_out: bool = False
    photos_compared: bool = False
    chips: Dict[str, str]
    components: Dict[str, ComponentDetail]
    explanation: str


class VerifyAttemptRequest(BaseModel):
    """Owner's answer to a found item's verification question."""

    lost_report_id: Optional[int] = None
    answer: str


class VerifyAttemptResponse(BaseModel):
    """Result of an ownership verification attempt."""

    claim_id: int
    verified: bool
    method: str
    attempts_used: int
    attempts_remaining: int
    locked: bool
    message: str
    handover_point: Optional[str] = None
    staffed_only: bool = False
    status_stage: str
    stages: List[str] = Field(
        default_factory=lambda: ["Matched", "Verified", "Handover scheduled", "Done"]
    )


class StatusUpdateRequest(BaseModel):
    """Advance the handover tracker after verification succeeds."""

    stage: Literal["Matched", "Verified", "Handover scheduled", "Done"]
