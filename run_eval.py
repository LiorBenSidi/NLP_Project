# run_eval.py
# TODO: Implement the evaluation logic according to "generated_data.py"


import json
import re

# --- Part 1: Prompt Templates and Static Data ---
# These are the static parts of our API request, defined for clarity.
SYSTEM_INSTRUCTIONS_PROMPT = """You are an automated sports data analyst. Your sole function is to process a narrative log of a basketball game and convert it into a structured JSON report.

                                ### YOUR TASK ###
                                Analyze the provided game log, which lists events in chronological order.
                                Track all relevant statistics for each player and team.
                                Synthesize this information into a single, complete JSON object that represents the final box score of the game.

                                ### OUTPUT FORMAT ###
                                - Your entire response MUST be a single, valid JSON object.
                                - Your response MUST NOT include any introductory text, explanations, or conversational markdown (like ```json ...```).
                                - Your response MUST begin with the character `{` and end with the character `}`.

                                ### REQUIRED STATS ###
                                For each player, you must track and include the following statistics:
                                - `points`: Total points scored.
                                - `assists`: Total assists made.
                                - `fouls`: Total fouls committed.
                                - `steals`: Total steals made.
                                - `blocks`: Total blocks made.
                                - `ft_made`: Total free throws successfully made.
                                - `ft_attempted`: Total free throws attempted.
                                - `ft_percentage`: The calculated free throw percentage.

                                ### CALCULATION RULES ###
                                - Calculate `ft_percentage` as `ft_made` / `ft_attempted`.
                                - If a player's `ft_attempted` is 0, their `ft_percentage` must be `0.0`.
                                - The `total_score` for each team must be the sum of the `points` of all players on that team.

                                ### EXAMPLE JSON STRUCTURE ###
                                Your final output must follow this exact structure. Do not add, remove, or rename any keys.

                                ```json
                                {
                                "TeamNameA": {
                                    "total_score": ...,
                                    "leading_scorer": "PlayerName1-A",
                                    "Total points": ...,
                                    "Total assists": ...,
                                    "Total fouls": ...,
                                    "Total steals": ...,
                                    "Total blocks": ...,
                                    "Total turnovers": ...,
                                    "players": {
                                    "PlayerName1-A": {
                                        "points": ...,
                                        "assists": ...,
                                        "fouls": ...,
                                        "steals": ...,
                                        "blocks": ...,
                                        "turnovers": ...,
                                        "ft_percentage": ...
                                        "2pt_field_goals": ...,
                                        "3pt_field_goals": ...,
                                    },
                                    "PlayerName2-A": {
                                        ...
                                    }
                                    }
                                },
                                "TeamNameB": {
                                    ...
                                }
                                }

                                I will provide the game log in my next message. Acknowledge that you understand these instructions.
                            """
MODEL_ACKNOWLEDGEMENT = "Understood. I am ready to process the game log. I will adhere to all instructions and provide the final report as a single, valid JSON object."

# --- Part 2: Core Functions ---
def construct_api_request(narrative, team_a, team_b):
    """
    Constructs the full JSON payload for the Gemini API.
    Args:
        narrative (str): The events log text to include in the API request.
        team_a (tuple): A tuple containing the name and player list for Team A.
        team_b (tuple): A tuple containing the name and player list for Team B.
    Returns:
        dict: The JSON payload for the API request.
    """
    game_log_text = (f"### GAME LOG TO ANALYZE ###\n\n"
                 f"Here is the event log for a basketball game between the **{team_a[0]}** and the **{team_b[0]}**:\n"
                 f"Team A Players: {team_a[1]}\n"
                 f"Team B Players: {team_b[1]}\n\n"
                 f"{narrative}")
    request_body = {
        "contents": [
            {"role": "user", "parts": [{"text": SYSTEM_INSTRUCTIONS_PROMPT}]},
            {"role": "model", "parts": [{"text": MODEL_ACKNOWLEDGEMENT}]},
            {"role": "user", "parts": [{"text": game_log_text}]}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1024
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
        ]
    }
    return request_body