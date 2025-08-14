# run_eval.py

# TODO:
# 1. Ask the tutor for clarification on the way that they will contact the LLM using the API.
# 2. Improve the instruction to be more clear and unambiguous
# 3. Provide examples of the expected inputs (events) and output formats (effects)
# 4. Ask the tutor for clarification regarding to the advanced LLM settings.
# 5. Ask the tutor if there will be different scores for students who are using different LLM models.
# 6. Ask the tutor to get clarification on the expected input and output formats for the API calls.

import json
import re
import os
import google.generativeai as genai
from dotenv import load_dotenv
from evaluation import evaluate_reports
import time

# --- Part 1: Constants and Prompt for "Batch Q&A" Strategy ---

# Define the canonical order of stats. This is CRITICAL for correctly mapping the LLM's list response.
TEAM_STATS_ORDER = ["score", "assists", "rebounds", "fouls", "steals", "blocks", "turnovers"]
PLAYER_STATS_ORDER = [
    "points", "assists", "rebounds", "fouls", "steals", "blocks", "turnovers", 
    "2pt_shots_made", "2pt_shots_attempted", "3pt_shots_made", "3pt_shots_attempted", 
    "ft_made", "ft_attempted"
]

# This new prompt instructs the LLM to return only a list of numbers.
SYSTEM_INSTRUCTIONS_PROMPT = """You are a data extraction bot. You will be given a basketball game log and a single, specific question about a team's or player's statistics.

                                ### STATISTIC DEFINITIONS FOR PLAYERS ###
                                - `points`: Total points scored.
                                - `assists`: Total assists made.
                                - `rebounds`: Total rebounds grabbed.
                                - `fouls`: Total fouls committed.
                                - `steals`: Total steals made.
                                - `blocks`: Total blocks made.
                                - `turnovers`: Total turnovers committed.
                                - `2pt_shots_made`: Total 2-point shots made.
                                - `2pt_shots_attempted`: Total 2-point shots attempted.
                                - `3pt_shots_made`: Total 3-point shots made.
                                - `3pt_shots_attempted`: Total 3-point shots attempted.
                                - `ft_made`: Total free throws successfully made.
                                - `ft_attempted`: Total free throws attempted.

                                ### STATISTIC DEFINITIONS FOR TEAMS ###
                                - `score`: Total points scored by the team.
                                - `assists`: Total assists made by the team.
                                - `rebounds`: Total rebounds grabbed by the team.
                                - `fouls`: Total fouls committed by the team.
                                - `steals`: Total steals made by the team.
                                - `blocks`: Total blocks made by the team.
                                - `turnovers`: Total turnovers committed by the team.

                                ### HOW TO HANDLE EACH EVENT ###
                                You must follow these rules precisely when calculating the stats for your answer:
                                - **"{player_A1} delivers a sharp pass to {player_A2}, who finishes with a 2-point layup."**:
                                    - Add 2 points and 1 assists to scoring team_A.
                                    - Add 1 assist to player_A1.
                                    - Add 2 points, 1 `2pt_shots_made`, and 1 `2pt_shots_attempted` to player_A2.
                                - **"{player_A1} finds {player_A2} open on the perimeter for a successful 3-point shot."**:
                                    - Add 3 points and 1 assists to scoring team_A.
                                    - Add 1 assist to player_A1.
                                    - Add 3 points, 1 `3pt_shots_made`, and 1 `3pt_shots_attempted` to player_A2.
                                - **"{player_A} attempts a 2-point shot but misses."**:
                                    - Add 1 `2pt_shots_attempted` to player_A.
                                - **"{player_A} attempts a 3-point shot but misses."**:
                                    - Add 1 `3pt_shots_attempted` to player_A.
                                - **"{player_A} is fouled by {player_B} on a 2-point attempt and will go to the line for two shots."**:
                                    - Add 1 `2pt_shots_attempted` to player_A.
                                    - Add 1 foul to team_B.
                                    - Add 1 foul to player_B.
                                - **"{player_A} is fouled by {player_B} on a 3-point attempt and will go to the line for three shots."**:
                                    - Add 1 `3pt_shots_attempted` to player_A.
                                    - Add 1 foul to team_B.
                                    - Add 1 foul to player_B.
                                - **"{player_A} makes the {shot_ordinal} free throw."**:
                                    - Add 1 point to team_A.
                                    - Add 1 point, 1 `ft_made`, 1 `ft_attempted` to player_A.
                                - **"{player_A} misses the {shot_ordinal} free throw."**:
                                    - Add 1 `ft_attempted` to player_A.
                                - **"{player_A} steals the ball from {player_B}!"**:
                                    - Add 1 steal to team_A.
                                    - Add 1 turnover to team_B.
                                    - Add 1 steal to player_A.
                                    - Add 1 turnover to player_B.
                                - **"{player_A} blocks the 2pt shot from {player_B}!"**:
                                    - Add 1 block to team_A.
                                    - Add 1 block to player_A.
                                    - Add 1 `2pt_shots_attempted` to player_B.
                                - **"{player_A} blocks the 3pt shot from {player_B}!"**:
                                    - Add 1 block to team_A.
                                    - Add 1 block to player_A.
                                    - Add 1 `3pt_shots_attempted` to player_B.
                                - **"A bad pass from {player_A} results in a turnover."**:
                                    - Add 1 turnover to team_A.
                                    - Add 1 turnover to player_A.
                                - **"Defensive rebound by {player_A}."**:
                                    - Add 1 rebound to team_A.
                                    - Add 1 rebound to player_A.
                                - **"Offensive rebound by {player_A}."**:
                                    - Add 1 rebound to team_A.
                                    - Add 1 rebound to player_A.
                                - **"After a VAR review, the previous basket by {player_B} is overturned due to an offensive foul committed by {player_B} before the shot."**:
                                    - This is a correction. You must REVERSE the stats from the previous scoring play.
                                    - Subtract 2 points, 1 assist from team_B.
                                    - Add 1 foul, 1 turnover to team_B.
                                    - Subtract 1 assist from player_A (the passer).
                                    - Subtract 2 points, 1 made shot, and 1 attempted shot from player_B.
                                    - Add 1 foul, 1 turnover to player_B.
                                - **"The referees go to the monitor. After review, the 3-point shot by {player_B} is waved off due to a shot clock violation."**:
                                    - This is a correction. You must REVERSE the stats from the previous scoring play.
                                    - Subtract 3 points, 1 assist from team_B.
                                    - Add 1 turnover to team_B.
                                    - Subtract 1 assist from player_A (the passer).
                                    - Subtract 3 points, 1 made 3pt shot, 1 attempted 3pt shot from player_B.
                                    - Add 1 turnover to player_B.
                                - **""Substitution by {head_coach}: {player_in} comes in for {player_out}.""**:
                                    - This event does not affect player or team statistics. Use it only to track who is on the court.
                                    - player_in is being active and can contribute to the game now, till he may be substituted out.
                                    - player_out is temporarily inactive, but may return later by being substituted in.
                                    - the statistics for both players should be tracked.

                                ### CRITICAL RULES ###
                                -   Your response MUST be ONLY a Python-style list of numbers (e.g., `[10, 5, 0, 2]`).
                                -   The numbers in the list must be in the EXACT order requested in the question.
                                -   Do NOT include any explanations, sentences, or markdown formatting.
                                -   If all stats are zero, return a list of zeros (e.g., `[0, 0, 0, 0]`).

                                Example Question: Give me the stats for Player A in this order: ['points', 'assists', 'rebounds'].
                                Example Correct Response: [15, 4, 8]
                                """

# --- Part 2: Core Functions ---

def construct_roster_context(game_data):
    """
    Creates a detailed string containing the coach, starting lineup, and bench for both teams.
    """
    team_a_name, team_b_name = list(game_data["teams"].keys())
    team_a_meta = game_data["teams"][team_a_name]
    team_b_meta = game_data["teams"][team_b_name]

    return f"""
            ### TEAM INFORMATION FOR CONTEXT ###
            This information tells you which players belong to which team and who is playing at the start of the game.

            # {team_a_name}
            - Coach: {team_a_meta['coach']}
            - Starting Lineup (Active Players): {', '.join(team_a_meta['starting_lineup'])}
            - Bench: {', '.join(team_a_meta['bench'])}

            # {team_b_name}
            - Coach: {team_b_meta['coach']}
            - Starting Lineup (Active Players): {', '.join(team_b_meta['starting_lineup'])}
            - Bench: {', '.join(team_b_meta['bench'])}
            """

def get_gemini_list_response(model, conversation_history):
    """
    Sends a request to the Gemini API and expects a Python-style list of numbers as a response.
    Returns the parsed list or None if parsing fails.
    """
    try:
        print("Sending request to API...")
        response = model.generate_content(
            conversation_history,
            generation_config=genai.types.GenerationConfig( #type: ignore
                temperature=0.5,
                max_output_tokens=1024
            )
        )
        response_text = response.text.strip()
        
        # Use regex to find the list within the response text, making it robust
        match = re.search(r'\[\s*(-?\d+\s*,\s*)*-?\d*\s*\]', response_text)
        if match:
            # Safely parse the found list string into a Python list
            return json.loads(match.group(0))
        else:
            print(f"Warning: Could not find a list in the response: {response_text}")
            return None
    except Exception as e:
        print(f"An error occurred during API call: {e}")
        time.sleep(2) # Wait before the next retry
        return None


# --- Part 3: Main Execution ---
if __name__ == "__main__":
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is missing.")
    else:
        genai.configure(api_key=api_key) #type: ignore
        model = genai.GenerativeModel('gemini-1.5-pro') #type: ignore

        data_dir = "data"
        examples_path = os.path.join(data_dir, "examples.json")
        true_report_path = os.path.join(data_dir, "true_report.json")

        if not os.path.exists(examples_path) or not os.path.exists(true_report_path):
            print("Error: Data files not found.")
        else:
            with open(examples_path, 'r', encoding='utf-8') as f:
                all_examples_data = json.load(f)
            with open(true_report_path, 'r', encoding='utf-8') as f:
                all_true_reports_data = json.load(f)
            
            results_base_dir = os.path.join(data_dir, "llm_responses")
            for difficulty_level in ["basic", "medium", "hard"]:
                os.makedirs(os.path.join(results_base_dir, difficulty_level, "json"), exist_ok=True)

            results_by_difficulty = { "basic": {"accuracies": [], "discrepancies": {}}, "medium": {"accuracies": [], "discrepancies": {}}, "hard": {"accuracies": [], "discrepancies": {}}}
            total_successful_games, total_failed_games = 0, 0
            
            for game_key, game_narrative_data in all_examples_data.items(): 
                print(f"\n{'='*20} PROCESSING {game_key.upper()} {'='*20}")
                ground_truth_data = all_true_reports_data[game_key]
                difficulty = ground_truth_data.get("difficulty", "unknown")

                # 1. Create the skeleton of the final report
                llm_report = json.loads(json.dumps(ground_truth_data))

                # 2. Prepare the narrative log once per game
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                narrative_events = [ansi_escape.sub('', event['description']) for event in game_narrative_data['play_by_play']]
                narrative_log = "\n".join([f"{event['event_id']}. {text}" for event, text in zip(game_narrative_data['play_by_play'], narrative_events)])
                roster_context = construct_roster_context(game_narrative_data)
                
                game_succeeded = True
                
                # 3. Iterate through every team and player to get their stats
                for team_name, team_data in ground_truth_data["final_stats"].items():
                    if not game_succeeded: break

                    # 1. Get TEAM stats
                    question = f"Give me the stats for the team '{team_name}' in this exact order: {TEAM_STATS_ORDER}"
                    
                    conversation_history = [
                        {'role': 'user', 'parts': [SYSTEM_INSTRUCTIONS_PROMPT]},
                        {'role': 'model', 'parts': ["Understood. I will answer each question with a Python-style list of numbers."]},
                        {'role': 'user', 'parts': [roster_context]},
                        {'role': 'user', 'parts': [f"Here is the game log:\n\n{narrative_log}"]},
                        {'role': 'user', 'parts': [question]}
                    ]

                    print(f"  Querying team stats for: {team_name}")
                    response_list = get_gemini_list_response(model, conversation_history)
                    
                    if response_list and len(response_list) == len(TEAM_STATS_ORDER):
                        for i, stat_key in enumerate(TEAM_STATS_ORDER):
                            llm_report["final_stats"][team_name]["stats"][stat_key] = response_list[i]
                    else:
                        print(f"    ERROR: Invalid response for {team_name} stats. Skipping game.")
                        game_succeeded = False
                        continue
                    
                    # 2. Get PLAYER stats for this team
                    for player_name in team_data["players"].keys():
                        if not game_succeeded: break
                        
                        question = f"Give me the stats for the player '{player_name}' in this exact order: {PLAYER_STATS_ORDER}"
                        
                        conversation_history = [
                            {'role': 'user', 'parts': [SYSTEM_INSTRUCTIONS_PROMPT]},
                            {'role': 'model', 'parts': ["Understood. I will answer each question with a Python-style list of numbers."]},
                            {'role': 'user', 'parts': [roster_context]},
                            {'role': 'user', 'parts': [f"Here is the game log:\n\n{narrative_log}"]},
                            {'role': 'user', 'parts': [question]}
                        ]
                        
                        print(f"    Querying player stats for: {player_name}")
                        response_list = get_gemini_list_response(model, conversation_history)

                        if response_list and len(response_list) == len(PLAYER_STATS_ORDER):
                            for i, stat_key in enumerate(PLAYER_STATS_ORDER):
                                llm_report["final_stats"][team_name]["players"][player_name][stat_key] = response_list[i]
                        else:
                            print(f"    ERROR: Invalid response for {player_name} stats. Skipping game.")
                            game_succeeded = False
                            continue
                
                # 4. Evaluate and save if the entire game was processed successfully
                if game_succeeded:
                    total_successful_games += 1

                    # --- Reconstruct the final_score string from the LLM's data ---
                    team_names_list = list(llm_report["final_stats"].keys())
                    teamA_name = team_names_list[0]
                    teamB_name = team_names_list[1]
                    
                    score_A = llm_report["final_stats"][teamA_name]["stats"]["score"]
                    score_B = llm_report["final_stats"][teamB_name]["stats"]["score"]

                    llm_report["final_score"] = f"{teamA_name}: {score_A}, {teamB_name}: {score_B}"

                    json_output_path = os.path.join(results_base_dir, difficulty, "json", f"{game_key}.json")
                    with open(json_output_path, 'w', encoding='utf-8') as f:
                        json.dump(llm_report, f, indent=4, ensure_ascii=False)
                    print(f"Saved LLM-built report to: {json_output_path}")

                    accuracy, discrepancies = evaluate_reports(llm_report, ground_truth_data)
                    if difficulty in results_by_difficulty:
                        results_by_difficulty[difficulty]["accuracies"].append(accuracy)
                        if discrepancies:
                            results_by_difficulty[difficulty]["discrepancies"][game_key] = discrepancies
                    
                    print(f"--- RESULT for {game_key}: Accuracy = {accuracy:.2f}% ---")
                else:
                    total_failed_games += 1
                    if difficulty in results_by_difficulty:
                        results_by_difficulty[difficulty]["discrepancies"][game_key] = ["Failed to get a valid list response for one or more entities."]

            # Final Summary
            print(f"\n\n{'='*20} FINAL SUMMARY {'='*20}")
            final_summary = {"model_used": "gemini-1.5-pro", "total_games_attempted": len(all_examples_data), "successful_games": total_successful_games, "failed_games": total_failed_games, "overall_average_accuracy": "N/A", "results_by_difficulty": {} }
            print(f"Total Games Attempted: {total_successful_games + total_failed_games}")
            print(f"Successful Games: {total_successful_games}")
            print(f"Failed Games: {total_failed_games}")
            
            all_successful_accuracies = []
            for difficulty, results in results_by_difficulty.items():
                num_games_succeeded = len(results["accuracies"])
                if num_games_succeeded > 0:
                    avg_acc = sum(results["accuracies"]) / num_games_succeeded
                    all_successful_accuracies.extend(results["accuracies"])
                    print(f"\n--- Difficulty: {difficulty.upper()} ---")
                    print(f"  Games Succeeded: {num_games_succeeded}")
                    print(f"  Average Accuracy: {avg_acc:.2f}%")
                    final_summary["results_by_difficulty"][difficulty] = {"average_accuracy": f"{avg_acc:.2f}%", "games_succeeded": num_games_succeeded, "discrepancies": results["discrepancies"]}
            
            if all_successful_accuracies:
                overall_average = sum(all_successful_accuracies) / len(all_successful_accuracies)
                print(f"\n-------------------------------------")
                print(f"OVERALL AVERAGE ACCURACY (on {len(all_successful_accuracies)} successful games): {overall_average:.2f}%")
                final_summary["overall_average_accuracy"] = f"{overall_average:.2f}%"

            summary_path = os.path.join(data_dir, "summary.json")
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(final_summary, f, indent=4, ensure_ascii=False)
            print(f"\nFull summary saved to: {summary_path}")