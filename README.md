# CampusLost+: Lost on Campus. Found by AI.

Built for the **IIT Bhilai Hackathon** — targeting **Best Use of Gemma 4** and **Best Open-Source AI Project**.

---

## What It Does

Students post **LOST** or **FOUND** reports in **English, Hindi, or Hinglish**, with or without a photo:
1. **Gemma 4** (called via the `google-genai` SDK using `GEMMA_MODEL=gemma-4-31b-it` from `.env`) extracts structured features (`category`, `colours`, `brand`, `marks`, `summary`, `sensitive` flag) and generates a hidden **ownership verification question** for found items.
2. **Deterministic Code (`backend/scoring.py`)** computes the heuristic **Match score** (0–100) across open reports of the opposite type. **Gemma never produces the numeric match score.**
3. **Gemma 4** writes a single-sentence explanation for each of the Top 3 matches.
4. **Privacy-First Claim Flow**: Claimants answer the hidden verification question (max 3 attempts; exact normalised check first, Gemma 4 fuzzy semantic check only as fallback). Only after verification succeeds is the handover point revealed alongside a 4-stage status tracker (`Matched` → `Verified` → `Handover scheduled` → `Done`).

---

## AI Model Configuration (`Gemma 4` via Gemini API)

All model calls live in `backend/gemma_client.py` and use the official `google-genai` Python SDK.
- **Model ID & API Key**: Loaded **strictly** from `.env` (`GEMINI_API_KEY` and `GEMMA_MODEL`). Nothing is hardcoded in source code.
- **Default Model ID in `.env.example`**:
  - `GEMMA_MODEL=gemma-4-31b-it` (Gemma 4 31B Dense Instruction-Tuned)
  - Alternative supported in Gemini API: `GEMMA_MODEL=gemma-4-26b-a4b-it` (Gemma 4 26B MoE / 4B Active)
- **Resilience Guarantee**: Every Gemma call retries twice (up to 3 attempts), strips markdown code fences, validates JSON with **Pydantic**, and falls back to a deterministic bilingual (English/Hindi/Hinglish) extractor/explainer so a bad response or offline environment never crashes the app.

---

## Setup & Running Locally

### 1. Environment Configuration
```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_key and GEMMA_MODEL=gemma-4-31b-it
```

### 2. Backend Setup (Python + FastAPI + SQLite)
```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python seed.py
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### 3. Frontend Setup (React + Vite + Tailwind CSS)
```bash
cd frontend
npm install
npm run dev
```
Open **http://127.0.0.1:5173** in your browser (API docs available at **http://127.0.0.1:8000/docs**).

### 4. Run Tests & Evaluation
```bash
.\.venv\Scripts\python -m pytest -v
.\.venv\Scripts\python eval/run_eval.py
```

---

## Smart Match Score Table (`backend/scoring.py`)

We label the output **"Match score"** (heuristic, 0–100) — never "probability".

- **Hard Gate**: If `lost.category != found.category`, the pair is immediately gated out (`Match score = 0.0`).
- **Weighted Components**:

| Component | Base Weight (With Photos) | Normalised Weight (Missing Photo) | How It Is Computed in `scoring.py` |
| :--- | :---: | :---: | :--- |
| **Attributes** | **30** | **37.5** | Colour Jaccard overlap (50%), Brand match/conflict (25%), Distinguishing marks token overlap (25%) |
| **Location** | **20** | **25.0** | Loaded from `config/zones.json` (`Library`, `LHC`, `Lab 2`, `Mess`, `Hostel`, `Sports ground`): Same zone = `1.0`, Adjacent = `0.6`, Far = `0.2` |
| **Time** | **15** | **18.75** | Found on/after lost (`1.0` at 0h, linear decay over 7 days / `168h`); `-2h..0h` clock grace = `0.5`; found >2h before lost = `0.0` |
| **Text Similarity** | **15** | **18.75** | Bilingual English/Hinglish synonym-normalised token Jaccard + containment overlap |
| **Visual Similarity** | **20** | *0.0 (Normalised)* | Deterministic Pillow 64-bit perceptual `dHash` (45%) + 48-bin RGB colour histogram cosine similarity (55%) when **both** items have photos |
| **Total** | **100.0** | **100.0** | Returned alongside per-component breakdown for the collapsible *"How was this scored?"* UI panel |

---

## Privacy & Safety Design (`backend/privacy.py`)

1. **PII Redaction on All Stored Text**:
   - **10-digit Indian phone numbers** (with optional `+91` / separators) → `[REDACTED_PHONE]`
   - **8–12 digit institute roll numbers** → `[REDACTED_ROLL]`
   - **Email addresses** → `[REDACTED_EMAIL]`
2. **EXIF Stripping & Image Resizing**:
   - Every uploaded photo is decoded with Pillow, resized with `LANCZOS` so the longest edge is `<= 1024px`, and copied into a brand-new RGB pixel buffer (`Image.new("RGB", ...)`), stripping **100% of EXIF, GPS, and camera metadata**.
3. **Sensitive Item Protection (ID Cards & Wallets)**:
   - Any report classified as `id_card`, `wallet`, or `sensitive=True` has its photo blocked from public endpoints (`photo_url = null`, `photo_hidden = true`, `/api/photos/{file}` returns `403 Forbidden`) and displays a blurred privacy shield placeholder in the UI.
   - Handover is restricted to **Staffed Handover Only** (`Staffed Security Desk (Main Gate / DOSA Office) — Bring Institute ID`).
4. **Zero Secret Leakage on Public Endpoints**:
   - Public endpoints (`/api/reports`, `/api/reports/{id}/matches`) never return `verify_answer` or `drop_off_point`. The handover location is unlocked only after `POST /api/claims/{found_id}/verify` succeeds within the **3-attempt limit**.

---

## Honest Evaluation Table (`eval/run_eval.py`)

Evaluated across the seeded IIT Bhilai dataset (6 Found candidates including 2 near-identical decoy black backpacks, 6 Lost reports):

| Scenario | Lost Report | True Found Report | Predicted Rank | Top-1 Match Score | Runner-Up Score | Top-1 | Top-3 | Notes / Honest Takeaway |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Hinglish Bottle (LHC)** | `#7` | `#1` | **#1** | `92.4 / 100` | `0.0 / 100` | PASS | PASS | Hinglish synonym mapping (`neeche`, `chhoot`) + shared brand (`Milton`) & marks (`dent`, `ISRO sticker`) rank #1 cleanly. |
| **Wildcraft Bag vs 2 Decoys (Lab 2)** | `#8` | `#2` | **#1** | `93.9 / 100` | `31.3 / 100` | PASS | PASS | Separates the true black Wildcraft backpack (`93.9`) from the two decoy black backpacks (`Skybags` in Sports ground `31.3` and `American Tourister` in Hostel `29.2`). |
| **Casio Calculator — No Lost Photo (Library)** | `#9` | `#5` | **#1** | `92.5 / 100` | `0.0 / 100` | PASS | PASS | Lost report has no photo; `scoring.py` normalises the remaining 80 weight points to 100 without crashing. |
| **Sensitive ID Card with Redacted PII (Mess)** | `#10` | `#6` | **#1** | `93.7 / 100` | `0.0 / 100` | PASS | PASS | Roll numbers and phone numbers are redacted to `[REDACTED_ROLL]` / `[REDACTED_PHONE]`, yet zone (`Mess`), lanyard colour, and hostel sticker still match at #1. |

- **Overall Top-1 Accuracy**: **100.0% (4/4)** on specific reports.
- **Overall Top-3 Accuracy**: **100.0% (4/4)**.
- **Known Limitations**: If a student posts an extremely vague report with no brand, marks, or photo (e.g., *"Lost black bag somewhere on campus"*), multiple black backpacks will cluster within ~5–10 points of each other, relying on Top-3 inspection and the hidden verification question during the Claim step to disambiguate ownership.

---

## Agent Skill (`/skill`)

See [`skill/SKILL.md`](skill/SKILL.md) and the runnable CLI tools in `skill/scripts/`:
- `skill/scripts/extract.py`
- `skill/scripts/score.py`
- `skill/scripts/explain.py`
- `skill/scripts/verify.py`
