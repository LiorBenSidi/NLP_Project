# evaluation.py
# This file contains the core evaluation logic for the project.
# The `evaluate_reports` function calculates the success rate by comparing the LLM's generated report against the ground truth report.

# TODO:
# 1. Consider use weights of failures, or, distance from the ground truth.
# 2. Check the paper that in the pdf instructions for more details. Send it to chatbot to learn it.
# 3. Calculate more metrics (e.g., precision, recall, F1-score) to get a comprehensive view of performance.
# 4. Add more types of evaluation metrics, like if the LLM had success with more then 50% of the stats.
# 5. Add penalty for players that get more than 5 fouls by the LLM.
# 6. consider adaptation of the evaluation based on fouls limit, Overtimes

def _init_details(eval_type):
    return {"eval_type": "both", "contributions": [], "totals": {}}

def _add_contrib(details, *, scope, team=None, player=None, stat=None,
                 gt=None, llm=None, correct=False, w_field=1.0, w_frac=0.0, note=""):
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
    """Helper function to check if a player's stats dictionary contains only zeros."""
    #if not player_stats:
    if not player_stats or not isinstance(player_stats, dict):
        return False
    return all((value == 0) for value in player_stats.values())

def evaluate_reports(llm_report, ground_truth_report, eval_type='both', return_details=False):
    """
    Compares the LLM's generated report against the ground truth and calculates accuracy.
    Single-pass evaluation that produces contributions usable by both 'field' and 'fractional_per_block'.
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

    totals_by_type = {
        "field": {
            "accuracy_pct": 100.0 * (sum_c_field / max(1e-9, sum_w_field)),
            "formula": f"{sum_c_field}/{sum_w_field} * 100",
            "weighted_sanity": {"sum_weights": sum_w_field, "sum_contributions": sum_c_field},
        },
        "fractional_per_block": {
            "accuracy_pct": 100.0 * (sum_c_frac / max(1e-9, sum_w_frac)),
            "formula": f"{sum_c_frac}/{sum_w_frac} * 100",
            "weighted_sanity": {"sum_weights": sum_w_frac, "sum_contributions": sum_c_frac},
        },
    }

    details_out = None
    if return_details:
        details["totals"] = totals_by_type
        details_out = details

    return (totals_by_type, discrepancies, details_out)