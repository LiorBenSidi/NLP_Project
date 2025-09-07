# Narrative-to-Box-Score — End-to-End Evaluation

## Project Goal
This project tests a Large Language Model's (LLM) ability to synthesize a complete, structured, multi-faceted statistical report (a "box score") from a qualitative, narrative event log of a basketball game. This advanced task requires the model to perform parallel state tracking for multiple entities (teams, players) across numerous statistical categories (points, assists, fouls, etc.).

The project measures the model's ability to accurately attribute stats, perform calculations, and maintain a consistent internal state, serving as a critical test of its potential as a reliable **unstructured-to-structured** data transformation engine.

## The Test:
A compact pipeline that stress-tests an LLM’s ability to convert **play-by-play basketball text** into a **structured box score**. It generates synthetic games, prompts a model, and scores the model’s JSON report against ground truth with clear metrics.

---

## 1) What’s in the repo

- `generate_data.py` — Game simulator that produces:
  - a **play_by_play log** (natural language),
  - the **ground-truth report** (per–team and per-player stats),
  - metadata (difficulty, teams, settings).
- `run_eval.py` — Orchestrates prompting an LLM, validates/normalizes the LLM’s JSON, and calls the evaluator.
- `evaluation.py` — Compares the LLM report to the ground truth and prints per-field scores. Also aggregates **Average** and **Median** scores across games.
- `data/` — Created at runtime with all inputs/outputs for auditing (examples, GT, LLM raw/JSON, summaries).

> The code is intentionally adversarial in “hard” difficulty to surface typical NLP/LLM failure modes (coreference drift, assist-bias, bonus/FT rule conflation, boundary leaks across quarters/OT, etc.).

---

## 2) Setup

**Python**: 3.10+

**Install** (venv recommended):
```bash
pip install -U python-dotenv litellm
```

**API key** (if you use Gemini via LiteLLM; adjust per your provider):
Create a `.env` file in the project root:
```env
GEMINI_API_KEY="your-api-key-here"
```

**Model selection**: In `run_eval.py`, edit:
```python
MODEL_TO_TEST = "gemini/gemini-2.5-pro"   # change to any model you’ve wired via LiteLLM
```
There’s a commented list of alternatives in the file.

---

## 3) Quickstart

**A. Generate a game**
```bash
python generate_data.py
```
This creates under `data/`:
- `examples.jsonl` — pair of game eaxmple and ground true for each 2 lines (Save JSONL with alternating lines: example, then true_report)
- optional (need to set `create_json_files = True` in `generate_data.py`):
- - `examples.json` — the narrative log + metadata sent to the LLM.
- - `true_report.json` — the simulator’s ground truth.

**B. Run the model & evaluate**
```bash
python run_eval.py
```
This produces:
- `llm_response.txt` — raw model output (helpful when JSON is broken - we use methods in code or asking LLM to fix the txt file for valid json).
- `llm_report.json` — the JSON the evaluator uses.
- `summary.json` — aggregated metrics (per evaluation type, plus overall **average** and **median**).

All artifacts live in `data/` for easy inspection.

---

## 4) Game simulation — key rules & knobs

The simulator tries to be realistic while remaining controllable:

- **Quarters & OT**
  - 4 quarters; each quarter must end with a **shot attempt**.
  - **OT** triggers on a tie after Q4; each OT is half a quarter’s length; starts with a **jump ball**; repeats until not tied.
- **Possession & period boundaries**
  - Q1 starts from the jump ball winner.
  - Q2–Q4 alternate opening possession between teams as configured.
- **Team foul limit**
  - Per-quarter limit (default **5**). After a team hits the limit, *any non-shooting* foul yields **two free throws** to the opponent (bonus). Shooting-foul rules remain standard (e.g., 3 FTs on a 3PT attempt).
- **Foul-out**
  - Players foul out at **5**. If a team’s **bench is empty**, it cannot commit fouls (foul events are suppressed for that team).
- **Substitutions**
  - Controlled by difficulty (probabilistic substitutions on dead balls).
- **VAR (video review)**
  - On successful makes, a probabilistic VAR may:
    - **Overturn** a make (offensive foul → points removed, team/personal foul added; bonus FT if in effect).
    - **Change 2↔3** (foot on the line / toe on 3).  
  - The engine rolls back stats in non-monotonic updates correctly.
- **Adversarial wording**
  - The simulator samples **pass verbs** and **shot descriptions** per run. In higher difficulty, wording is more “assist-scented” (e.g., *dished it to*, *set up*) to bait LLMs into false assists.
  - Neutral wording can be forced in “basic” (e.g., *passes to*, *swings it to*).

### Difficulty presets
Defined inside `generate_data.py`:
- **basic** — more neutral wording; longer pass chains **do not** affect stats; fewer disruptive events; no VAR.
- **medium** — mid-complexity; more events; more statistical events: more successful shots and less misses/blocks/fouls; VAR enabled, but low; more substitutions.
- **hard** — adversarial wording; more events; substitutions/VAR; more non-monotonic updates; max types of pass/shots; more statistical events and less misses/blocks/fouls; only maximum one pass per possession. 

Each difficulty controls:
- `target_events` (game length),
- `difficulty_max_passes` (pass chain length per possession),
- `adversarial_assist_bias` (enable the use of pass types for shooting to regular ball passing),
- substitution/VAR rates,
- number of pass/shot types,
- **EVENT_WEIGHTS** for the sampler (relative frequency of: turnovers/steals/timeouts; successful 2PT/3PT patterns; misses/blocks/shooting fouls).

> **Note.** Pass chains are narrative only unless the terminal event affects stats. Pure `pass_ball` events **do not** modify the box score.

---

## 5) Evaluation

Two out-of-the-box evaluation modes (see `run_eval.py`):
- `field` — strict per-field match against ground truth.
- `fractional_per_block` — credit is assigned proportionally within stat blocks.

For each difficulty and evaluation type, the runner prints:
- **Games Succeeded** (valid JSON + evaluated),
- **Average accuracy** and **Median accuracy** across successful games,
- Detailed **discrepancies** per field (from `evaluation.py`).

The final `summary.json` aggregates per-type and overall stats (including **overall median**).

---

## 6) Configuration cheatsheet

Edit these in `generate_data.py` unless otherwise noted:

- **TEAMS & ROSTERS** — Named in the file; feel free to extend.
- **FOUL for players an teams limits** — `FOUL_LIMIT`(foul-out at x fouls), `TEAM_FOUL_LIMIT`(per quarter -> bonus shots after limit reached).
- **Difficulty** — sets `target_events`, `difficulty_max_passes`, `adversarial_assist_bias`, substitution/VAR rates, number of pass/shot types, and **EVENT_WEIGHTS**.
- **Lexicons** — `pass_types`, `opposite_pass_types`, and shot-description pools; per-run subsets are sampled according to difficulty (neutral vs adversarial).

In `run_eval.py`:
- **MODEL_TO_TEST** — choose provider/model via LiteLLM route.
- **EVAL_TYPES** — select which evaluators to run (both types run as deafult)
- `.env` — API key(s).

---

## 7) Reproducibility

Set an explicit seed (optional) at the top of `generate_data.py` before sampling:
```python
import random
random.seed(42)
```

---

## 8) Deliverables (for course submission)

Zip the following structure:
```
nlp_final_project_ID1_ID2.zip
├── data/examples.jsonl
├── generate_data.py
├── run_eval.py
├── evaluation.py
└── README.md
```

---

## Acknowledgements

Thanks to the course staff and the discussion slides on tokenization, n-gram/HMM, log-linear, RNNs/LSTMs, attention/Transformers, and evaluation design — the difficulty presets and adversarial wording are guided by those principles.
