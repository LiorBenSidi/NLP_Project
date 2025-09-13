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
    return {"meta": {}, "team_stats": {}, "players": {}, "eval_type": eval_type, "contributions": [], "totals": {}}

def _add_contrib(details, *, scope, team=None, player=None, stat=None, gt=None, llm=None, correct=False, weight=1.0, note=""):
    contrib = {
        "scope": scope, # "meta" | "team" | "player" | "non_participant"
        "team": team,
        "player": player,
        "stat": stat,
        "gt": gt,
        "llm": llm,
        "correct": bool(correct),
        "weight": float(weight),   # The "worth" inside the calculation
        "contribution": float(weight if correct else 0.0),
        "formula": f"{1 if correct else 0} * {weight:.6f}",
        "note": note
    }
    details["contributions"].append(contrib)


def is_player_stats_all_zeros(player_stats):
    """Helper function to check if a player's stats dictionary contains only zeros."""
    #if not player_stats:
    if not player_stats or not isinstance(player_stats, dict):
        return False
    return all((value == 0) for value in player_stats.values())

def evaluate_reports(llm_report, ground_truth_report, eval_type='field', return_details=False):
    """
    Compares the LLM's generated report against the ground truth and calculates accuracy.
    This function is designed to validate the complex JSON structure including metadata and stats.
    """
    discrepancies, total_fields, correct_fields = [], 0, 0
    details = _init_details(eval_type)


    # 1. Evaluate the final score
    total_fields += 1
    llm_value = llm_report.get("final_score")
    gt_value = ground_truth_report.get("final_score")
    ok = (llm_value == gt_value)
    if ok:
        correct_fields += 1
    else:
        discrepancies.append(f"METADATA MISMATCH for 'final_score': GT='{gt_value}', LLM='{llm_value}'")
    details["meta"]["final_score"] = {"gt": gt_value, "llm": llm_value, "ok": ok}
    _add_contrib(details, scope="meta", stat="final_score", gt=gt_value, llm=llm_value, correct=ok, weight=1.0, note="meta: final_score counts as one full field")

    # 2. Evaluate detailed final statistics
    gt_stats_block = ground_truth_report.get("final_stats", {})
    llm_stats_block = llm_report.get("final_stats", {})
    for team_name, gt_team_data in gt_stats_block.items():
        if team_name not in llm_stats_block:
            discrepancies.append(f"MISSING STATS BLOCK for team: {team_name}")
            continue
        llm_team_data = llm_stats_block[team_name]
        # init details buckets for this team (if not exist)
        details["team_stats"].setdefault(team_name, {})
        details["players"].setdefault(team_name, {})
        
        # Compare team aggregate stats
        gt_agg_stats = gt_team_data.get("stats", {})
        llm_agg_stats = llm_team_data.get("stats", {})

        if eval_type == 'fractional_per_block':
            num_team_stats = len(gt_agg_stats)
            if num_team_stats > 0:
                total_fields += 1  # one field representing the whole team-aggregate block
                matched_team_stats = 0
                w_team = 1.0 / num_team_stats if num_team_stats else 0.0
                for stat, gt_value in gt_agg_stats.items():
                    llm_value = llm_agg_stats.get(stat)
                    ok = (gt_value == llm_value)
                    if ok:
                        matched_team_stats += 1
                    else:
                        discrepancies.append(f"TEAM STAT MISMATCH for {team_name} ({stat}): GT={gt_value}, LLM={llm_value}")
                    # record per-stat detail even in fractional mode
                    details["team_stats"][team_name][stat] = {"gt": gt_value, "llm": llm_value, "ok": ok}
                    # weighted contribution per stat in the team-block (fractional)
                    _add_contrib(
                        details, scope="team", team=team_name, stat=stat,
                        gt=gt_value, llm=llm_value, correct=ok, weight=w_team,
                        note=f"fractional team-block: each stat worth 1/{num_team_stats} of this block"
                    )
                block_fraction = matched_team_stats / num_team_stats
                correct_fields += block_fraction
                # optional block summary
                details["team_stats"][team_name]["__block_fraction__"] = block_fraction

        else: # eval_type == 'field'
            for stat, gt_value in gt_agg_stats.items():
                total_fields += 1
                llm_value = llm_agg_stats.get(stat)
                ok = (gt_value == llm_value)
                if ok:
                    correct_fields += 1
                else:
                    discrepancies.append(f"TEAM STAT MISMATCH for {team_name} ({stat}): GT={gt_value}, LLM={llm_value}")
                details["team_stats"][team_name][stat] = {"gt": gt_value, "llm": llm_value, "ok": ok}
                _add_contrib(
                    details, scope="team", team=team_name, stat=stat,
                    gt=gt_value, llm=llm_value, correct=ok, weight=1.0,
                    note="field mode: each team stat = 1 field"
                )


        # --- Compare player stats based on participation ---
        
        # Get the list of players who actually played from the ground truth report
        participants = ground_truth_report.get("teams", {}).get(team_name, {}).get("participants", [])
        full_roster = ground_truth_report.get("teams", {}).get(team_name, {}).get("roster", [])

        # 1. Evaluate PARTICIPATING players (detailed, stat-by-stat check)
        if eval_type == 'fractional_per_block':
            # Count total player-stat checks (participating player stat fields + one check per non-participant)
            total_player_checks = 0
            matched_player_checks = 0

            # participating
            for player_name in participants:
                gt_player_stats = gt_team_data.get("players", {}).get(player_name, {})
                llm_player_stats = llm_team_data.get("players", {}).get(player_name)
                num_stats = len(gt_player_stats)
                total_player_checks += num_stats

                # init details bucket for this player
                details["players"][team_name].setdefault(player_name, {})

                if not llm_player_stats:
                    discrepancies.append(f"MISSING PARTICIPATING PLAYER: {player_name} in team {team_name}.")
                    for stat, gt_value in gt_player_stats.items():
                        details["players"][team_name][player_name][stat] = {"gt": gt_value, "llm": None, "ok": False}
                    continue

                for stat, gt_value in gt_player_stats.items():
                    llm_value = llm_player_stats.get(stat)
                    ok = (gt_value == llm_value)
                    if ok:
                        matched_player_checks += 1
                    else:
                        discrepancies.append(f"PLAYER STAT MISMATCH for {player_name} ({stat}): GT={gt_value}, LLM={llm_value}")
                    details["players"][team_name][player_name][stat] = {"gt": gt_value, "llm": llm_value, "ok": ok}

            # non-participants: each counts as a single check (all-zeros)
            non_participants = [p for p in full_roster if p not in participants]
            total_player_checks += len(non_participants)
            for player_name in non_participants:
                llm_player_stats = llm_team_data.get("players", {}).get(player_name)
                ok = is_player_stats_all_zeros(llm_player_stats)
                if ok:
                    matched_player_checks += 1
                else:
                    discrepancies.append(f"NON-PARTICIPANT ERROR for {player_name}: Should have all zero stats, but got: {llm_player_stats}")
                # record a one-line summary detail for non-participant
                details["players"][team_name][player_name] = {"all_zeros_expected": True, "llm": llm_player_stats, "ok": ok}

            if total_player_checks > 0:
                total_fields += 1  # one field representing the whole players block
                correct_fields += (matched_player_checks / total_player_checks)

            # add weighted contributions for the players block (fractional)
            if total_player_checks > 0:
                w_players = 1.0 / total_player_checks

                # participants: לכל סטט ששמרת כבר ב-details
                for player_name in participants:
                    for stat, rec in details["players"][team_name].get(player_name, {}).items():
                        if stat == "all_zeros_expected":
                            continue
                        ok_stat = rec.get("ok", False)
                        _add_contrib(
                            details, scope="player", team=team_name, player=player_name, stat=stat,
                            gt=rec.get("gt"), llm=rec.get("llm"), correct=ok_stat, weight=w_players,
                            note=f"fractional players-block ({team_name})"
                        )

                # non-participants: בדיקת all-zeros ששמרת ב-details
                non_participants = [p for p in full_roster if p not in participants]
                for player_name in non_participants:
                    rec = details["players"][team_name].get(player_name, {})
                    ok_np = bool(rec.get("ok"))
                    _add_contrib(
                        details, scope="non_participant", team=team_name, player=player_name, stat="all_zeros",
                        gt="all zeros expected", llm=rec.get("llm"), correct=ok_np, weight=w_players,
                        note=f"fractional players-block ({team_name})"
                    )

        else: # eval_type == 'field'
            # existing behavior: stat-by-stat counting
            for player_name in participants:
                gt_player_stats = gt_team_data.get("players", {}).get(player_name, {})
                llm_player_stats = llm_team_data.get("players", {}).get(player_name)

                # init details bucket for this player
                details["players"][team_name].setdefault(player_name, {})

                if not llm_player_stats:
                    discrepancies.append(f"MISSING PARTICIPATING PLAYER: {player_name} in team {team_name}.")
                    total_fields += len(gt_player_stats) # Penalize for all missing stats
                    for stat, gt_value in gt_player_stats.items():
                        details["players"][team_name][player_name][stat] = {"gt": gt_value, "llm": None, "ok": False}
                    continue
                
                for stat, gt_value in gt_player_stats.items():
                    total_fields += 1
                    llm_value = llm_player_stats.get(stat)
                    ok = (gt_value == llm_value)
                    if ok:
                        correct_fields += 1
                    else:
                        discrepancies.append(f"PLAYER STAT MISMATCH for {player_name} ({stat}): GT={gt_value}, LLM={llm_value}")
                    details["players"][team_name][player_name][stat] = {"gt": gt_value, "llm": llm_value, "ok": ok}
                    # each player-stat is 1 full field
                    _add_contrib(
                        details, scope="player", team=team_name, player=player_name, stat=stat,
                        gt=gt_value, llm=llm_value, correct=ok, weight=1.0,
                        note="field mode: each participating player-stat = 1 field"
                    )

            # 2. Evaluate NON-PARTICIPATING players (simple all-zeros check)
            non_participants = [p for p in full_roster if p not in participants]
            for player_name in non_participants:
                total_fields += 1 # This check counts as one field to evaluate
                llm_player_stats = llm_team_data.get("players", {}).get(player_name)
                ok = is_player_stats_all_zeros(llm_player_stats)
                if ok:
                    correct_fields += 1
                else:
                    discrepancies.append(f"NON-PARTICIPANT ERROR for {player_name}: Should have all zero stats, but got: {llm_player_stats}")
                # record a one-line summary detail for non-participant
                details["players"][team_name][player_name] = {"all_zeros_expected": True, "llm": llm_player_stats, "ok": ok}
                # non-participant all-zeros check counts as 1 field
                _add_contrib(
                    details, scope="non_participant", team=team_name, player=player_name, stat="all_zeros",
                    gt="all zeros expected", llm=llm_player_stats, correct=ok, weight=1.0,
                    note="field mode: each non-participant all-zeros check = 1 field"
                )


    accuracy = (correct_fields / total_fields) * 100 if total_fields > 0 else 0

    # fill totals for the detailed report (if requested)
    if return_details:
        sum_weights = sum(c["weight"] for c in details["contributions"])
        sum_contribs = sum(c["contribution"] for c in details["contributions"])
        details["totals"] = {
            "correct_fields": correct_fields,
            "total_fields": total_fields,
            "accuracy_pct": accuracy,
            "formula": f"{correct_fields}/{total_fields} * 100",
            "weighted_sanity": {
                "sum_weights": sum_weights,
                "sum_contributions": sum_contribs
            }
        }
        return (accuracy, discrepancies, details)
    else:
        return (accuracy, discrepancies)
