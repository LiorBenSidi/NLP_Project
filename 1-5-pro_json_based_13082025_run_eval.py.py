# run_eval.py

# TODO:
# 1. Ask the tutor for clarification on the way that they will contact the LLM using the API.
# 2. Improve the instruction to be more clear and unambiguous
# 3. Provide examples of the expected inputs (events) and output formats (effects)
# 4. Ask the tutor for clarification regarding to the advanced LLM settings.
# 5. Ask the tutor if there will be different scores for students who are using different LLM models.
# 6. Need to fix bug with the brackets ({}).

import json
import re
import os
import google.generativeai as genai
from dotenv import load_dotenv
from evaluation import evaluate_reports

# --- Part 1: Prompt Templates and Static Data ---
SYSTEM_INSTRUCTIONS_PROMPT = """You are an automated sports data analyst.
                                Your sole function is to process a narrative log of a basketball game and convert it into a structured JSON report.

                                ### YOUR TASK ###
                                Analyze the provided game log, which lists events in chronological order.
                                You will be given the full rosters for each team. Your JSON output must include stats for EVERY player on the roster,
                                even if they did not play (in which case their stats should be 0).
                                Synthesize this information into a single, complete JSON object that represents the final box score of the game.

                                ### HOW TO HANDLE EACH EVENT ###
                                You must follow these rules precisely for each event type:
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

                                ### REQUIRED STATS ###
                                For each team, you must track and include the following:
                                - `matchup`: The matchup of the game in the format "<TeamNameA> vs <TeamNameB>"
                                - `final_score`: The final score of the game in the format "<TeamNameA>: <ScoreA>, <TeamNameB>: <ScoreB>"
                                - `teams`: The two teams participating in the game, including their coaches and rosters.
                                - `final_stats`: A dictionary containing the stats for each team.

                                For each player, you must track and include the following statistics:
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

                                ### OUTPUT FORMAT ###
                                - Your entire response MUST be a single, valid JSON object.
                                - Your response MUST NOT include any introductory text, explanations, or conversational markdown (like ```json ...```).
                                - Your response MUST begin with the character `{` and end with the character `}`.

                                ### EXAMPLE JSON STRUCTURE ###
                                Your final output must follow this exact structure. Do not add, remove, or rename any keys.

                                ```json
                                {
                                    "matchup": "TeamNameA vs TeamNameB",
                                    "final_score": "TeamNameA: 0, TeamNameB: 0",
                                    "teams": {
                                        "TeamNameA": {
                                            "coach": "CoachNameA",
                                            "roster": ["PlayerName1-A", "PlayerName2-A", "PlayerName3-A", "PlayerName4-A", "PlayerName5-A"],
                                            "starting_lineup": ["PlayerName1-A", "PlayerName2-A", "PlayerName3-A", "PlayerName4-A", "PlayerName5-A"],
                                            "bench": ["PlayerName6-A", "PlayerName7-A", "PlayerName8-A", "PlayerName9-A", "PlayerName10-A"]
                                        },
                                        "TeamNameB": {
                                            "coach": "CoachNameB",
                                            "roster": ["PlayerName1-B", "PlayerName2-B", "PlayerName3-B", "PlayerName4-B", "PlayerName5-B"],
                                            "starting_lineup": ["PlayerName1-B", "PlayerName2-B", "PlayerName3-B", "PlayerName4-B", "PlayerName5-B"],
                                            "bench": ["PlayerName6-B", "PlayerName7-B", "PlayerName8-B", "PlayerName9-B", "PlayerName10-B"]
                                        }
                                    },
                                    "final_stats": {
                                        "TeamNameA": {
                                            "stats": {
                                                "score": 0,
                                                "assists": 0,
                                                "rebounds": 0,
                                                "fouls": 0,
                                                "steals": 0,
                                                "blocks": 0,
                                                "turnovers": 0
                                            },
                                            "players": {
                                                "PlayerName1-A": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName2-A": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName3-A": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName4-A": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName5-A": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName6-A": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName7-A": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName8-A": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName9-A": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName10-A": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                }
                                            }
                                        },
                                        "TeamNameB": {
                                            "stats": {
                                            "score": 0,
                                            "assists": 0,
                                            "rebounds": 0,
                                            "fouls": 0,
                                            "steals": 0,
                                            "blocks": 0,
                                            "turnovers": 0
                                            },
                                            "players": {
                                                "PlayerName1-B": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName2-B": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName3-B": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName4-B": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName5-B": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName6-B": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName7-B": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName8-B": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName9-B": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                },
                                                "PlayerName10-B": {
                                                    "points": 0,
                                                    "assists": 0,
                                                    "rebounds": 0,
                                                    "fouls": 0,
                                                    "steals": 0,
                                                    "blocks": 0,
                                                    "turnovers": 0,
                                                    "2pt_shots_made": 0,
                                                    "2pt_shots_attempted": 0,
                                                    "3pt_shots_made": 0,
                                                    "3pt_shots_attempted": 0,
                                                    "ft_made": 0,
                                                    "ft_attempted": 0
                                                }
                                            }
                                        }
                                    }
                                }
                                ```
                            """
MODEL_ACKNOWLEDGEMENT = "Understood. I am ready to process the game log. I will adhere to all instructions and provide the final report as a single, valid JSON object."

# --- Part 2: Core Functions ---

def construct_prompt(game_data):
    """Constructs the full user prompt string to be sent to the Gemini API."""
    team_a_name, team_b_name = list(game_data["teams"].keys())

    # Provide all context the LLM needs to build the complex JSON
    roster_info = f"""
                    ### TEAM METADATA & ROSTERS ###
                    # {team_a_name}
                    - Coach: {game_data['teams'][team_a_name]['coach']}
                    - Starting Lineup: {game_data['teams'][team_a_name]['starting_lineup']}
                    - Bench: {game_data['teams'][team_a_name]['bench']}

                    # {team_b_name}
                    - Coach: {game_data['teams'][team_b_name]['coach']}
                    - Starting Lineup: {game_data['teams'][team_b_name]['starting_lineup']}
                    - Bench: {game_data['teams'][team_b_name]['bench']}
                    """
    
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    narrative_events = [ansi_escape.sub('', event['description']) for event in game_data['play_by_play']]
    narrative_log = "\n".join([f"{event['event_id']}. {text}" for event, text in zip(game_data['play_by_play'], narrative_events)])
    
    full_prompt = SYSTEM_INSTRUCTIONS_PROMPT + "\n\n" + roster_info + "\n### GAME LOG ###\n" + narrative_log + "\n\nNow, generate the complete JSON object for the game described above. Your response must begin with `{` and end with `}`."
    #full_prompt = SYSTEM_INSTRUCTIONS_PROMPT + "\n\n" + roster_info + "\n### GAME LOG ###\n" + narrative_log
    return full_prompt

def is_report_all_zeros(llm_report):
    """
    Checks if all key statistics in the LLM report are zero.
    This is a sign that the LLM has failed to process the data.
    """
    try:
        for team_data in llm_report.get("final_stats", {}).values():
            if team_data.get("stats", {}).get("score", 0) != 0:
                return False # Found a non-zero score, report is likely valid
            for player_stats in team_data.get("players", {}).values():
                if (player_stats.get("points", 0) != 0
                    or player_stats.get("assists", 0) != 0
                    or player_stats.get("rebounds", 0) != 0
                    or player_stats.get("fouls", 0) != 0
                    or player_stats.get("steals", 0) != 0
                    or player_stats.get("blocks", 0) != 0
                    or player_stats.get("turnovers", 0) != 0
                    or player_stats.get("2pt_shots_attempted", 0) != 0
                    or player_stats.get("3pt_shots_attempted", 0) != 0
                    or player_stats.get("ft_attempted", 0) != 0):
                    return False # Found a player with points, report is likely valid
    except (TypeError, AttributeError):
        # The report is malformed, so we can't check it. Treat as not all zeros.
        return False
    
    # If we get through the whole loop without finding a non-zero score or points, it's an all-zero report.
    return True

def get_gemini_response(prompt_text):
    """Calls the Google Gemini API and returns the response content."""
    try:
        # Using 'gemini-1.5-pro'
        model = genai.GenerativeModel('gemini-1.5-pro') #type: ignore

        generation_config = genai.types.GenerationConfig(  #type: ignore
            temperature=0.5,
            max_output_tokens=8192,
            response_mime_type="application/json",
        )
        print("\nSending request to Google Gemini API (model: gemini-1.5-pro)...")
        response = model.generate_content(prompt_text, generation_config=generation_config)
        print("Response received from API.")
        return response.text.strip()
    except Exception as e:
        print(f"An unexpected error occurred while calling the Gemini API: {e}")
        return None
    
# def get_gemini_response(prompt_text):
#     """Calls the Google Gemini API and returns the response content."""
#     try:
#         # UPDATED: Using 'gemini-2.5-pro'
#         model = genai.GenerativeModel(model_name="gemini-2.5-pro") #type: ignore

#         generation_config = {
#             "temperature": 0.5,
#             "max_output_tokens": 8192,
#             "response_mime_type": "application/json",
#         }
#         print("\nSending request to Google Gemini API (model: gemini-2.5-pro)...")
#         response = model.generate_content(prompt_text, generation_config=generation_config) #type: ignore
#         print("Response received from API.")
#         return response.text.strip()
#     except Exception as e:
#         print(f"An unexpected error occurred while calling the Gemini API: {e}")
#         return None

# def evaluate_reports(llm_report, ground_truth_report):
#     """
#     Completely rewritten to evaluate the new, complex JSON structure.
#     """
#     discrepancies, total_fields, correct_fields = [], 0, 0
    
#     # 1. Evaluate top-level metadata
#     for key in ["matchup", "final_score"]:
#         total_fields += 1
#         llm_value = llm_report.get(key)
#         gt_value = ground_truth_report.get(key)
#         if llm_value == gt_value:
#             correct_fields += 1
#         else:
#             discrepancies.append(f"METADATA MISMATCH for '{key}': GT='{gt_value}', LLM='{llm_value}'")

#     # 2. Evaluate team metadata (rosters, coaches, etc.)
#     gt_teams_meta = ground_truth_report.get("teams", {})
#     llm_teams_meta = llm_report.get("teams", {})
#     for team_name, gt_meta in gt_teams_meta.items():
#         if team_name not in llm_teams_meta:
#             discrepancies.append(f"MISSING TEAM METADATA for: {team_name}")
#             continue
#         llm_meta = llm_teams_meta[team_name]
#         for key, gt_value in gt_meta.items():
#             total_fields += 1
#             llm_value = llm_meta.get(key)
#             # For lists like rosters, order doesn't matter, so we compare sets
#             if isinstance(gt_value, list):
#                 if llm_value and set(gt_value) == set(llm_value):
#                     correct_fields += 1
#                 else:
#                     discrepancies.append(f"TEAM METADATA MISMATCH for {team_name} ('{key}'): GT={gt_value}, LLM={llm_value}")
#             else: # For strings like coach name
#                 if gt_value == llm_value:
#                     correct_fields += 1
#                 else:
#                     discrepancies.append(f"TEAM METADATA MISMATCH for {team_name} ('{key}'): GT='{gt_value}', LLM='{llm_value}'")

#     # 3. Evaluate detailed final statistics (the original evaluation logic)
#     gt_stats_block = ground_truth_report.get("final_stats", {})
#     llm_stats_block = llm_report.get("final_stats", {})
#     for team_name, gt_team_data in gt_stats_block.items():
#         if team_name not in llm_stats_block:
#             discrepancies.append(f"MISSING STATS BLOCK for team: {team_name}")
#             continue
#         llm_team_data = llm_stats_block[team_name]
        
#         # Compare team aggregate stats
#         gt_agg_stats = gt_team_data.get("stats", {})
#         llm_agg_stats = llm_team_data.get("stats", {})
#         for stat, gt_value in gt_agg_stats.items():
#             total_fields += 1
#             llm_value = llm_agg_stats.get(stat)
#             if gt_value == llm_value:
#                 correct_fields += 1
#             else:
#                 discrepancies.append(f"TEAM STAT MISMATCH for {team_name} ({stat}): GT={gt_value}, LLM={llm_value}")

#         # Compare player stats
#         gt_players = gt_team_data.get("players", {})
#         llm_players = llm_team_data.get("players", {})
#         for player_name, gt_player_stats in gt_players.items():
#             if player_name not in llm_players:
#                 discrepancies.append(f"MISSING PLAYER STATS for: {player_name} ({team_name})")
#                 total_fields += len(gt_player_stats)
#                 continue
            
#             llm_player_stats = llm_players[player_name]
#             for stat, gt_value in gt_player_stats.items():
#                 total_fields += 1
#                 llm_value = llm_player_stats.get(stat)
#                 if gt_value == llm_value:
#                     correct_fields += 1
#                 else:
#                     discrepancies.append(f"PLAYER STAT MISMATCH for {player_name} ({stat}): GT={gt_value}, LLM={llm_value}")

#     accuracy = (correct_fields / total_fields) * 100 if total_fields > 0 else 0
#     return accuracy, discrepancies

def repair_json_output(json_string, team_names):
    """
    Attempts to fix JSON errors by first fixing truncation, then using the
    number of added braces to diagnose and fix the specific team nesting error.
    """
    repaired = json_string.strip()
    if repaired.startswith("```json"):
        repaired = repaired.strip("```json")
    if repaired.endswith("```"):
        repaired = repaired.strip("```")
    repaired = repaired.strip()

    # --- Step 1: Fix truncation by balancing the braces ---
    open_braces = repaired.count('{')   
    close_braces = repaired.count('}')
    
    extra_braces_at_end = 0
    if repaired.startswith('{') and open_braces < close_braces:
        extra_braces_at_end = close_braces - open_braces
        print(f"Step 1: Fixing truncation by removing {extra_braces_at_end} closing brace(s).")
        repaired = repaired[:-extra_braces_at_end]

    missing_braces_at_end = 0
    if repaired.startswith('{') and open_braces > close_braces:
        missing_braces_at_end = open_braces - close_braces
        print(f"Step 1: Fixing truncation by adding {missing_braces_at_end} closing brace(s).")
        repaired += '}' * missing_braces_at_end

    # --- Step 2: Use the number of missing braces as a clue to diagnose the nesting error ---
    # According to your insight, if we were missing exactly 2 braces, it's highly likely
    # the nesting error occurred, because the LLM forgot to close the 'players' and 'team' objects.
    if missing_braces_at_end >= 1 and len(team_names) == 2:
        team_a, team_b = team_names[0], team_names[1]
        
        # Define the error pattern: a closing player block followed immediately by the other team's key.
        # This is syntactically invalid JSON.
        error_pattern_1 = f'}}}}, "{team_b}"'
        # The correction replace '}},' at the end of last player of 'TeamA', with "}}}," making the structure valid.
        correct_pattern_1 = f'}}}}}}, "{team_b}"' 
        
        error_pattern_2 = f'}}}}, "{team_a}"'
        correct_pattern_2 = f'}}}}}}, "{team_a}"'

        # Check if this specific error exists in the string
        if error_pattern_1 in repaired:
            print(f"Step 2: Detected and fixing incorrect nesting of team '{team_b}'.")
            # Perform the replacement
            repaired = repaired.replace(error_pattern_1, correct_pattern_1, 1)
            # CRITICAL: As you said, since our replacement added 2 braces, we must now
            # remove 1 of the braces we added at the very end to avoid having too many.
            repaired = repaired[:-1]  # Remove the last brace we added in Step 1
        elif error_pattern_2 in repaired:
            print(f"Step 2: Detected and fixing incorrect nesting of team '{team_a}'.")
            repaired = repaired.replace(error_pattern_2, correct_pattern_2, 1)
            repaired = repaired[:-1]
            
    return repaired

# def repair_json_output(json_string):
#     """
#     Attempts to fix common JSON errors, like missing closing braces, by counting them.
#     """
#     # Trim whitespace and remove common markdown artifacts
#     repaired = json_string.strip()
#     if repaired.startswith("```json"):
#         repaired = repaired.strip("```json")
#     if repaired.endswith("```"):
#         repaired = repaired.strip("```")
#     repaired = repaired.strip() # Strip again just in case

#     # This is the new, more robust check: count the braces
#     open_braces = repaired.count('{')   
#     close_braces = repaired.count('}')
    
#     if repaired.startswith('{') and open_braces > close_braces:
#         # Add the exact number of missing braces
#         missing_count = open_braces - close_braces
#         print(f"Attempting to fix JSON by adding {missing_count} closing brace(s) '}}'.")
#         repaired += '}' * missing_count
    
#     return repaired

# --- Part 3: Main Execution ---
# --- Support multi difficulty levels ---

if __name__ == "__main__":
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is missing. Please create a .env file and add your key.")
    else:
        genai.configure(api_key=api_key) #type: ignore

        data_dir = "data"
        examples_path = os.path.join(data_dir, "examples.json")
        true_report_path = os.path.join(data_dir, "true_report.json")

        if not os.path.exists(examples_path) or not os.path.exists(true_report_path):
            print("Error: Data files not found. Please run 'generate_data.py' first.")
        else:
            with open(examples_path, 'r', encoding='utf-8') as f:
                all_examples_data = json.load(f)
            with open(true_report_path, 'r', encoding='utf-8') as f:
                all_true_reports_data = json.load(f)
            
            results_base_dir = os.path.join(data_dir, "llm_responses")
            for difficulty_level in ["basic", "medium", "hard"]:
                os.makedirs(os.path.join(results_base_dir, difficulty_level, "text"), exist_ok=True)
                os.makedirs(os.path.join(results_base_dir, difficulty_level, "json"), exist_ok=True)

            # --- Structures to hold results grouped by difficulty ---
            results_by_difficulty = {
                "basic": {"accuracies": [], "discrepancies": {}},
                "medium": {"accuracies": [], "discrepancies": {}},
                "hard": {"accuracies": [], "discrepancies": {}}
            }
            total_successful_games = 0
            total_failed_games = 0
            
            # Loop through each game in the dataset
            for game_key, game_narrative_data in all_examples_data.items():
                print(f"\n{'='*20} PROCESSING {game_key.upper()} {'='*20}")
                ground_truth_data = all_true_reports_data[game_key]
                team_names = list(ground_truth_data.get("teams", {}).keys())
                difficulty = ground_truth_data.get("difficulty", "unknown")

                # --- Retry Logic ---
                max_retries = 1
                llm_report = None
                llm_response_str = ""
                
                for attempt in range(max_retries):
                    prompt = construct_prompt(game_narrative_data)
                    current_response_str = get_gemini_response(prompt)
                    
                    if not current_response_str:
                        print(f"--- ERROR on attempt {attempt + 1}: No response from API. Retrying... ---")
                        continue

                    llm_response_str = current_response_str
                    repaired_llm_str = repair_json_output(llm_response_str, team_names)
                    
                    try:
                        llm_report_candidate = json.loads(repaired_llm_str)
                        if not is_report_all_zeros(llm_report_candidate):
                            print(f"--- SUCCESS on attempt {attempt + 1}: LLM provided a valid, non-empty report. ---")
                            llm_report = llm_report_candidate
                            break
                        else:
                            print(f"--- WARNING on attempt {attempt + 1}: All-zeros report. Retrying... ---")
                            llm_report = None
                    except json.JSONDecodeError:
                        print(f"--- ERROR on attempt {attempt + 1}: Could not parse JSON. Retrying... ---")
                        llm_report = None
                
                # --- Process the final result of the retries ---
                raw_output_path = os.path.join(results_base_dir, difficulty, "text", f"{game_key}.txt")
                with open(raw_output_path, 'w', encoding='utf-8') as f:
                    f.write(llm_response_str)
                
                if llm_report:
                    total_successful_games += 1
                    json_output_path = os.path.join(results_base_dir, difficulty, "json", f"{game_key}.json")
                    with open(json_output_path, 'w', encoding='utf-8') as f:
                        json.dump(llm_report, f, indent=4, ensure_ascii=False)
                    print(f"Saved parsed report to: {json_output_path}")

                    accuracy, discrepancies = evaluate_reports(llm_report, ground_truth_data)
                    
                    # Add results to the correct difficulty group
                    if difficulty in results_by_difficulty:
                        results_by_difficulty[difficulty]["accuracies"].append(accuracy)
                        if discrepancies:
                            results_by_difficulty[difficulty]["discrepancies"][game_key] = discrepancies
                    
                    print(f"--- RESULT for {game_key}: Accuracy = {accuracy:.2f}% ---")
                else:
                    total_failed_games += 1
                    print(f"--- FAILURE for {game_key}: Could not get a valid report after {max_retries} attempts. SKIPPING. ---")
                    if difficulty in results_by_difficulty:
                         results_by_difficulty[difficulty]["discrepancies"][game_key] = [f"Failed after {max_retries} retries."]

            # --- Final Summary ---
            print(f"\n\n{'='*20} FINAL SUMMARY {'='*20}")
            
            final_summary = {
                "total_games_attempted": len(all_examples_data),
                "successful_games": total_successful_games,
                "failed_games": total_failed_games,
                "overall_average_accuracy": "N/A",
                "results_by_difficulty": {}
            }

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
                    
                    final_summary["results_by_difficulty"][difficulty] = {
                        "average_accuracy": f"{avg_acc:.2f}%",
                        "games_succeeded": num_games_succeeded,
                        "discrepancies": results["discrepancies"]
                    }
            
            # Calculate and print the overall average accuracy
            if all_successful_accuracies:
                overall_average = sum(all_successful_accuracies) / len(all_successful_accuracies)
                print(f"\n-------------------------------------")
                print(f"OVERALL AVERAGE ACCURACY (on {len(all_successful_accuracies)} successful games): {overall_average:.2f}%")
                final_summary["overall_average_accuracy"] = f"{overall_average:.2f}%"

            summary_path = os.path.join(data_dir, "summary.json")
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(final_summary, f, indent=4, ensure_ascii=False)
            print(f"\nFull summary saved to: {summary_path}")


# # --- Part 3: Main Execution ---
# # --- handle failed attempts (got all-zeors stats) ---

# if __name__ == "__main__":
#     load_dotenv(override=True)
#     api_key = os.getenv("GEMINI_API_KEY")
#     if not api_key:
#         print("Error: GEMINI_API_KEY is missing.")
#     else:
#         genai.configure(api_key=api_key) #type: ignore

#         data_dir = "data"
#         examples_path = os.path.join(data_dir, "examples.json")
#         true_report_path = os.path.join(data_dir, "true_report.json")

#         if not os.path.exists(examples_path) or not os.path.exists(true_report_path):
#             print("Error: Data files not found. Please run 'generate_data.py' first.")
#         else:
#             with open(examples_path, 'r', encoding='utf-8') as f:
#                 all_examples_data = json.load(f)
#             with open(true_report_path, 'r', encoding='utf-8') as f:
#                 all_true_reports_data = json.load(f)
            
#             text_results_dir = os.path.join(data_dir, "llm_response_text")
#             json_results_dir = os.path.join(data_dir, "llm_response_json")
#             os.makedirs(text_results_dir, exist_ok=True)
#             os.makedirs(json_results_dir, exist_ok=True)

#             all_accuracies = []
#             all_discrepancies = {}
#             successful_games = 0
#             failed_games = 0
            
#             # Loop through each game in the dataset
#             for game_key, game_narrative_data in all_examples_data.items():
#                 print(f"\n{'='*20} PROCESSING {game_key.upper()} {'='*20}")
#                 ground_truth_data = all_true_reports_data[game_key]

#                 # --- Retry Logic ---
#                 max_retries = 2
#                 llm_report = None
#                 llm_response_str = ""
                
#                 for attempt in range(max_retries):
#                     prompt = construct_prompt(game_narrative_data)
#                     current_response_str = get_gemini_response(prompt)
                    
#                     if not current_response_str:
#                         print(f"--- ERROR on attempt {attempt + 1}: No response from API. Retrying... ---")
#                         continue

#                     # Always save the latest raw attempt
#                     llm_response_str = current_response_str
#                     repaired_llm_str = repair_json_output(llm_response_str)
                    
#                     try:
#                         llm_report_candidate = json.loads(repaired_llm_str)
                        
#                         if not is_report_all_zeros(llm_report_candidate):
#                             print(f"--- SUCCESS on attempt {attempt + 1}: LLM provided a valid, non-empty report. ---")
#                             llm_report = llm_report_candidate
#                             break
#                         else:
#                             print(f"--- WARNING on attempt {attempt + 1}: LLM returned an all-zeros report. Retrying... ---")
#                             llm_report = None
#                     except json.JSONDecodeError:
#                         print(f"--- ERROR on attempt {attempt + 1}: Could not parse JSON. Retrying... ---")
#                         llm_report = None
                
#                 # --- Process the final result of the retries ---
#                 raw_output_path = os.path.join(text_results_dir, f"{game_key}.txt")
#                 with open(raw_output_path, 'w', encoding='utf-8') as f:
#                     f.write(llm_response_str)
#                 print(f"Saved final raw response to: {raw_output_path}")

#                 if llm_report:
#                     successful_games += 1
#                     json_output_path = os.path.join(json_results_dir, f"{game_key}.json")
#                     with open(json_output_path, 'w', encoding='utf-8') as f:
#                         json.dump(llm_report, f, indent=4, ensure_ascii=False)
#                     print(f"Saved parsed report to: {json_output_path}")

#                     accuracy, discrepancies = evaluate_reports(llm_report, ground_truth_data)
#                     all_accuracies.append(accuracy)
#                     if discrepancies:
#                         all_discrepancies[game_key] = discrepancies
                    
#                     print(f"--- RESULT for {game_key}: Accuracy = {accuracy:.2f}% ---")
#                 else:
#                     failed_games += 1
#                     print(f"--- FAILURE for {game_key}: Could not get a valid report after {max_retries} attempts. SKIPPING. ---")
#                     all_discrepancies[game_key] = [f"Failed to get a valid, non-empty JSON response from the LLM after {max_retries} retries."]

#             # --- Final Summary ---
#             if successful_games > 0:
#                 average_accuracy = sum(all_accuracies) / len(all_accuracies)
#                 summary_data = {
#                     "total_games_attempted": len(all_examples_data),
#                     "successful_games": successful_games,
#                     "failed_games": failed_games,
#                     "average_accuracy_on_success": f"{average_accuracy:.2f}%",
#                     "discrepancies_by_game": all_discrepancies
#                 }
#                 summary_path = os.path.join(data_dir, "summary.json")
#                 with open(summary_path, 'w', encoding='utf-8') as f:
#                     json.dump(summary_data, f, indent=4, ensure_ascii=False)
                
#                 print(f"\n\n{'='*20} FINAL SUMMARY {'='*20}")
#                 print(f"Total Games Processed: {successful_games + failed_games}")
#                 print(f"Successful Games: {successful_games}")
#                 print(f"Failed Games: {failed_games}")
#                 print(f"Average Accuracy (on successful games): {average_accuracy:.2f}%")
#                 print(f"Full summary saved to: {summary_path}")
#             else:
#                 print(f"\nNo games were processed successfully.")

# --- Part 3: Main Execution ---
# --- handle multiple games ---

# if __name__ == "__main__":
#     load_dotenv(override=True)
#     api_key = os.getenv("GEMINI_API_KEY")
#     if not api_key:
#         print("Error: GEMINI_API_KEY is missing.")
#     else:
#         genai.configure(api_key=api_key) #type: ignore

#         data_dir = "data"
#         examples_path = os.path.join(data_dir, "examples.json")
#         true_report_path = os.path.join(data_dir, "true_report.json")

#         if not os.path.exists(examples_path) or not os.path.exists(true_report_path):
#             print("Error: Data files not found. Please run 'generate_data.py' first.")
#         else:
#             with open(examples_path, 'r', encoding='utf-8') as f:
#                 all_examples_data = json.load(f)
#             with open(true_report_path, 'r', encoding='utf-8') as f:
#                 all_true_reports_data = json.load(f)
            
#             # --- NEW: Create specific directories for text and json results ---
#             text_results_dir = os.path.join(data_dir, "llm_response_text")
#             json_results_dir = os.path.join(data_dir, "llm_response_json")
#             os.makedirs(text_results_dir, exist_ok=True)
#             os.makedirs(json_results_dir, exist_ok=True)


#             all_accuracies = []
#             all_discrepancies = {}
            
#             # Loop through each game in the dataset
#             for game_key, game_narrative_data in all_examples_data.items():
#                 print(f"\n{'='*20} PROCESSING {game_key.upper()} {'='*20}")
#                 ground_truth_data = all_true_reports_data[game_key]

#                 prompt = construct_prompt(game_narrative_data)
#                 llm_response_str = get_gemini_response(prompt)
                
#                 if llm_response_str:
#                     # --- MODIFIED: Save the raw response to the 'text' folder ---
#                     raw_output_path = os.path.join(text_results_dir, f"{game_key}.txt")
#                     with open(raw_output_path, 'w', encoding='utf-8') as f:
#                         f.write(llm_response_str)
#                     print(f"Saved raw response to: {raw_output_path}")

#                     repaired_llm_str = repair_json_output(llm_response_str)
#                     try:
#                         llm_report = json.loads(repaired_llm_str)

#                         # --- MODIFIED: Save the parsed JSON to the 'json' folder ---
#                         json_output_path = os.path.join(json_results_dir, f"{game_key}.json")
#                         with open(json_output_path, 'w', encoding='utf-8') as f:
#                             json.dump(llm_report, f, indent=4, ensure_ascii=False)
#                         print(f"Saved parsed report to: {json_output_path}")

#                         # Evaluate this specific game
#                         accuracy, discrepancies = evaluate_reports(llm_report, ground_truth_data)
#                         all_accuracies.append(accuracy)
#                         if discrepancies:
#                             all_discrepancies[game_key] = discrepancies
                        
#                         print(f"--- RESULT for {game_key}: Accuracy = {accuracy:.2f}% ---")

#                     except json.JSONDecodeError:
#                         print(f"--- ERROR for {game_key}: Could not parse JSON response. Skipping evaluation. ---")
#                         all_discrepancies[game_key] = ["Failed to parse JSON response."]

#             # Final summary after the loop
#             if all_accuracies:
#                 average_accuracy = sum(all_accuracies) / len(all_accuracies)
                
#                 # Create and save a final summary report
#                 summary_data = {
#                     "total_games_processed": len(all_accuracies),
#                     "average_accuracy": f"{average_accuracy:.2f}%",
#                     "discrepancies_by_game": all_discrepancies
#                 }
#                 summary_path = os.path.join(data_dir, "summary.json")
#                 with open(summary_path, 'w', encoding='utf-8') as f:
#                     json.dump(summary_data, f, indent=4, ensure_ascii=False)
                
#                 print(f"\n\n{'='*20} FINAL SUMMARY {'='*20}")
#                 print(f"Processed {len(all_accuracies)} games.")
#                 print(f"Average Accuracy: {average_accuracy:.2f}%")
#                 print(f"Full summary saved to: {summary_path}")
#             else:
#                 print("\nNo games were processed successfully.")

# --- Part 3: Main Execution ---
# --- one iteration ---

# if __name__ == "__main__":
#     load_dotenv(override=True)
#     api_key = os.getenv("GEMINI_API_KEY")
#     if not api_key:
#         print("Error: GEMINI_API_KEY is missing.")
#     else:
#         genai.configure(api_key=api_key)

#         data_dir = "data"
#         examples_path = os.path.join(data_dir, "examples.json")
#         true_report_path = os.path.join(data_dir, "true_report.json")

#         if not os.path.exists(examples_path) or not os.path.exists(true_report_path):
#             print("Error: Data files not found. Please run 'generate_data.py' first.")
#         else:
#             with open(examples_path, 'r', encoding='utf-8') as f:
#                 game_narrative_data = json.load(f)
#             with open(true_report_path, 'r', encoding='utf-8') as f:
#                 ground_truth_data = json.load(f)

#             prompt = construct_prompt(game_narrative_data)
#             llm_response_str = get_gemini_response(prompt)
            
#             if llm_response_str:
#                 raw_output_path = os.path.join(data_dir, "llm_response.txt")
#                 with open(raw_output_path, 'w', encoding='utf-8') as f:
#                     f.write(llm_response_str)
#                 print(f"\nSuccessfully saved LLM's raw text response to: {raw_output_path}")

#                 repaired_llm_str = repair_json_output(llm_response_str)
#                 try:
#                     llm_report = json.loads(repaired_llm_str)
#                     print("\n--- GEMINI RESPONSE (Parsed JSON) ---")
#                     print(json.dumps(llm_report, indent=2))
                    
#                     json_output_path = os.path.join(data_dir, "llm_report.json")
#                     with open(json_output_path, 'w', encoding='utf-8') as f:
#                         json.dump(llm_report, f, indent=4, ensure_ascii=False)
#                     print(f"Successfully saved valid JSON report to: {json_output_path}")

#                     # The call to the imported function
#                     accuracy, discrepancies = evaluate_reports(llm_report, ground_truth_data)
                    
#                     print("\n--- EVALUATION RESULTS ---")
#                     print(f"Overall Accuracy: {accuracy:.2f}%")
#                     if discrepancies:
#                         print(f"\nFound {len(discrepancies)} discrepancies:")
#                         for d in discrepancies:
#                             print(f"- {d}")
#                     else:
#                         print("\nNo discrepancies found. The Gemini report perfectly matches the ground truth!")

#                 except json.JSONDecodeError:
#                     print("\nError: The Gemini response was not valid JSON, even after attempting to repair it.")
#                     print("The raw response was saved to llm_response.txt for inspection.")

# --- use evaluate_reports locally ---

# # --- Part 3: Main Execution ---
# if __name__ == "__main__":
#     load_dotenv(override=True)
#     api_key = os.getenv("GEMINI_API_KEY")
#     if not api_key:
#         print("Error: GEMINI_API_KEY is missing.")
#     else:
#         genai.configure(api_key=api_key)

#         data_dir = "data"
#         examples_path = os.path.join(data_dir, "examples.json")
#         true_report_path = os.path.join(data_dir, "true_report.json")

#         if not os.path.exists(examples_path) or not os.path.exists(true_report_path):
#             print("Error: Data files not found. Please run 'generate_data.py' first.")
#         else:
#             with open(examples_path, 'r', encoding='utf-8') as f:
#                 game_narrative_data = json.load(f)
#             with open(true_report_path, 'r', encoding='utf-8') as f:
#                 ground_truth_data = json.load(f)

#             prompt = construct_prompt(game_narrative_data)
#             llm_response_str = get_gemini_response(prompt)
            
#             if llm_response_str:
#                 # --- NEW: Save the raw text output ---
#                 raw_output_path = os.path.join(data_dir, "llm_response.txt")
#                 try:
#                     with open(raw_output_path, 'w', encoding='utf-8') as f:
#                         f.write(llm_response_str)
#                     print(f"\nSuccessfully saved LLM's raw text response to: {raw_output_path}")
#                 except Exception as e:
#                     print(f"Error saving raw text response: {e}")

#                 # Use the repair function
#                 repaired_llm_str = repair_json_output(llm_response_str)

#                 try:
#                     # Attempt to parse the REPAIRED string
#                     llm_report = json.loads(repaired_llm_str)
#                     print("\n--- GEMINI RESPONSE (Parsed JSON) ---")
#                     print(json.dumps(llm_report, indent=2))
#                     print("-" * 50)

#                     # --- NEW: Save the valid parsed JSON output ---
#                     json_output_path = os.path.join(data_dir, "llm_report.json")
#                     try:
#                         with open(json_output_path, 'w', encoding='utf-8') as f:
#                             json.dump(llm_report, f, indent=4, ensure_ascii=False)
#                         print(f"Successfully saved valid JSON report to: {json_output_path}")
#                     except Exception as e:
#                         print(f"Error saving JSON report: {e}")


#                     # Evaluate the parsed report
#                     accuracy, discrepancies = evaluate_reports(llm_report, ground_truth_data)
                    
#                     print("\n--- EVALUATION RESULTS ---")
#                     print(f"Overall Accuracy: {accuracy:.2f}%")
#                     if discrepancies:
#                         print(f"\nFound {len(discrepancies)} discrepancies:")
#                         for d in discrepancies:
#                             print(f"- {d}")
#                     else:
#                         print("\nNo discrepancies found. The Gemini report perfectly matches the ground truth!")

#                 except json.JSONDecodeError:
#                     print("\nError: The Gemini response was not valid JSON, even after attempting to repair it.")
#                     print("The raw response was saved to llm_response.txt for inspection.")

# --- evaluation only ---

# if __name__ == "__main__":
#     load_dotenv(override=True)
#     api_key = os.getenv("GEMINI_API_KEY")
#     if not api_key:
#         print("Error: GEMINI_API_KEY is missing.")
#     else:
#         genai.configure(api_key=api_key)

#         data_dir = "data"
#         examples_path = os.path.join(data_dir, "examples.json")
#         true_report_path = os.path.join(data_dir, "true_report.json")
        
#         # --- NEW: Define the path for the saved LLM response ---
#         llm_response_path = os.path.join(data_dir, "llm_response.txt")

#         if not os.path.exists(llm_response_path) or not os.path.exists(true_report_path):
#             print(f"Error: Required files not found.")
#             print("Please ensure 'true_report.json' and 'llm_response.txt' exist in the 'data' directory.")
#         else:
#             with open(true_report_path, 'r', encoding='utf-8') as f:
#                 ground_truth_data = json.load(f)

#             # --- MODIFIED: Read from file instead of calling the API ---
#             print(f"--- TESTING MODE: Reading LLM response from {llm_response_path} ---")
#             with open(llm_response_path, 'r', encoding='utf-8') as f:
#                 llm_response_str = f.read()

#             # The original API call is commented out for testing
#             # prompt = construct_prompt(game_narrative_data)
#             # llm_response_str = get_gemini_response(prompt)
            
#             if llm_response_str:
#                 # Use the repair function on the loaded text
#                 repaired_llm_str = repair_json_output(llm_response_str)

#                 try:
#                     # Attempt to parse the REPAIRED string
#                     llm_report = json.loads(repaired_llm_str)
#                     print("\n--- LLM RESPONSE (Parsed JSON) ---")
#                     print(json.dumps(llm_report, indent=2))
#                     print("-" * 50)
                    
#                     # (Optional) You can still save the parsed JSON if you want
#                     # json_output_path = os.path.join(data_dir, "llm_report.json")
#                     # with open(json_output_path, 'w', encoding='utf-8') as f:
#                     #     json.dump(llm_report, f, indent=4, ensure_ascii=False)

#                     # Evaluate the parsed report
#                     accuracy, discrepancies = evaluate_reports(llm_report, ground_truth_data)
                    
#                     print("\n--- EVALUATION RESULTS ---")
#                     print(f"Overall Accuracy: {accuracy:.2f}%")
#                     if discrepancies:
#                         print(f"\nFound {len(discrepancies)} discrepancies:")
#                         for d in discrepancies:
#                             print(f"- {d}")
#                     else:
#                         print("\nNo discrepancies found. The Gemini report perfectly matches the ground truth!")

#                 except json.JSONDecodeError:
#                     print("\nError: The Gemini response was not valid JSON, even after attempting to repair it.")
#                     print("Original LLM Response Text:", llm_response_str)