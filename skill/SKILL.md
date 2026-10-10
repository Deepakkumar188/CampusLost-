---
# TODO: Check and validate these frontmatter fields against the official Agent Skill Open Standard specification.
name: campus-lost-plus
description: Extract structured features from English/Hindi/Hinglish lost-and-found reports with Gemma 4, compute a deterministic heuristic Match score in scoring.py, explain matches in one sentence, and verify item ownership with privacy redaction.
version: 1.0.0
license: MIT
---

# CampusLost+ Agent Skill (`extract`, `score`, `explain`, `verify`)

This skill equips an AI agent to operate the four core workflows of **CampusLost+** ("Lost on Campus. Found by AI.") for IIT Bhilai without ever exposing unredacted PII or letting the LLM invent numeric match scores.

## Core Guardrails
1. **Environment-Only Credentials**: `GEMINI_API_KEY` and `GEMMA_MODEL` must be read strictly from `.env`. Never hardcode model names or API keys.
2. **Heuristic Match Score Only**: Always use `backend/scoring.py` (`skill/scripts/score.py`) to compute the **Match score** (0–100). Never call the score a "probability".
3. **Privacy First**: Always run `backend/privacy.py` (`redact_pii`) before storing or displaying text. Never expose `verify_answer`, `drop_off_point`, or photos of sensitive items (`id_card`, `wallet`) on public endpoints.

---

## Available CLI Scripts

Run all commands from the repository root (`campus-lost-plus/`) using the project's virtual environment (`.venv/Scripts/python` on Windows or `.venv/bin/python` on Linux/macOS):

### 1. `extract` — Structured Feature Extraction (`skill/scripts/extract.py`)
Extracts `category`, `colours`, `brand`, `marks`, `summary`, `sensitive` flag, and (for found items) a hidden `verify_question` + `verify_answer` using Gemma 4 with 2 retries, fence stripping, Pydantic validation, and safe fallback.

```bash
python skill/scripts/extract.py --type lost --text "Mera black Milton bottle LHC ke bahar bench pe chhoot gaya, dent near cap"
```

### 2. `score` — Heuristic Match Score (`skill/scripts/score.py`)
Computes the deterministic **Match score** (0–100) between a lost JSON report and a found JSON report using `backend/scoring.py` and `config/zones.json`. Returns the score, signal chips (`Colour`, `Zone`, `Time`), and full component breakdown.

```bash
python skill/scripts/score.py \
  --lost '{"category":"bottle","colours":["black"],"brand":"Milton","marks":["dent"],"zone":"LHC","event_time":"2026-10-10T09:00:00Z","description":"Black Milton bottle"}' \
  --found '{"category":"bottle","colours":["black"],"brand":"Milton","marks":["dent"],"zone":"LHC","event_time":"2026-10-10T10:00:00Z","description":"Found black Milton bottle"}'
```

### 3. `explain` — One-Sentence Match Explanation (`skill/scripts/explain.py`)
Generates a concise one-sentence plain-English explanation of why two reports match using Gemma 4 (with deterministic fallback).

```bash
python skill/scripts/explain.py \
  --lost '{"category":"bottle","colours":["black"],"brand":"Milton","zone":"LHC","summary":"Black Milton Bottle"}' \
  --found '{"category":"bottle","colours":["black"],"brand":"Milton","zone":"LHC","summary":"Black Milton Bottle"}'
```

### 4. `verify` — Ownership Answer Verification (`skill/scripts/verify.py`)
Checks a claimant's answer against the hidden verification answer: runs **exact normalised matching first**, and calls **Gemma 4 fuzzy semantic check** only as a fallback.

```bash
python skill/scripts/verify.py \
  --question "What sticker is on the bottom of the bottle?" \
  --expected "ISRO sticker and dent near cap" \
  --answer "It has an ISRO sticker on the base and a small dent by the cap"
```
