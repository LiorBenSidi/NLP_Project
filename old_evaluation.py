# evaluation.py
# This file contains the core evaluation logic for the project.
# The `evaluate_reports` function calculates the success rate by comparing the LLM's generated report against the ground truth report.

# TODO:
# 1. Consider use weights of failures, or, distance from the ground truth.
# 2. Check the paper that in the pdf instructions for more details. Send it to chatbot to learn it.
# 3. Calculate more metrics (e.g., precision, recall, F1-score) to get a comprehensive view of performance.
# 4. Add more types of evaluation metrics, like if the LLM had success with more then 50% of the stats.
# 5. Add evaluation type, such that if team has 1/7 for teams stats and 1/13 for players stats, insted of 1 for success.

def is_player_stats_all_zeros(player_stats):
    """Helper function to check if a player's stats dictionary contains only zeros."""
    if not player_stats:
        return False
    return all(value == 0 for value in player_stats.values())

def evaluate_reports(llm_report, ground_truth_report):
    """
    Compares the LLM's generated report against the ground truth and calculates accuracy.
    This function is designed to validate the complex JSON structure including metadata and stats.
    """
    discrepancies, total_fields, correct_fields = [], 0, 0

    # 1. Evaluate the final score
    total_fields += 1
    llm_value = llm_report.get("final_score")
    gt_value = ground_truth_report.get("final_score")
    if llm_value == gt_value:
        correct_fields += 1
    else:
        discrepancies.append(f"METADATA MISMATCH for 'final_score': GT='{gt_value}', LLM='{llm_value}'")

    # 2. Evaluate detailed final statistics
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

        # --- Compare player stats based on participation ---
        
        # Get the list of players who actually played from the ground truth report
        participants = ground_truth_report.get("teams", {}).get(team_name, {}).get("participants", [])
        full_roster = ground_truth_report.get("teams", {}).get(team_name, {}).get("roster", [])

        # 1. Evaluate PARTICIPATING players (detailed, stat-by-stat check)
        for player_name in participants:
            gt_player_stats = gt_team_data.get("players", {}).get(player_name, {})
            llm_player_stats = llm_team_data.get("players", {}).get(player_name)

            if not llm_player_stats:
                discrepancies.append(f"MISSING PARTICIPATING PLAYER: {player_name} in team {team_name}.")
                total_fields += len(gt_player_stats) # Penalize for all missing stats
                continue
            
            for stat, gt_value in gt_player_stats.items():
                total_fields += 1
                llm_value = llm_player_stats.get(stat)
                if gt_value == llm_value:
                    correct_fields += 1
                else:
                    discrepancies.append(f"PLAYER STAT MISMATCH for {player_name} ({stat}): GT={gt_value}, LLM={llm_value}")

        # 2. Evaluate NON-PARTICIPATING players (simple all-zeros check)
        non_participants = [p for p in full_roster if p not in participants]
        for player_name in non_participants:
            total_fields += 1 # This check counts as one field to evaluate
            llm_player_stats = llm_team_data.get("players", {}).get(player_name)

            if is_player_stats_all_zeros(llm_player_stats):
                # The LLM correctly reported all zeros for this player who didn't play.
                correct_fields += 1
            else:
                # The LLM either missed the player or incorrectly gave them non-zero stats.
                discrepancies.append(f"NON-PARTICIPANT ERROR for {player_name}: Should have all zero stats, but got: {llm_player_stats}")

    accuracy = (correct_fields / total_fields) * 100 if total_fields > 0 else 0
    return accuracy, discrepancies