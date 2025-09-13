"""
evaluation.py
=============

Purpose
-------
Core evaluation logic comparing a model-produced game report (LLM) against the ground-truth report (GT).
The function `evaluate_reports(...)` performs a single pass and produces contributions that support two scoring modes:

1) "field" — each check (final score/team stat/player check/non-participant check)
   counts as 1. Accuracy = (#correct / #total) * 100.

2) "fractional_per_block" — weights within each logical block sum to ~1.0:
   A) final_score (1.0)
   B) team A stats (~1.0)
   C) team B stats (~1.0)
   D) team A players (~1.0)
   E) team B players (~1.0)
   Accuracy = (sum of correct weights / sum of all block weights) * 100.

Output shape
------------
`evaluate_reports` always returns a triplet:
    (totals_by_type, discrepancies, details_or_none)

- totals_by_type: dict with keys "field" and "fractional_per_block". Each holds:
    {
      "accuracy_pct": float,
      "formula": "numerator/denominator * 100",
      "formula_vars": { ... },         # all variables that compose the formula
      "weighted_sanity": {
          "sum_weights": float,         # internal sums from contributions
          "sum_contributions": float
      }
    }

- discrepancies: list[str] of mismatches detected during comparison.

- details_or_none: None unless `return_details=True`, in which case:
    {
      "eval_type": "both",
      "contributions": [...],
      "totals": <totals_by_type>       # includes formula_vars breakdowns
    }

Contribution schema
-------------------
Each contribution (a single check) has:
{
  "scope": "meta"|"team"|"player"|"non_participant",
  "team": Optional[str],
  "player": Optional[str],
  "stat": Optional[str],               # e.g., "points", "ft_made", "all_zeros"
  "gt": Any,                           # ground-truth value
  "llm": Any,                          # model value
  "correct": bool,
  "weights": {
      "field": float,                  # typically 1.0 per check
      "fractional_per_block": float    # normalized inside each logical block
  },
  "contribution": {
      "field": float,                  # weight if correct else 0.0
      "fractional_per_block": float
  },
  "formula": {
      "field": "1 * 1.000000" (or "0 * ..."),
      "fractional_per_block": "1 * w" / "0 * w"
  },
  "note": str
}

Notes
-----
- This module does not write files; it only computes and returns structured results to be persisted by the caller (see run_eval.py).
- Floating-point sums within blocks may be slightly below 1.0 due to binary representation.
  Display values are snapped to 1.0 where appropriate without affecting the underlying accuracy calculation.
"""

def _init_details(eval_type):
    """Initialize the details container for this evaluation run.

    Args:
        eval_type (str): Kept for compatibility; evaluation is unified ("both").

    Returns:
        dict: A dict with keys:
            - "eval_type": "both"
            - "contributions": []
            - "totals": {}
    """
    return {"eval_type": "both", "contributions": [], "totals": {}}

def _add_contrib(details, *, scope, team=None, player=None, stat=None, gt=None, llm=None, correct=False, w_field=1.0, w_frac=0.0, note=""):
    """Append a single check (contribution) for both scoring modes.

    Semantics
    ---------
    - field mode:    each check has weight w_field (usually 1.0)
    - fractional:    checks inside the same logical block share weights that
                     sum to ~1.0 (e.g., 1/num_stats for team stats)

    Args:
        details (dict): Mutable details dict created by `_init_details`.
        scope (str): One of {"meta","team","player","non_participant"}.
        team (str|None): Team name for team/player/non_participant scopes.
        player (str|None): Player name for player/non_participant scopes.
        stat (str|None): Stat key (e.g., "points", "ft_made", "all_zeros").
        gt, llm (Any): Ground-truth and model values.
        correct (bool): Whether the check passed.
        w_field (float): Weight in field mode (default 1.0).
        w_frac (float):  Weight in fractional_per_block mode (default 0.0).
        note (str):      Free-form note for traceability.

    Side effects:
        Appends a normalized record to details["contributions"].
    """
    details["contributions"].append({
        "scope": scope,
        "team": team,
        "player": player,
        "stat": stat,
        "gt": gt,
        "llm": llm,
        "correct": bool(correct),
        "weights": {
            "field": float(w_field),
            "fractional_per_block": float(w_frac),
        },
        "contribution": {
            "field": float(w_field if correct else 0.0),
            "fractional_per_block": float(w_frac if correct else 0.0),
        },
        "formula": {
            "field": f"{1 if correct else 0} * {w_field:.6f}",
            "fractional_per_block": f"{1 if correct else 0} * {w_frac:.6f}",
        },
        "note": note
    })

def is_player_stats_all_zeros(player_stats):
    """Return True if a player's stats dict contains only zeros.

    Policy
    ------
    - Non-dicts or None → False (treated as “not all zeros”).
    - Empty dict {} → True by Python's all([])==True semantics is *not* used here.
      We explicitly require a dict and test its values; an empty dict currently
      returns False to enforce explicit zero fields.

    Args:
        player_stats (dict|Any): Player stat map or other.

    Returns:
        bool: True if all values are exactly 0; False otherwise.
    """
    #if not player_stats:
    if not player_stats or not isinstance(player_stats, dict):
        return False
    return all((value == 0) for value in player_stats.values())

def evaluate_reports(llm_report, ground_truth_report, eval_type='both', return_details=False):
    """Compare LLM vs. ground-truth report and compute accuracy in two modes.

    High-level flow
    ---------------
    1) Final score:
       - One check ("meta"/"final_score") with weight 1.0 in both modes.

    2) Per-team blocks:
       a) If a whole team block is missing in the LLM report:
          - Count all team stats and all player checks as incorrect using GT values, so the denominator is preserved in both modes.
       b) Else:
          - Team stats (scope="team"): one contribution per stat.
          - Players (scope="player"):
            - participants -> one contribution per stat
            - Non-participants (scope="non_participant"): a single "all_zeros" check per non-participant

       Fractional weights:
       - team stats block: each stat has w_frac = 1 / (#team_stats)
       - players block:    each player stat and each non-participant zero-check
                           share 1 / (participant_stat_checks + non_participants)

    3) Aggregate contributions:
       - Compute sums of weights and correct contributions for both modes.
       - Build `formula_vars`, including explicit components that explain how totals are composed (e.g., participant counts, per-team expected checks).

    4) Return:
       - totals_by_type (with accuracy, formula string, formula_vars, and sanity sums)
       - discrepancies (list of messages)
       - details_or_none (if `return_details=True`, includes contributions + totals)

    Args:
        llm_report (dict): The model's rebuilt/typed report (same shape as GT).
        ground_truth_report (dict): The ground-truth report for the same game.
        eval_type (str): Kept for compatibility; evaluation is unified ("both").
        return_details (bool): If True, `details` is returned (else None).

    Returns:
        tuple[dict, list[str], dict|None]: (totals_by_type, discrepancies, details_or_none)

    totals_by_type schema
    ---------------------
    - field:
        {
          "accuracy_pct": float,
          "formula": "<correct_fields>/<total_fields> * 100",
          "formula_vars": {
            "correct_fields": float,
            "total_fields": float,
            "breakdown": {
              "final_score":      {"correct": float, "total": float},
              "team_stats":       {"correct": float, "total": float, "per_team": {team:{"correct":float,"total":float}}},
              "player_stats": {
                  "correct": float,
                  "total": float,
                  "components": {
                      "participants_total": int,
                      "participants_by_team": {team:int},
                      "roster_total": int,
                      "non_participants_total": int,
                      "stats_per_participant_uniform": int|None,
                      "stats_per_participant_by_team": {team: {"unique_counts":[int], "avg_per_player": float}},
                      "participant_checks_expected_by_team": {team:int},
                      "participant_checks_expected_total": int
                  }
              },
              "non_participants": {"correct": float, "total": float}
            }
          },
          "weighted_sanity": {"sum_weights": float, "sum_contributions": float}
        }

    - fractional_per_block:
        {
          "accuracy_pct": float,
          "formula": "<weighted_correct_sum>/<total_weight_sum> * 100",
          "formula_vars": {
            "weighted_correct_sum": float,
            "total_weight_sum": float,   # display-snapped to an exact block sum
            "blocks": {
              "final_score": {"weight": float, "correct_weight": float},
              "team_stats":  {team: {"weight": float, "matched_stats": int, "total_stats": int, "block_fraction": float}},
              "players":     {team: {"weight": float, "matched_checks": int, "total_checks": int, "block_fraction": float,
                                     "components": {
                                         "participants": int,
                                         "non_participants": int,
                                         "stats_per_participant_uniform": int|None,
                                         "participant_checks_expected": int,
                                         "non_participant_checks_expected": int,
                                         "expected_total_checks": int
                                     }}}
            }
          },
          "weighted_sanity": {"sum_weights": float, "sum_contributions": float}
        }

    Notes
    -----
    - We snap display weights of blocks (≈1.0) to exactly 1.0 (where |x-1| < 1e-9)
      to improve readability. Accuracy uses the raw sums.
    - Helper `_agg(scopes, team, wkey)` aggregates sums/counts over contributions.
    - Helper `is_player_stats_all_zeros` defines the non-participant all-zeros check.
    """
    discrepancies = []
    details = _init_details(eval_type)

    # 1) Final score (counts as its own field/block in both modes)
    llm_value = llm_report.get("final_score")
    gt_value  = ground_truth_report.get("final_score")
    ok = (llm_value == gt_value)
    if not ok:
        discrepancies.append(f"METADATA MISMATCH for 'final_score': GT='{gt_value}', LLM='{llm_value}'")
    _add_contrib(
        details, scope="meta", stat="final_score",
        gt=gt_value, llm=llm_value, correct=ok,
        w_field=1.0, w_frac=1.0,
        note="final_score counts as one full field in both modes"
    )

    # 2) Team + player stats
    gt_stats_block  = ground_truth_report.get("final_stats", {})
    llm_stats_block = llm_report.get("final_stats", {})

    for team_name, gt_team_data in gt_stats_block.items():
        if team_name not in llm_stats_block:
            discrepancies.append(f"MISSING STATS BLOCK for team: {team_name}")
            llm_team_data = {}  # נשתמש בערכים ריקים כדי להוסיף תרומות שגויות במקום לדלג

            # --- Team aggregate stats (treat as all incorrect) ---
            gt_agg_stats = gt_team_data.get("stats", {}) or {}
            num_team_stats = len(gt_agg_stats)
            w_frac_team = (1.0 / num_team_stats) if num_team_stats else 0.0

            for stat, gt_val in gt_agg_stats.items():
                _add_contrib(
                    details, scope="team", team=team_name, stat=stat,
                    gt=gt_val, llm=None, correct=False,
                    w_field=1.0, w_frac=w_frac_team,
                    note="missing team stats block – counted as incorrect"
                )

            # --- Players (participants counted as incorrect; non-participants must be all zeros but missing ≠ zeros) ---
            participants = ground_truth_report.get("teams", {}).get(team_name, {}).get("participants", []) or []
            full_roster  = ground_truth_report.get("teams", {}).get(team_name, {}).get("roster", []) or []

            total_player_checks = 0
            for player_name in participants:
                gt_player_stats = gt_team_data.get("players", {}).get(player_name, {}) or {}
                total_player_checks += len(gt_player_stats)
            non_participants = [p for p in full_roster if p not in participants]
            total_player_checks += len(non_participants)

            w_frac_players = (1.0 / total_player_checks) if total_player_checks > 0 else 0.0

            # participants → incorrect per stat
            for player_name in participants:
                gt_player_stats = gt_team_data.get("players", {}).get(player_name, {}) or {}
                for stat, gt_v in gt_player_stats.items():
                    _add_contrib(
                        details, scope="player", team=team_name, player=player_name, stat=stat,
                        gt=gt_v, llm=None, correct=False,
                        w_field=1.0, w_frac=w_frac_players,
                        note="missing team block → player stat incorrect"
                    )

            # non-participants → expect all zeros; missing stats are NOT zeros → incorrect
            for player_name in non_participants:
                _add_contrib(
                    details, scope="non_participant", team=team_name, player=player_name, stat="all_zeros",
                    gt="all zeros expected", llm=None, correct=False,
                    w_field=1.0, w_frac=w_frac_players,
                    note="missing team block → non-participant not verified as zeros"
                )

            # המשך ללולאה הבאה (בלי continue למעלה)
            continue


        llm_team_data = llm_stats_block.get(team_name, {})

        # --- Team aggregate stats (unified) ---
        gt_agg_stats  = gt_team_data.get("stats", {}) or {}
        llm_agg_stats = llm_team_data.get("stats", {}) or {}

        num_team_stats = len(gt_agg_stats)
        w_frac_team = (1.0 / num_team_stats) if num_team_stats else 0.0

        for stat, gt_val in gt_agg_stats.items():
            llm_val = llm_agg_stats.get(stat)
            ok = (gt_val == llm_val)
            if not ok:
                discrepancies.append(f"TEAM STAT MISMATCH for {team_name} ({stat}): GT={gt_val}, LLM={llm_val}")
            _add_contrib(
                details, scope="team", team=team_name, stat=stat,
                gt=gt_val, llm=llm_val, correct=ok,
                w_field=1.0, w_frac=w_frac_team,
                note=f"team-block: field=1 per stat; fractional=1/{num_team_stats or 1} each"
            )

        # --- Player stats (unified) ---
        participants = ground_truth_report.get("teams", {}).get(team_name, {}).get("participants", []) or []
        full_roster  = ground_truth_report.get("teams", {}).get(team_name, {}).get("roster", []) or []

        # fractional normalization for players: sum to 1 over all checks
        total_player_checks = 0
        for player_name in participants:
            gt_player_stats = gt_team_data.get("players", {}).get(player_name, {}) or {}
            total_player_checks += len(gt_player_stats)
        non_participants = [p for p in full_roster if p not in participants]
        total_player_checks += len(non_participants)

        w_frac_players = (1.0 / total_player_checks) if total_player_checks > 0 else 0.0

        # participating players
        for player_name in participants:
            gt_player_stats  = gt_team_data.get("players", {}).get(player_name, {}) or {}
            llm_player_stats = (llm_team_data.get("players", {}) or {}).get(player_name)
            if not llm_player_stats:
                discrepancies.append(f"MISSING PARTICIPATING PLAYER: {player_name} in team {team_name}.")
                for stat, gt_v in gt_player_stats.items():
                    _add_contrib(
                        details, scope="player", team=team_name, player=player_name, stat=stat,
                        gt=gt_v, llm=None, correct=False,
                        w_field=1.0, w_frac=w_frac_players,
                        note="missing participating player"
                    )
                continue

            for stat, gt_v in gt_player_stats.items():
                llm_v = llm_player_stats.get(stat)
                ok = (gt_v == llm_v)
                if not ok:
                    discrepancies.append(f"PLAYER STAT MISMATCH for {player_name} ({stat}): GT={gt_v}, LLM={llm_v}")
                _add_contrib(
                    details, scope="player", team=team_name, player=player_name, stat=stat,
                    gt=gt_v, llm=llm_v, correct=ok,
                    w_field=1.0, w_frac=w_frac_players,
                    note="player stat"
                )

        # non-participants must be all zeros
        for player_name in non_participants:
            llm_player_stats = (llm_team_data.get("players", {}) or {}).get(player_name)
            ok = is_player_stats_all_zeros(llm_player_stats)
            if not ok:
                discrepancies.append(
                    f"NON-PARTICIPANT ERROR for {player_name}: Should have all zero stats, but got: {llm_player_stats}"
                )
            _add_contrib(
                details, scope="non_participant", team=team_name, player=player_name, stat="all_zeros",
                gt="all zeros expected", llm=llm_player_stats, correct=ok,
                w_field=1.0, w_frac=w_frac_players,
                note="non-participant all-zeros"
            )

    # --- Totals for both evaluation types (from unified contributions) ---
    sum_w_field = sum(c["weights"]["field"] for c in details["contributions"])
    sum_c_field = sum(c["contribution"]["field"] for c in details["contributions"])
    sum_w_frac  = sum(c["weights"]["fractional_per_block"] for c in details["contributions"])
    sum_c_frac  = sum(c["contribution"]["fractional_per_block"] for c in details["contributions"])

    # helpers to aggregate by scope/team from contributions
    def _agg(scopes, *, team=None, wkey="field"):
        w_sum = c_sum = 0.0
        count = matched = 0
        for c in details["contributions"]:
            if c["scope"] not in scopes:
                continue
            if team is not None and c.get("team") != team:
                continue
            w = float(c["weights"][wkey])
            v = float(c["contribution"][wkey])
            w_sum += w
            c_sum += v
            count += 1
            if c.get("correct"):
                matched += 1
        return w_sum, c_sum, count, matched

    # teams seen in contributions
    teams_seen = sorted({c.get("team") for c in details["contributions"] if c.get("team")})

    # --- Gather explicit counts from GT for explanations ---
    participants_by_team = {}
    roster_size_by_team = {}
    non_participants_by_team = {}
    # per-team counts of stats per participating player
    stats_counts_by_team = {}              # {team: {"per_player_counts":[...], "unique_counts":[...], "avg_per_player":float}}
    participant_checks_expected_by_team = {}  # {team: int}

    for t in teams_seen:
        gt_team_final = (ground_truth_report.get("final_stats", {}) or {}).get(t, {}) or {}
        gt_players_map = gt_team_final.get("players", {}) or {}

        team_meta = (ground_truth_report.get("teams", {}) or {}).get(t, {}) or {}
        participants = team_meta.get("participants", []) or []
        roster      = team_meta.get("roster", []) or []

        participants_by_team[t] = len(participants)
        roster_size_by_team[t] = len(roster)
        non_participants_by_team[t] = len([p for p in roster if p not in participants])

        per_counts = []
        for p in participants:
            per_counts.append(len(gt_players_map.get(p, {}) or {}))
        stats_counts_by_team[t] = {
            "per_player_counts": per_counts,
            "unique_counts": sorted(list(set(per_counts))) if per_counts else [],
            "avg_per_player": (sum(per_counts)/len(per_counts)) if per_counts else 0.0
        }
        participant_checks_expected_by_team[t] = sum(per_counts)

    participants_total = sum(participants_by_team.values())
    roster_total = sum(roster_size_by_team.values())
    non_participants_total = sum(non_participants_by_team.values())
    participant_checks_expected_total = sum(participant_checks_expected_by_team.values())

    # Try to detect a uniform stats-per-participant across all participants (e.g., 15)
    _all_counts = []
    for t in teams_seen:
        _all_counts.extend(stats_counts_by_team[t]["per_player_counts"])
    unique_stats_per_participant = sorted(list(set(_all_counts))) if _all_counts else []
    uniform_stats_per_participant = unique_stats_per_participant[0] if len(unique_stats_per_participant) == 1 else None

    # ---- FIELD breakdown (counts) ----
    fs_w_fld, fs_c_fld, _, _      = _agg({"meta"}, wkey="field")
    team_w_fld, team_c_fld, _, _  = _agg({"team"}, wkey="field")
    plyr_w_fld, plyr_c_fld, _, _  = _agg({"player"}, wkey="field")
    nonp_w_fld, nonp_c_fld, _, _  = _agg({"non_participant"}, wkey="field")

    field_per_team = {}
    for t in teams_seen:
        tw, tc, tcount, tmatched = _agg({"team"}, team=t, wkey="field")
        field_per_team[t] = {
            "correct": float(tc),     # כמה סטטי-קבוצה נכונים (count)
            "total":   float(tw)      # כמה סטטי-קבוצה נבדקו (count)
        }

    field_formula_vars = {
        "correct_fields": float(sum_c_field),
        "total_fields":   float(sum_w_field),
        "breakdown": {
            "final_score":      {"correct": float(fs_c_fld),  "total": float(fs_w_fld)},
            "team_stats":       {"correct": float(team_c_fld),"total": float(team_w_fld), "per_team": field_per_team},
            # כאן מוסיפים הסבר מפורש ל-player_stats: total = Σ (סטט' לשחקן) עבור כל המשתתפים
            "player_stats": {
                "correct": float(plyr_c_fld),
                "total":   float(plyr_w_fld),  # אמור להיות participant_checks_expected_total
                "components": {
                    "participants_total": int(participants_total),
                    "participants_by_team": {t: int(v) for t, v in participants_by_team.items()},
                    "roster_total": int(roster_total),
                    "non_participants_total": int(non_participants_total),
                    "stats_per_participant_uniform": int(uniform_stats_per_participant) if uniform_stats_per_participant is not None else None,
                    "stats_per_participant_by_team": {
                        t: {
                            "unique_counts": [int(x) for x in stats_counts_by_team[t]["unique_counts"]],
                            "avg_per_player": float(stats_counts_by_team[t]["avg_per_player"])
                        } for t in teams_seen
                    },
                    "participant_checks_expected_by_team": {t: int(v) for t, v in participant_checks_expected_by_team.items()},
                    "participant_checks_expected_total": int(participant_checks_expected_total)
                }
            },
            "non_participants": {"correct": float(nonp_c_fld), "total": float(nonp_w_fld)}
        }
    }

    # ---- FRACTIONAL breakdown (per-block) ----
    fs_w_fr, fs_c_fr, _, _ = _agg({"meta"}, wkey="fractional_per_block")

    # snap-to-1 helper for display (לא משנה את החישוב, רק את ההצגה)
    def _snap1(x, eps=1e-9):
        x = float(x)
        return 1.0 if abs(x - 1.0) < eps else x

    team_blocks = {}
    players_blocks = {}
    for t in teams_seen:
        # team-stats block
        tw, tc, tcount, tmatched = _agg({"team"}, team=t, wkey="fractional_per_block")
        team_blocks[t] = {
            "weight":          _snap1(tw),                       # מציג 1.0 במקום 0.999...
            "matched_stats":   int(tmatched),
            "total_stats":     int(tcount),
            "block_fraction":  float(tc / max(1e-9, tw))
        }
        # players block (participants + non_participants for this team)
        pw, pc, pcount, pmatched = _agg({"player","non_participant"}, team=t, wkey="fractional_per_block")
        players_blocks[t] = {
            "weight":          _snap1(pw),                       # מציג 1.0 במקום 0.999...
            "matched_checks":  int(pmatched),
            "total_checks":    int(pcount),
            "block_fraction":  float(pc / max(1e-9, pw)) if pw > 0 else 0.0,
            "components": {
                "participants": int(participants_by_team.get(t, 0)),
                "non_participants": int(non_participants_by_team.get(t, 0)),
                "stats_per_participant_uniform": int(uniform_stats_per_participant) if uniform_stats_per_participant is not None else None,
                "participant_checks_expected": int(participant_checks_expected_by_team.get(t, 0)),
                "non_participant_checks_expected": int(non_participants_by_team.get(t, 0)),
                "expected_total_checks": int(participant_checks_expected_by_team.get(t, 0) + non_participants_by_team.get(t, 0))
            }
        }

    # סכום משקלים להצגה (בדיוק 5.0 כשיש את כל הבלוקים)
    fs_display = _snap1(fs_w_fr)
    team_display_sum = sum(_snap1(tb["weight"]) for tb in team_blocks.values())
    players_display_sum = sum(_snap1(pb["weight"]) for pb in players_blocks.values())
    total_weight_sum_display = float(fs_display + team_display_sum + players_display_sum)

    fractional_formula_vars = {
        "weighted_correct_sum": float(sum_c_frac),               # החישוב האמיתי (לא מעוגל)
        "total_weight_sum":     total_weight_sum_display,        # מוצג כסכום בלוקים "נקי"
        "blocks": {
            "final_score": {"weight": fs_display, "correct_weight": float(fs_c_fr)},
            "team_stats":  team_blocks,
            "players":     players_blocks
        }
    }

    totals_by_type = {
        "field": {
            "accuracy_pct": 100.0 * (sum_c_field / max(1e-9, sum_w_field)),
            "formula": f"{sum_c_field}/{sum_w_field} * 100",
            "formula_vars": field_formula_vars,
            "weighted_sanity": {"sum_weights": float(sum_w_field), "sum_contributions": float(sum_c_field)},
        },
        "fractional_per_block": {
            "accuracy_pct": 100.0 * (sum_c_frac / max(1e-9, sum_w_frac)),
            "formula": f"{sum_c_frac}/{total_weight_sum_display} * 100",
            "formula_vars": fractional_formula_vars,
            "weighted_sanity": {"sum_weights": float(sum_w_frac), "sum_contributions": float(sum_c_frac)},
        },
    }

    details_out = None
    if return_details:
        details["totals"] = totals_by_type
        details_out = details

    return (totals_by_type, discrepancies, details_out)