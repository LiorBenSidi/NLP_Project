# evaluation.py
# This file contains the core evaluation logic for the project.
# The `evaluate_reports` function calculates the success rate by comparing
# the LLM's generated report against the ground truth report.

def evaluate_reports(llm_report, ground_truth_report):
    """
    Compares the LLM's generated report against the ground truth and calculates accuracy.
    This function is designed to validate the complex JSON structure including metadata and stats.
    """
    discrepancies, total_fields, correct_fields = [], 0, 0
    
    # 1. Evaluate top-level metadata
    for key in ["matchup", "final_score"]:
        total_fields += 1
        llm_value = llm_report.get(key)
        gt_value = ground_truth_report.get(key)
        if llm_value == gt_value:
            correct_fields += 1
        else:
            discrepancies.append(f"METADATA MISMATCH for '{key}': GT='{gt_value}', LLM='{llm_value}'")

    # 2. Evaluate team metadata (rosters, coaches, etc.)
    gt_teams_meta = ground_truth_report.get("teams", {})
    llm_teams_meta = llm_report.get("teams", {})
    for team_name, gt_meta in gt_teams_meta.items():
        if team_name not in llm_teams_meta:
            discrepancies.append(f"MISSING TEAM METADATA for: {team_name}")
            continue
        llm_meta = llm_teams_meta[team_name]
        for key, gt_value in gt_meta.items():
            total_fields += 1
            llm_value = llm_meta.get(key)
            # For lists like rosters, order doesn't matter, so we compare sets
            if isinstance(gt_value, list):
                if llm_value and set(gt_value) == set(llm_value):
                    correct_fields += 1
                else:
                    discrepancies.append(f"TEAM METADATA MISMATCH for {team_name} ('{key}'): GT={gt_value}, LLM={llm_value}")
            else: # For strings like coach name
                if gt_value == llm_value:
                    correct_fields += 1
                else:
                    discrepancies.append(f"TEAM METADATA MISMATCH for {team_name} ('{key}'): GT='{gt_value}', LLM='{llm_value}'")

    # 3. Evaluate detailed final statistics
    gt_stats_block = ground_truth_report.get("final_stats", {})
    llm_stats_block = llm_report.get("final_stats", {})
    for team_name, gt_team_data in gt_stats_block.items():
        if team_name not in llm_stats_block:
            discrepancies.append(f"MISSING STATS BLOCK for team: {team_name}")
            continue
        llm_team_data = llm_stats_block[team_name]
        
        # Compare team aggregate stats
        gt_agg_stats = gt_team_data.get("stats", {})
        llm_agg_stats = llm_team_data.get("stats", {})
        for stat, gt_value in gt_agg_stats.items():
            total_fields += 1
            llm_value = llm_agg_stats.get(stat)
            if gt_value == llm_value:
                correct_fields += 1
            else:
                discrepancies.append(f"TEAM STAT MISMATCH for {team_name} ({stat}): GT={gt_value}, LLM={llm_value}")

        # Compare player stats
        gt_players = gt_team_data.get("players", {})
        llm_players = llm_team_data.get("players", {})
        for player_name, gt_player_stats in gt_players.items():
            if player_name not in llm_players:
                discrepancies.append(f"MISSING PLAYER STATS for: {player_name} ({team_name})")
                total_fields += len(gt_player_stats)
                continue
            
            llm_player_stats = llm_players[player_name]
            for stat, gt_value in gt_player_stats.items():
                total_fields += 1
                llm_value = llm_player_stats.get(stat)
                if gt_value == llm_value:
                    correct_fields += 1
                else:
                    discrepancies.append(f"PLAYER STAT MISMATCH for {player_name} ({stat}): GT={gt_value}, LLM={llm_value}")

    accuracy = (correct_fields / total_fields) * 100 if total_fields > 0 else 0
    return accuracy, discrepancies