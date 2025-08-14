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
import litellm
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
                                - **"The game starts with a jump ball between {player_A} and {player_B}. {winner} wins possession."**:
                                  - Do nothing
                                - **"The final buzzer sounds. End of game."**:
                                  - Do nothing
                                - **"{player_A1} inbounds the ball to {player_A2} to start the possession."**
                                  - Do nothing
                                - **"{player_A1} passes to {player_A2}."**
                                  - Do nothing
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
                                - `difficulty`: The difficulty level of the game, which can be "basic", "medium", or "hard".
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
                                    "difficulty": "basic",
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

def construct_litellm_messages(game_data):
    """Constructs the 'messages' list required by the litellm.completion API."""
    team_a_name, team_b_name = list(game_data["teams"].keys())
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
    
    # The user's final prompt combines all context
    user_prompt = roster_info + "\n### GAME LOG ###\n" + narrative_log
    
    # LiteLLM uses the standard OpenAI messages format ("system", "user")
    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTIONS_PROMPT},
        {"role": "user", "content": user_prompt}
    ]
    return messages

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

def get_litellm_response(model_name, messages, api_keys):
    """Calls any LLM using the LiteLLM library and returns the response content."""
    try:
        print(f"\nSending request to model: {model_name} via LiteLLM...")
        # --- Determine the correct API key to use ---
        provider = model_name.split('/')[0] # e.g., "gemini/..." -> "gemini"
        api_key = api_keys.get(provider)
        if not api_key:
            raise ValueError(f"API key for provider '{provider}' not found in .env file.")
        # --- Call the LiteLLM API ---
        response = litellm.completion(
            model=model_name,
            messages=messages,
            temperature=0.0,
            max_tokens=8192,
            response_format={"type": "json_object"},
            api_key=api_key # Pass the specific key
        )
        print("Response received.")
        return response.choices[0].message.content #type: ignore
    except Exception as e:
        print(f"An unexpected error occurred during LiteLLM API call: {e}")
        return None
    
def repair_and_rebuild_json(llm_dict, ground_truth_template):
    """
    Intelligently rebuilds a dictionary from the LLM to match the exact structure
    of a ground_truth_template.

    This version specifically handles the case where the LLM incorrectly nests
    one team object inside another.
    """
    # Create a new, clean dictionary to return
    rebuilt_dict = {}

    # Iterate through the keys of the PERFECT template to define the structure
    for key, gt_value in ground_truth_template.items():

        # --- CRITICAL: Skip the 'participants' key ---
        # This is evaluation metadata and should NOT be in the LLM's final report.
        if key == "participants":
            continue

        if key == "final_stats":
            rebuilt_dict[key] = {}
            llm_stats_block = llm_dict.get("final_stats", {})
            gt_stats_block = ground_truth_template.get("final_stats", {})

            for team_name, gt_team_data in gt_stats_block.items():
                llm_team_data = None
                
                # Step A: Look for the team in the correct place
                if team_name in llm_stats_block and isinstance(llm_stats_block[team_name], dict):
                    llm_team_data = llm_stats_block[team_name]
                else:
                    # Step B: If not found, search for it nested inside OTHER teams
                    print(f"Repair Warning: Team '{team_name}' not found at top level. Searching for nested team...")
                    for other_team_name, other_team_data in llm_stats_block.items():
                        if isinstance(other_team_data, dict) and team_name in other_team_data:
                            llm_team_data = other_team_data[team_name]
                            print(f"Found and corrected nested '{team_name}' inside '{other_team_name}'.")
                            break
                
                # Step C: Rebuild the team data using the found data (or an empty dict if not found)
                # This re-uses the original recursive logic, but scoped to just one team
                rebuilt_dict[key][team_name] = repair_and_rebuild_json(llm_team_data or {}, gt_team_data)

        # --- Original recursive logic for all other keys ---
        elif key in llm_dict:
            llm_value = llm_dict[key]
            if isinstance(gt_value, dict) and isinstance(llm_value, dict):
                rebuilt_dict[key] = repair_and_rebuild_json(llm_value, gt_value)
            else:
                rebuilt_dict[key] = llm_value
        else:
            # Handle other missing keys with neutral defaults
            if isinstance(gt_value, dict): rebuilt_dict[key] = {}
            elif isinstance(gt_value, list): rebuilt_dict[key] = []
            elif isinstance(gt_value, str): rebuilt_dict[key] = ""
            else: rebuilt_dict[key] = 0
            
    return rebuilt_dict

def repair_json_syntax(json_string):
    """Performs a basic syntax repair on a raw string to make it parsable."""
    repaired = json_string.strip().strip("```json").strip("```").strip()
    open_braces = repaired.count('{')
    close_braces = repaired.count('}')
    if repaired.startswith('{') and open_braces > close_braces:
        repaired += '}' * (open_braces - close_braces)
    return repaired

if __name__ == "__main__":
    load_dotenv(override=True)
    # --- Load all potential API keys into a dictionary ---
    api_keys = {
        "gemini": os.getenv("GEMINI_API_KEY"),
        "openai": os.getenv("OPENAI_API_KEY"),
        "anthropic": os.getenv("ANTHROPIC_API_KEY"),
        # Add keys for other providers here if needed
    }
    
    # --- NEW: Define the model you want to test here ---
    # This is the only line you need to change to switch models!
    #MODEL_TO_TEST = "gemini/gemini-1.5-flash-latest"
    MODEL_TO_TEST = "gemini/gemini-1.5-pro-latest"
    #MODEL_TO_TEST = "gemini/gemini-1.5-flash"
    #MODEL_TO_TEST = "gemini/gemini-2.5-pro"
    #MODEL_TO_TEST = "gpt-4o"
    #MODEL_TO_TEST = "claude-3-haiku-20240307"

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
            os.makedirs(os.path.join(results_base_dir, difficulty_level, "text"), exist_ok=True)
            os.makedirs(os.path.join(results_base_dir, difficulty_level, "json"), exist_ok=True)

        results_by_difficulty = { "basic": {"accuracies": [], "discrepancies": {}}, "medium": {"accuracies": [], "discrepancies": {}}, "hard": {"accuracies": [], "discrepancies": {}}}
        total_successful_games, total_failed_games = 0, 0
        
        for game_key, game_narrative_data in all_examples_data.items():
            print(f"\n{'='*20} PROCESSING {game_key.upper()} {'='*20}")
            ground_truth_data = all_true_reports_data[game_key]
            difficulty = ground_truth_data.get("difficulty", "unknown")

            max_retries = 2
            llm_report = None
            
            for attempt in range(max_retries):
                messages = construct_litellm_messages(game_narrative_data)
                raw_response_str = get_litellm_response(MODEL_TO_TEST, messages, api_keys)
                
                if not raw_response_str:
                    print(f"--- ERROR on attempt {attempt + 1}: No response from API. Retrying... ---")
                    continue

                # Stage 1: Fix basic syntax of the raw string
                repaired_syntax_str = repair_json_syntax(raw_response_str)
                
                try:
                    # Attempt to parse the syntactically corrected string
                    llm_dict_candidate = json.loads(repaired_syntax_str)
                    
                    # Stage 2: Rebuild the dictionary to ensure perfect structure
                    rebuilt_report = repair_and_rebuild_json(llm_dict_candidate, ground_truth_data)

                    if not is_report_all_zeros(rebuilt_report):
                        print(f"--- SUCCESS on attempt {attempt + 1}: LLM response parsed and rebuilt successfully. ---")
                        llm_report = rebuilt_report
                        break
                    else:
                        print(f"--- WARNING on attempt {attempt + 1}: All-zeros report. Retrying... ---")
                except json.JSONDecodeError:
                    print(f"--- ERROR on attempt {attempt + 1}: Could not parse JSON even after syntax repair. Retrying... ---")
            
            # --- Process, save, and evaluate the final, rebuilt report ---
            if llm_report:
                total_successful_games += 1
                json_output_path = os.path.join(results_base_dir, difficulty, "json", f"{game_key}.json")
                with open(json_output_path, 'w', encoding='utf-8') as f:
                    json.dump(llm_report, f, indent=4, ensure_ascii=False)
                print(f"Saved rebuilt report to: {json_output_path}")

                raw_output_path = os.path.join(results_base_dir, difficulty, "text", f"{game_key}.txt")
                with open(raw_output_path, 'w', encoding='utf-8') as f:
                    f.write(raw_response_str) #type: ignore
                print(f"Saved original raw response to: {raw_output_path}")

                accuracy, discrepancies = evaluate_reports(llm_report, ground_truth_data)
                
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