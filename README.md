# Narrative-to-Box-Score — End-to-End Evaluation

## Project Goal
This project evaluates a Large Language Model’s (LLM) ability to convert a **play-by-play basketball narrative** into a **structured box-score JSON**. <br/>
The pipeline generates synthetic games, prompts an LLM, rebuilds/repairs its JSON to match ground truth, and scores the result with clear, explainable metrics.

---

## 1) What’s in the repo

- **`generate_data.py`** — Game simulator that produces:
  - A **play_by_play** event log (natural language),
  - The **ground-truth report** (final team and per-player stats),
  - Team metadata (rosters, starting lineups, participants).
- **`run_eval.py`** — Orchestrates:
  1) Building the prompt/messages,
  2) Calling the chosen model (with JSON-mode detection & fallback),
  3) Repairing the model’s JSON to the **exact GT schema**,
  4) **Evaluating once** and recording results for both scoring modes.
- **`evaluation.py`** — Compares LLM vs GT in one pass and returns:
  - Per-mode totals (`field`, `fractional_per_block`) with:
    - `accuracy_pct`, human-readable `formula`,
    - **`formula_vars`** (all variables that compose the formula, with per-team/per-block breakdowns),
    - `weighted_sanity` (internal sums for auditing).
- **`data/`** — Created at runtime with all inputs/outputs for auditing (examples, GT, LLM raw/JSON, details, summary).

---

## 2) Setup

**Python**: 3.10+ (we used 3.11.13)

**Install**:
- dotenv
- lightllm
```bash
pip install -U python-dotenv litellm
```

**Provider key(s) (example: Gemini via LiteLLM)**:
- create .env in repo root
- Write a list of keys
```env
GEMINI_API_KEY="your-api-key-here"
```

**Model selection**: In `run_eval.py`:
```python
MODEL_TO_TEST = "gemini/gemini-2.5-pro"   # change to any model that supported by LiteLLM
```
There’s a commented list of alternatives checked LLMs in the file.

---

## 3) Quickstart

**A. Generate a game**
```bash
python generate_data.py
```
This creates under `data/`:
- `examples.jsonl` — pair of game eaxmple and ground true for each 2 lines (Save JSONL with alternating lines: example, then true_report)
- optional (Disabled by default - need to set `create_json_files = True` in `generate_data.py`), and those files are only for readability (not useable) :
- - `examples.json` — the narrative log + metadata sent to the LLM.
- - `true_report.json` — the simulator’s ground truth.

**B. Run the model & evaluate**
```bash
python run_eval.py
```

> **Note:** (Optional) Enabled by default - You can set `RETURN_DETAILS = True`  in `run_eval.py` to get more detials regarding the evaluation analysis per-game.

**Per difficulty (basic, medium, hard), artifacts are saved as**:<br/>
| Path | Description |
|---|---|
| `data/llm_responses/<difficulty>/text/<game_id>.txt` | Raw model output. |
| `data/llm_responses/<difficulty>/json/<game_id>.json` | Rebuilt JSON that matches the ground-truth schema. |
| `data/llm_responses/<difficulty>/json/<game_id>__details.json` | Per-game detailed contributions + totals (both modes). |
| `data/summary.json` | Per-difficulty summary + per-game results. |

---

## 4) Game simulation — key rules & knobs

This section is aligned with the current code in **`generate_data.py`** (and how it is consumed by `run_eval.py`/`evaluation.py`). It explains *exactly* what the simulator produces, how the gameplay logic works, and which knobs you can tune.

### 4.1 Output contract (what the simulator produces)
For each generated game the simulator returns a `game_summary` dict with three main parts:

- **`teams`** — per-team metadata
  - `coach`, `roster` (12 players by default), `starting_lineup` (5), `bench` (7)
  - `participants`: *subset of roster who actually stepped on court* (starters and anyone who subbed in)
- **`play_by_play`** — an ordered list of natural-language events with incremental `event_id`
- **`final_stats`** — the **ground-truth** box score (what the LLM should reconstruct):
  - Per **team**: a `stats` map (points, assists, rebounds, blocks, steals, turnovers, fouls, 2pt/3pt/FT attempts & made, etc.)
  - Per **player**: the same stat schema as the team (attempts ≥ made is enforced)

> `run_eval.py` reads `examples.jsonl` (narrative+metadata as “example”, ground truth as “true_report”) and prompts the model to emit a JSON with the *same shape*. <br/>
`evaluation.py` compares the LLM report to `final_stats` (plus `final_score`).

### 4.2 Game flow & periods
- **Quarters & OT**
  - 4 quarters. If tied after Q4, **OT** periods are added until not tied; each OT starts with a **jump ball** and is modeled as a shortened period.
  - The event stream is *stochastic*; the simulator does **not** guarantee a specific terminal event (e.g., “every quarter ends in a shot”).

- **Possession & period boundaries**
  - Q1 possession starts with the **jump ball** winner.
  - Period-opening possessions are simulated; strict alternation beyond Q1 is **not** guaranteed, as the sampler focuses on coherent but randomized narratives.

### 4.3 Event sampling & state updates
Events are sampled from internal **`event_templates`**. Each template has:
1) A **text** generator (for `play_by_play` phrasing),
2) A **state mutator** (Python callable) that updates the game state: team/player stats, fouls, rebounds, substitutions, and optional **VAR** reversals.

Typical event families:
- **Passes / turnovers** — narrative setup, potential assist chains, occasional turnovers.
- **Shots** — 2PT / 3PT (made/missed) and **FT** (made/missed). On makes/misses we update attempts/made and points; an assist may be credited depending on sampler decisions.
- **Rebounds** — offensive/defensive; increments team and player rebounds.
- **Blocks** — on shot attempts.
- **Fouls** — personal fouls always update player/team fouls. Shooting fouls may generate **FT** sequences. **Foul-out** is handled immediately once a player reaches the limit.
- **Substitutions** — random (difficulty-dependent) or **forced** (post foul-out).
- **VAR corrections** — see §4.6.

**Invariants the mutators keep**
- For every shot type: **attempts ≥ made** (2PT, 3PT, FT), at both team and player levels.
- No negative stats. Counter rollbacks on VAR always keep data consistent.

### 4.4 Lineups, participants, and foul-out
- **Participants**: any player who appears on court (starter or bench entrant). The simulator appends to `participants` whenever a bench player checks in.
- **Substitutions**: modeled on dead balls with a small probability (increases with difficulty). See `_handle_substitution(...)`.
- **Foul-out**: personal **`FOUL_LIMIT`** (default 5). When a player fouls out, `_check_and_handle_foul_out(...)` calls `_force_foul_out_substitution(...)`:
  - If a bench player exists → forced sub and the game continues.
  - If **bench is empty** → the team becomes **short-handed** and further **foul events are suppressed** for that team (no legal sub path).

### 4.5 Team foul limit (optional)
- Per-quarter **team-foul** tracking is **disabled by default**. Set `TEAM_FOUL_LIMIT = 5` to enable.
- When enabled and the per-quarter limit is reached, **non-shooting** fouls trigger **two free throws** (bonus). Shooting-foul rules remain standard (e.g., 3 FTs on 3PT attempts).

### 4.6 VAR (video review)
On some made shots (probability increases with difficulty), the simulator may run a **VAR** event that **reverses or adjusts** the last scoring event:
- **Overturn a make** (e.g., offensive foul): remove points/assist, add foul/turnover where applicable, and apply bonus FT if the team-foul limit is active.
- **Convert 3PT ↔ 2PT** (foot on the line): adjust attempts/made and points accordingly.

All rollbacks are **non-monotonic but consistent**: after a VAR, the schema constraints still hold (e.g., attempts ≥ made).

### 4.7 Difficulty presets (what actually changes)
Difficulty affects the *sampler knobs* and the *narrative style*:
- **`target_events`** — expected game length (#events).
- **`difficulty_max_passes`** — max passes allowed in a possession before a terminal event (e.g., shot/turnover).
- **`adversarial_assist_bias`** — increases the chance of **assist-scented** verbs (“dished to”, “set up”) vs. neutral verbs (“passes to”). *Wording affects the narrative only.*
- **Substitution rate** — higher at harder levels.
- **VAR rate** — higher at harder levels.
- **Lexicon breadth** — more varied pass/shot phrasings at harder levels.
- **`EVENT_WEIGHTS`** — per-difficulty relative probabilities for event families (turnovers/steals/timeouts; made/missed 2PT/3PT; blocks; shooting fouls).

Preset summary:
- **basic** — fewer events, neutral wording, low substitutions, **low/none VAR**, simpler phrasing.
- **medium** — more events, moderate VAR, more subs, richer phrasing.
- **hard** — many events, higher VAR/subs, adversarial wording, more non-monotonic updates.

> **Note:** Pass chains are narrative unless a terminal event affects stats. Pure `pass_ball` events never change the box score.

### 4.8 Knobs & where to tweak them (code map)
- **Stats schema & zero-initialization**: `_initialize_stats()` — add/remove fields here (do so for **both** team and player maps).
- **Foul-out**: constants `FOUL_LIMIT` and helpers `_check_and_handle_foul_out(...)`, `_force_foul_out_substitution(...)`.
- **Substitutions**: `_handle_substitution(...)` and its call sites in `generate_report(...)`.
- **Event sampling**: the `event_templates` list and the sampler block in `generate_report(...)`.
- **VAR behavior**: the specific templates that perform “undo” or “convert 3→2” mutations.
- **Roster size & naming**: team setup at the top of the generator class.
- **Periods/OT length**: driven indirectly by `target_events` and event mix; increase/decrease to emulate longer/shorter games.

### 4.9 How this feeds evaluation (shape & files)
- The *example* (narrative + metadata) and *true_report* (ground truth) are written to **`data/examples.jsonl`** in alternating lines per `game_id`.
- `run_eval.py` builds a strict JSON contract in the **system prompt**, calls the model, repairs/parses the output, and **rebuilds its shape** to match the ground truth.
- `evaluation.py` runs **once** per game and produces *both* scoring modes (`field`, `fractional_per_block`) from the same contributions. Each per-game result in `summary.json` includes `formula_vars` with a transparent breakdown of how the numerator/denominator are composed.

---

## 5) Evaluation

`evaluation.py` compares the model’s rebuilt report to the ground truth **in one pass**, generating a list of **contributions** (one per check). From the same contributions it computes two scoring modes.

### 5.1 What is compared
- **Final score** (meta): a single check comparing the top-level `final_score` string.
- **Team stats** (per team): for each key in `final_stats[team]["stats"]`, one check.
- **Player stats** (participants): for each `participant` and for each stat key in `final_stats[team]["players"][player]`, one check.
- **Non-participants**: for each roster member **not** in `participants`, a single **all_zeros** check (the player must have an all-zero stat map).

> If a whole team block is **missing** from the LLM report, all team+player checks for that team are counted as **incorrect** in both modes (denominator is preserved).

### 5.2 Contribution model (per check)
Every check yields a record:
- `scope`: `"meta"` | `"team"` | `"player"` | `"non_participant"`
- `weights`: `{ "field": 1.0, "fractional_per_block": w }`
- `contribution`: `{ "field": 1.0 or 0.0, "fractional_per_block": w or 0.0 }` (depending on correctness)
- `note`, `team`, `player`, `stat`, `gt`, `llm`, `correct`

The evaluator then aggregates these contributions to compute **accuracy** and to build **`formula_vars`** that expose exactly how numerator/denominator are formed.

### 5.3 Mode A — `field` (strict per-field counting)
- Weight for each check = **1.0**.
- Accuracy = `correct_fields / total_fields * 100`.
- `formula_vars` include a detailed `breakdown`:
  - `final_score`
  - `team_stats` (+ `per_team` counts)
  - `player_stats` with **components** that show how totals are computed:
    - participants per team & total,
    - roster sizes & non-participants,
    - stats-per-participant (uniform value if consistent, otherwise per-team unique counts + average),
    - expected totals per team and overall.

### 5.4 Mode B — `fractional_per_block` (block-normalized)
Each logical block sums to ~**1.0**, and in total we get that the sum of 5 blocks is ~**5.0**:
- `final_score` → **1.0**
- `team_stats` (per team) → ~**1.0** + ~**1.0** = ~**2.0**
- `players` (per team) → ~**1.0** + ~**1.0** = ~**2.0**
> **Note:** “~” means approximately: each block’s fractional weights are sums of many (1/N) terms and floating-point rounding can make the total slightly different from exactly 1.0

Within a block, each check’s fractional weight is **1 / (#checks in that block)**.  
Accuracy = `weighted_correct_sum / total_weight_sum * 100`.

- `formula_vars.blocks` lists, per team:
  - `team_stats`: `weight` (~1.0), `matched_stats`, `total_stats`, `block_fraction` (= matched/total).
  - `players`: `weight` (~1.0), `matched_checks`, `total_checks`, `block_fraction`, and **components**:
    - `participants`, `non_participants`,
    - `participant_checks_expected` (= participants × stats_per_participant),
    - `non_participant_checks_expected` (= non_participants),
    - `expected_total_checks` (= sum of the above).

> **Note:** For readability only, the display “snaps” weights extremely close to 1.0 to **1.0** (accuracy uses raw sums).

### 5.5 Per-game artifacts & summary fields
For every game (under each difficulty) the runner saves:
- **Raw text** → `data/llm_responses/<difficulty>/text/<game_id>.txt`
- **Rebuilt JSON** → `data/llm_responses/<difficulty>/json/<game_id>.json`
- **Details** (all contributions + totals) → `data/llm_responses/<difficulty>/json/<game_id>__details.json`

`data/summary.json` includes, per difficulty:
- `per_game[game_id]`:
  - `discrepancies` — a **single** list for the game.
  - `field` / `fractional_per_block`:
    - `accuracy_pct`, `formula`, **`formula_vars`** (full variables used in the formula).
  - `paths.details` — link to the per-game details file.
- Aggregates:
  - `average_accuracy` and `median_accuracy` per type.

---

## 6) Configuration cheatsheet

This section maps **what you might want to change** to **where in the code** it lives.
Items are aligned with the current implementations of `generate_data.py`, `run_eval.py`, and `evaluation.py`.

---

### 6.1 Core knobs in `generate_data.py`

- **Teams & rosters**  
  Location: team setup at the top of the generator class.  
  - `roster`: default 12 players per team (5 starters + 7 bench).  
  - `starting_lineup`: the first 5 from `roster` (can be customized).  
  - **Changing roster size** is supported; the simulator treats everyone not on court yet as **bench**, and adds them to `participants` when they sub in.

- **Stats schema (team & player)**  
  Location: `_initialize_stats()`  
  - Defines the **full box-score** keys for both team and players (e.g., points, assists, rebounds, 2pt/3pt/FT attempts & made, blocks, steals, turnovers, fouls, etc.).  
  - **Add a new stat** by adding a zeroed field to **both** the team map and the per-player map here, and then update relevant `event_templates` to mutate it.

- **Foul limits (players/teams)**  
  - `FOUL_LIMIT` (default **5**) — personal foul-out threshold. Handled by `_check_and_handle_foul_out(...)` → `_force_foul_out_substitution(...)`.  
  - `TEAM_FOUL_LIMIT` (default **disabled**). Set to e.g. **5** to enable per-quarter team-foul bonus: after the limit, **non-shooting** fouls yield **two FTs**. Shooting-foul rules remain standard (e.g., 3 FTs on 3PT attempts).

- **Substitutions**  
  Location: `_handle_substitution(...)` and call sites in `generate_report(...)`.  
  - Random subs occur on dead balls with a **small probability** (higher in harder difficulties).  
  - Foul-out triggers a **forced** substitution if a bench player is available; otherwise the team becomes **short-handed** and foul events are suppressed for that team.

- **Event sampling**  
  Location: `event_templates` and the sampler block in `generate_report(...)`.  
  - Each template has a **text generator** (for `play_by_play`) and a **state mutator** that updates team/player stats and other state (fouls, rebounds, subs).  
  - The sampler uses per-difficulty **`EVENT_WEIGHTS`** to pick the next event type (made/missed shots, fouls, rebounds, turnovers, etc.).

- **VAR behavior**  
  Location: the templates that perform “undo” or “convert 3→2” mutations.  
  - On a probabilistic basis (higher on **hard**), the simulator may **overturn** a made shot (remove points/assist, add turnover/foul) or **convert** a 3PT ↔ 2PT (foot on the line).  
  - All updates keep the invariants (e.g., **attempts ≥ made**).

- **Lexicons (phrasing)**  
  - `pass_types`, `opposite_pass_types`, and shot-description pools.  
  - Per difficulty, a **subset** is sampled each run. Higher difficulty increases **adversarial wording** (assist-leaning verbs like “dished to”, “set up”). Wording **does not** alter stats; it only affects narrative complexity.

- **Difficulty presets**  
  Location: `generate_report(...)` (difficulty block).  
  - **basic / medium / hard** configure:  
    - `target_events` (game length)  
    - `difficulty_max_passes` (max passes before a terminal event)  
    - `adversarial_assist_bias` (probability to pick assist-leaning verbs)  
    - substitution & VAR **rates**  
    - lexicon breadth (how many pass/shot phrasings are sampled)  
    - **`EVENT_WEIGHTS`** (relative frequency of event families)  
  - **Adding a new difficulty**: add a new entry with the fields above and include its name wherever the project iterates over difficulties.

- **Reproducibility**  
  Top of file (or in `__main__`): set a fixed seed to make generation deterministic per run:
  ```python
  import random
  random.seed(42)

### 6.2 Orchestration in `run_eval.py`

**Where to change / What it does**

- **Model route**
  - **Where:** `MODEL_TO_TEST` (top of file)
  - **Change to:** any LiteLLM route string (e.g., `"gemini/gemini-2.5-pro"`, `"gpt-4o"`, etc.)
  - **Effect:** selects the single model used for the entire run.

- **Per-game details file**
  - **Where:** `RETURN_DETAILS = False`
  - **Set to:** `True` to save `json/<game_id>__details.json` (full contributions + totals for both modes).

- **Evaluation modes list**
  - **Where:** `EVAL_TYPES = ["field", "fractional_per_block"]`
  - **Note:** kept for formatting/aggregation. Both modes are always computed from a single pass; usually do **not** change.

- **Rate limiting / sleeps**
  - **Where:** two places in `__main__` right after API calls:
    - after the main completion: `minutes = 0.25` → `time.sleep(60 * minutes)`
    - after the JSON-fixer call: `minutes = 1`
  - **Change to:** smaller/larger delays if you hit provider rate-limits (or `0` to disable).

- **Retries on malformed output**
  - **Where:** `max_retries = 2`
  - **Effect:** number of API attempts per game (repair & fixer are tried within each attempt).

- **JSON-mode detection & fallback**
  - **Where:** `DOES_MODEL_SUPPORT_JSON`, `JSON_MODE_FAILED_ONCE`, `get_litellm_response(...)`
  - **Behavior:** checks LiteLLM registry once; tries `response_format={"type":"json_object"}` (and Gemini `extra_body`).  
    On a single failure, flips `JSON_MODE_FAILED_ONCE=True` and falls back to plain text + local repair for the rest of the run.
  - **Force plain text:** set `DOES_MODEL_SUPPORT_JSON = False` near the top.

- **Prompt & schema**
  - **Where:** `SYSTEM_INSTRUCTIONS_PROMPT` (+ embedded **canonical JSON example**)
  - **Change:** edit only if you add/remove stats; keep the strict “single JSON object” rules.

- **JSON repair**
  - **Where:** `repair_json_structure(...)`, `ask_model_to_fix_json(...)`
  - **What:** strips code fences/comments, removes trailing commas, balances braces/brackets; optional second call asks the model to return a valid JSON.

- **Shape rebuild & typing**
  - **Where:** `repair_and_rebuild_json(...)`, `coerce_numbers_inplace(...)`
  - **What:** coerces the model output to the **exact** ground-truth shape and types (ints/strings/lists), including moving a wrongly nested team back to the top level.

- **All-zeros guard**
  - **Where:** `is_report_all_zeros(...)`
  - **What:** rejects degenerate reports (team points==0 and every player has zeros).  
    **Disable check:** return `False` from this function.

- **Outputs & summary**
  - **Where:** main loop under `__main__`
  - **What:** saves `text/`, rebuilt `json/`, optional `__details.json`, and builds `data/summary.json` with per-game `formula_vars`, `accuracy_pct`, and a single `discrepancies` list.

### 6.3 Evaluator in `evaluation.py`

**Single-pass contributions → two scoring modes**

- **Entry point**
  - **Where:** `evaluate_reports(llm_report, ground_truth_report, eval_type="both", return_details=False)`
  - **Note:** `eval_type` is kept for API compatibility; the function always computes **both** modes from the same contributions.

- **What is checked (per game)**
  - `final_score` (one check, scope `"meta"`).
  - **Team stats**: for every key under `final_stats[team]["stats"]`.
  - **Players (participants)**: for every participant × every stat key under `final_stats[team]["players"][player]`.
  - **Non-participants**: one `"all_zeros"` check per roster member **not** in `participants`.

- **Missing team block policy**
  - **Where:** early branch inside the team loop.
  - **Effect:** if LLM is missing an entire team block, **all** team stats and **all** player checks for that team are counted as **incorrect** in both modes (denominator preserved).

- **Weights (how scores are computed)**
  - **Where:** `_add_contrib(...)` + the loops that call it.
  - **`field` mode:** each check uses `w_field = 1.0`.
  - **`fractional_per_block` mode:**
    - `final_score`: `w_frac = 1.0`
    - team-stats block (per team): each stat uses `w_frac = 1 / (#team_stats)`
    - players block (per team): each player-stat and each non-participant zero-check uses  
      `w_frac = 1 / (participant_stat_checks + non_participants)`
  - **Display “snap to 1.0”**
    - **Where:** `_snap1(x, eps=1e-9)`
    - **What:** only for **display** in `formula_vars` the block weights are shown as `1.0` if `|x-1|<eps`.  
      Accuracy uses the **raw** sums (no snapping).

- **Non-participant all-zeros test**
  - **Where:** `is_player_stats_all_zeros(...)`
  - **Rule:** only a dict with **all zeros** passes; `None`/missing/partial stats → **incorrect**.

- **`formula_vars` (transparent numerators/denominators)**
  - **`field` → `formula`:** `"correct_fields/total_fields * 100"`  
    **`formula_vars.breakdown`:**
    - `final_score` — `{correct,total}`
    - `team_stats` — `{correct,total, per_team:{...}}`
    - `player_stats` — `{correct,total, components:{...}}`, where `components` includes:
      - `participants_total`, `participants_by_team`
      - `roster_total`, `non_participants_total`
      - `stats_per_participant_uniform` (if constant) **or** per-team `unique_counts` + `avg_per_player`
      - `participant_checks_expected_by_team` and the overall `participant_checks_expected_total`
    - `non_participants` — `{correct,total}`
  - **`fractional_per_block` → `formula`:** `"weighted_correct_sum/total_weight_sum * 100"`  
    **`formula_vars.blocks`:**
    - `final_score` — `{weight, correct_weight}`
    - `team_stats` — per team: `{weight, matched_stats, total_stats, block_fraction}`
    - `players` — per team: `{weight, matched_checks, total_checks, block_fraction, components:{participants, non_participants, participant_checks_expected, non_participant_checks_expected, expected_total_checks}}`

- **Return shape**
  - `(totals_by_type, discrepancies, details_or_none)`  
    - `totals_by_type["field"|"fractional_per_block"]` → `{accuracy_pct, formula, formula_vars, weighted_sanity}`
    - `discrepancies` → one list per game
    - `details_or_none` → only if `return_details=True` (also saved by `run_eval.py` when `RETURN_DETAILS=True`)

---

## 7) Deliverables (for course submission)

Baseline zip (after **data generation**):
```
nlp_final_project_ID1_ID2.zip
├── data/examples.jsonl
├── generate_data.py
├── run_eval.py
├── evaluation.py
└── README.md
```

If you **also run** `run_eval.py`, you will have additional artifacts:
```
data/
  llm_responses/
    basic/
      text/<game_id>.txt
      json/<game_id>.json
      json/<game_id>__details.json
    medium/
      text/<game_id>.txt
      json/<game_id>.json
      json/<game_id>__details.json
    hard/
      text/<game_id>.txt
      json/<game_id>.json
      json/<game_id>__details.json
  summary.json
```

- `text/<game_id>.txt` — raw model output (useful for debugging malformed JSON).
- `json/<game_id>.json` — rebuilt/typed JSON that **matches the ground-truth schema**.
- `json/<game_id>__details.json` — full per-check contributions + totals (both modes) for that game.
- `summary.json` — per-difficulty summary with per-game `accuracy_pct`, `formula`, and **`formula_vars`**.

---

---
## 8) Teams & rosters (EuroBasket 2025) — provenance & disclaimers

The simulator ships with **named teams, head coaches, and 12‑player rosters** inspired by EuroBasket 2025 national teams. These appear as **constants** in `generate_data.py` (see the `self.<Team>_head_coach`, `self.<Team>_players`, and the `self.teams` mapping). Example (abbreviated):

```python
# --- Team and Player Data ---
self.Israel_head_coach = "Ariel Beit-Halahmy"
self.Israel_players = ["Khadeen Carrington", "Itay Segev", "Deni Avdija", ...]

self.Iceland_head_coach = "Craig Pedersen"
self.Iceland_players = ["Aegir Steinarsson", "Hilmar Henningsson", "Jon Axel Gudmundsson", ...]

# ...
self.teams = {
    "Israel":  {"head_coach": self.Israel_head_coach,  "players": self.Israel_players},
    "Iceland": {"head_coach": self.Iceland_head_coach, "players": self.Iceland_players},
    "Poland":  {"head_coach": self.Poland_head_coach,  "players": self.Poland_players},
    "France":  {"head_coach": self.France_head_coach,  "players": self.France_players},
    "Belgium": {"head_coach": self.Belgium_head_coach, "players": self.Belgium_players},
    "Slovenia":{"head_coach": self.Slovenia_head_coach,"players": self.Slovenia_players},
}
```

**Important notes**
- Names are used **for educational/demo purposes** and to stress-test narrative NLG/NLU.  
  All **play‑by‑play** and **box scores** are **synthetic**; no real match data is used.
- Rosters in code are **illustrative** and may **not** match official selections at any point in time.
- You are encouraged to **replace** coaches/rosters with your own:
  - Edit the `self.<Team>_head_coach` and `self.<Team>_players` lists.
  - Update the `self.teams` dictionary accordingly.
  - Roster size is typically **12**; the first **5** are used as the `starting_lineup`.
- The project is **not affiliated** with FIBA/EuroBasket or any federation. “EuroBasket” is a trademark of its respective owners.


## Acknowledgements

This work was completed for "Natural Language Processing" Course, Technion - Israel Institute of Technology.

**Models & Tooling**  
- Evaluations used a single model route (`MODEL_TO_TEST`) via **LiteLLM**, with provider credentials loaded through **python-dotenv**.  
- The runner detects JSON-mode support and gracefully falls back to plain text + local JSON repair when needed.  
- Special thanks to the LiteLLM maintainers and provider SDKs that make multi-model experiments straightforward.

**Open-source Libraries**  
- `litellm`, `python-dotenv` (plus Python standard library modules like `json`, `re`, `os`, `pathlib`, `random`).

**Design & Evaluation**  
- The evaluator (`evaluation.py`) uses a single pass of “contributions” to report **both** scoring modes:
  - **field** (per-field counting) and  
  - **fractional_per_block** (block-normalized weights).  
  The exported `formula_vars` were inspired by best practices for transparent, auditable metrics.

**Data**  
- All game logs and box scores are **synthetic**, generated by `generate_data.py`. No real player statistics were used; names/plays/narratives are fictional.

**Contributors**  
- **Lior Ben Sidi** - B.Sc. in Information Systems Engineering
- **Ido Avital** - B.Sc. in Data Science and Engineering