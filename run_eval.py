# run_eval.py

#TODO:
# 2. Think about compare the JSON output format with LISTs output format.
# 3. I have notied that the LLM tend to interpret regular passing events as assists, even when they shouldn't be.
# 4. I have also noticed that the LLM sometimes fails to recognize when a player is attempting a shot.

import json
import re
import os
import litellm
import time
from evaluation import evaluate_reports
from dotenv import load_dotenv
load_dotenv(override=True)

# Support computing multiple evaluation types in the same run
EVAL_TYPES = ["field", "fractional_per_block"]

# --- Define the model you want to test here ---
# This is the only line you need to change to switch models.

# --- Gemini ---
#MODEL_TO_TEST = "gemini/gemini-1.5-flash"
#MODEL_TO_TEST = "gemini/gemini-1.5-pro"
#MODEL_TO_TEST = "gemini/gemini-2.0-flash-lite"
#MODEL_TO_TEST = "gemini/gemini-2.0-flash"
#MODEL_TO_TEST = "gemini/gemini-2.5-flash-lite"
#MODEL_TO_TEST = "gemini/gemini-2.5-flash"
MODEL_TO_TEST = "gemini/gemini-2.5-pro"

# --- OpenAI --- already paid 10$
#MODEL_TO_TEST = "gpt-4o-nano"
#MODEL_TO_TEST = "gpt-4o-mini"
#MODEL_TO_TEST = "gpt-4o"
#MODEL_TO_TEST = "gpt-5-mini"
#MODEL_TO_TEST = "gpt-5"

# --- Anthropic --- need to pay!
#MODEL_TO_TEST = "claude-3-haiku-20240307"
#MODEL_TO_TEST = "claude-opus-4-20250514"
#MODEL_TO_TEST = "claude-sonnet-4-20250514"

# --- DeepSeek --- need to pay!
#MODEL_TO_TEST = "deepseek/deepseek-chat"
#MODEL_TO_TEST = "deepseek/deepseek-coder"

# --- Grok ---
#MODEL_TO_TEST = ""

# --- Meta ---
#MODEL_TO_TEST = ""

# --- Part 1: Prompt Templates and Static Data ---
SYSTEM_INSTRUCTIONS_PROMPT = """You are an automated sports data analyst.
You have just received a chronological log of events from a basketball game.
Based only on what actually happened in the log, your role is to build the official statistical report for the game.

### YOUR TASK ###
- Read through the sequence of events in order, as if you are watching the game unfold.
- From those events, determine the stats for both teams and all their players.
- You will also have the full rosters for each team, including head coaches and starting lineups and bench players.
- Make sure every team and every player is included in the final report, even if some have zero stats.
- Combine everything into one complete JSON object that represents the final box score.

### REQUIRED STATS ###
For each team, you must track and include the following:
- `matchup`: The matchup of the game in the format "<TeamNameA> vs <TeamNameB>"
- `final_score`: The final score of the game in the format "<TeamNameA>: <ScoreA>, <TeamNameB>: <ScoreB>"
- `teams`: The two teams participating in the game, including their coaches, rosters and starting lineups and bench players.
- `final_stats`: A dictionary containing the stats for each team and their players.

### OUTPUT FORMAT ###
- Your entire response MUST be a single, valid JSON object.
- Your response MUST NOT include any introductory text, explanations, or conversational markdown (like ```json ...```).
- Your response MUST begin with the character `{` and end with the character `}`.
"""

# FULL - Add example for the required output
SYSTEM_INSTRUCTIONS_PROMPT += """\n\n### EXAMPLE FOR THE REQUIRED JSON STRUCTURE ###
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
                "score": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0
            },
            "players": {
                "PlayerName1-A": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName2-A": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName3-A": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName4-A": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName5-A": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName6-A": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName7-A": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName8-A": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName9-A": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName10-A": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                }
            }
        },
        "TeamNameB": {
            "stats": {
                "score": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0
            },
            "players": {
                "PlayerName1-B": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName2-B": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName3-B": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName4-B": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName5-B": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName6-B": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName7-B": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName8-B": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName9-B": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                },
                "PlayerName10-B": {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0, "2pt_shots_made": 0, "2pt_shots_attempted": 0, "3pt_shots_made": 0, "3pt_shots_attempted": 0, "ft_made": 0, "ft_attempted": 0
                }
            }
        }
    }
}
```
"""

# # SHORTENED (DONT WORK) - Add example for the required output
# SYSTEM_INSTRUCTIONS_PROMPT += """\n\n### EXAMPLE FOR THE REQUIRED JSON STRUCTURE ###
#                                     Your final output must follow this **exact JSON structure**. 
#                                     Do not add, remove, or rename any keys. 
#                                     Do not wrap it in code fences or extra text. 
#                                     Return only one valid JSON object.

#                                     EXAMPLE JSON STRUCTURE (values here are placeholders, the model must calculate real ones):

#                                     {
#                                         "matchup": "TeamNameA vs TeamNameB",
#                                         "final_score": "TeamNameA: 0, TeamNameB: 0",
#                                         "teams": {
#                                             "TeamNameA": {
#                                                 "coach": "CoachNameA",
#                                                 "roster": ["PlayerName1-A", "PlayerName2-A", "PlayerName3-A", "PlayerName4-A", "PlayerName5-A"],
#                                                 "starting_lineup": ["PlayerName1-A", "PlayerName2-A", "PlayerName3-A", "PlayerName4-A", "PlayerName5-A"],
#                                                 "bench": ["PlayerName6-A", "PlayerName7-A", "PlayerName8-A", "PlayerName9-A", "PlayerName10-A"]
#                                             },
#                                             "TeamNameB": {
#                                                 "coach": "CoachNameB",
#                                                 "roster": ["PlayerName1-B", "PlayerName2-B", "PlayerName3-B", "PlayerName4-B", "PlayerName5-B"],
#                                                 "starting_lineup": ["PlayerName1-B", "PlayerName2-B", "PlayerName3-B", "PlayerName4-B", "PlayerName5-B"],
#                                                 "bench": ["PlayerName6-B", "PlayerName7-B", "PlayerName8-B", "PlayerName9-B", "PlayerName10-B"]
#                                             }
#                                         },
#                                         "final_stats": {
#                                             "TeamNameA": {
#                                                 "stats": {
#                                                     "score": 0,
#                                                     "assists": 0,
#                                                     "rebounds": 0,
#                                                     "fouls": 0,
#                                                     "steals": 0,
#                                                     "blocks": 0,
#                                                     "turnovers": 0
#                                                 },
#                                                 "players": {
#                                                     "PlayerName1-A": {
#                                                         "points": 0,
#                                                         "assists": 0,
#                                                         "rebounds": 0,
#                                                         "fouls": 0,
#                                                         "steals": 0,
#                                                         "blocks": 0,
#                                                         "turnovers": 0,
#                                                         "2pt_shots_made": 0,
#                                                         "2pt_shots_attempted": 0,
#                                                         "3pt_shots_made": 0,
#                                                         "3pt_shots_attempted": 0,
#                                                         "ft_made": 0,
#                                                         "ft_attempted": 0
#                                                     }
#                                                     // ... repeat for all 10 players
#                                                 }
#                                             },
#                                             "TeamNameB": {
#                                                 "stats": {
#                                                     "score": 0,
#                                                     "assists": 0,
#                                                     "rebounds": 0,
#                                                     "fouls": 0,
#                                                     "steals": 0,
#                                                     "blocks": 0,
#                                                     "turnovers": 0
#                                                 },
#                                                 "players": {
#                                                     "PlayerName1-B": {
#                                                         "points": 0,
#                                                         "assists": 0,
#                                                         "rebounds": 0,
#                                                         "fouls": 0,
#                                                         "steals": 0,
#                                                         "blocks": 0,
#                                                         "turnovers": 0,
#                                                         "2pt_shots_made": 0,
#                                                         "2pt_shots_attempted": 0,
#                                                         "3pt_shots_made": 0,
#                                                         "3pt_shots_attempted": 0,
#                                                         "ft_made": 0,
#                                                         "ft_attempted": 0
#                                                     }
#                                                     // ... repeat for all 10 players
#                                                 }
#                                             }
#                                         }
#                                     }
#                                     """

# Add strict JSON reminder
SYSTEM_INSTRUCTIONS_PROMPT += "\n\nSTRICT: Output only a single valid JSON object. No prose, no code fences, no comments, no trailing commas."

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

def get_litellm_response(model_name, messages):
    """Calls any LLM using the LiteLLM library and returns the response content."""
    try:
        print(f"\nSending request to model: {model_name} via LiteLLM...")

        # --- Call the LiteLLM API ---
        response = litellm.completion(
            model=model_name,
            messages=messages,
            tools=None,  # No tools needed for this task
            response_format={"type": "json_object"},
            # Only Gemini needs this extra body param
            extra_body={"response_mime_type": "application/json"} if model_name.startswith("gemini") else {}
        )

        print("Response received.")
        return response.choices[0].message.content # type: ignore

    except Exception as e:
        print(f"An unexpected error occurred during LiteLLM API call: {e}")
        return None

# --- Structure-safe JSON repair utilities ---
_MD_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

def _strip_noise(s: str) -> str:
    s = s.strip()
    s = _MD_FENCE_RE.sub("", s)
    # Remove BOM/control chars except whitespace
    s = s.encode("utf-8", "ignore").decode("utf-8", "ignore")
    s = "".join(ch for ch in s if ch in ("\t", "\n", "\r") or ch >= " ")
    # Normalize curly quotes/backticks → standard
    s = s.replace("“", '"').replace("”", '"').replace("‟", '"').replace("`", '"').replace("’", "'").replace("‚", "'")
    return s

def _remove_jsonc_comments(s: str) -> str:
    s = _LINE_COMMENT_RE.sub("", s)
    s = _BLOCK_COMMENT_RE.sub("", s)
    return s

def _remove_trailing_commas(s: str) -> str:
    # remove ", ]" and ", }"
    return re.sub(r",(\s*[\}\]])", r"\1", s)

def repair_json_structure(raw: str) -> str:
    """
    Structure-safe repair:
    - strip fences / noise / comments / trailing commas
    - walk chars, ignore braces inside strings
    - drop unexpected closers
    - append missing closers in correct order
    """
    s = _strip_noise(raw)
    s = _remove_jsonc_comments(s)
    s = _remove_trailing_commas(s)

    result = []
    stack = []  # holds expected closers: '}' or ']'
    in_str = False
    esc = False

    for ch in s:
        result.append(ch)
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in "}]":
                if stack and stack[-1] == ch:
                    stack.pop()
                else:
                    # unexpected closer → drop it
                    result.pop()

    # close any missing scopes
    while stack:
        result.append(stack.pop())

    fixed = "".join(result)
    fixed = _remove_trailing_commas(fixed)
    return fixed

# --- model-only JSON fixer ---
def ask_model_to_fix_json(model_name: str, raw: str) -> str | None:
    messages = [
        {"role": "system", "content": "You are a formatter. Return only a single valid JSON object. No code fences. No comments. No extra text."},
        {"role": "user", "content": raw},
    ]
    try:
        # --- Call the LiteLLM API ---
        response = litellm.completion(
            model=model_name,
            messages=messages,
            tools=None,  # No tools needed for this task
            response_format={"type": "json_object"},
            # Only Gemini needs this extra body param
            extra_body={"response_mime_type": "application/json"} if model_name.startswith("gemini") else {}
        )
            
        print("Response received (for fixing JSON).")
        return response.choices[0].message.content  # type: ignore

    except Exception as e:
        print(f"An unexpected error occurred during LiteLLM API call (for fixing JSON): {e}")
        return None

# --- Type coercion after rebuild ---
def coerce_numbers_inplace(report: dict, template: dict):
    def walk(rv, tv):
        if isinstance(tv, dict):
            out = {}
            if not isinstance(rv, dict):
                rv = {}
            for k, tvv in tv.items():
                out[k] = walk(rv.get(k), tvv)
            return out
        elif isinstance(tv, list):
            return rv if isinstance(rv, list) else []
        elif isinstance(tv, (int, float)):
            try:
                return int(rv)
            except Exception:
                return 0
        elif isinstance(tv, str):
            return "" if rv is None else str(rv)
        else:
            return rv if rv is not None else 0
    return walk(report, template)

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

        # --- CRITICAL: Skip the 'participants' and 'difficulty' keys ---
        # This is evaluation metadata and should NOT be in the LLM's final report.
        if key in ["participants", "difficulty"]:
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

if __name__ == "__main__":
    
    data_dir = "data"
    jsonl_path = os.path.join(data_dir, "examples.jsonl")

    if not os.path.exists(jsonl_path):
        print("Error: JSONL file not found.")
    else:
        all_examples_data = {}
        all_true_reports_data = {}

        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    print("Skipping malformed JSONL line.")
                    continue

                game_id = obj.get("game_id")
                typ = obj.get("type")
                data = obj.get("data", {})

                if not game_id or not typ:
                    continue

                if typ == "example":
                    all_examples_data[game_id] = data
                elif typ == "true_report":
                    all_true_reports_data[game_id] = data

        # Optional sanity check
        missing_in_examples = set(all_true_reports_data.keys()) - set(all_examples_data.keys())
        missing_in_truth = set(all_examples_data.keys()) - set(all_true_reports_data.keys())
        if missing_in_examples or missing_in_truth:
            print(f"WARNING: mismatched game_ids. "
                f"Missing in examples: {sorted(missing_in_examples)}; "
                f"missing in true_report: {sorted(missing_in_truth)}")

    # data_dir = "data"
    # examples_path = os.path.join(data_dir, "examples.json")
    # true_report_path = os.path.join(data_dir, "true_report.json")

    # if not os.path.exists(examples_path) or not os.path.exists(true_report_path):
    #     print("Error: Data files not found.")
    # else:
    #     with open(examples_path, 'r', encoding='utf-8') as f:
    #         all_examples_data = json.load(f)
    #     with open(true_report_path, 'r', encoding='utf-8') as f:
    #         all_true_reports_data = json.load(f)
        
        results_base_dir = os.path.join(data_dir, "llm_responses")
        for difficulty_level in ["basic", "medium", "hard"]:
            os.makedirs(os.path.join(results_base_dir, difficulty_level, "text"), exist_ok=True)
            os.makedirs(os.path.join(results_base_dir, difficulty_level, "json"), exist_ok=True)

        # results_by_difficulty stores per-difficulty, per-eval-type accuracies and discrepancies
        results_by_difficulty = {}
        for lvl in ["basic", "medium", "hard"]:
            results_by_difficulty[lvl] = {
                "accuracies": {et: [] for et in EVAL_TYPES},
                "discrepancies": {et: {} for et in EVAL_TYPES}
            }
        total_successful_games, total_failed_games = 0, 0
        
        for game_key, game_narrative_data in all_examples_data.items():
            print(f"\n{'='*20} PROCESSING {game_key.upper()} {'='*20}")
            ground_truth_data = all_true_reports_data[game_key]
            difficulty = ground_truth_data.get("difficulty", "unknown")

            max_retries = 2
            llm_report = None
            raw_response_str = None
            
            for attempt in range(max_retries):
                messages = construct_litellm_messages(game_narrative_data)
                raw_response_str = get_litellm_response(MODEL_TO_TEST, messages)
                time.sleep(15) # Proactively avoid rate limiting
                
                if not raw_response_str:
                    print(f"--- ERROR on attempt {attempt + 1}: No response from API. Retrying... ---")
                    continue

                # Stage 1: structure-safe repair
                repaired_syntax_str = repair_json_structure(raw_response_str)

                # Try to parse
                parsed = None
                try:
                    parsed = json.loads(repaired_syntax_str)
                except json.JSONDecodeError:
                    # Last resort: ask model to fix JSON only
                    fixed_by_model = ask_model_to_fix_json(MODEL_TO_TEST, raw_response_str)
                    time.sleep(60) # Proactively avoid rate limiting

                    if fixed_by_model:
                        try:
                            parsed = json.loads(fixed_by_model)
                        except json.JSONDecodeError:
                            parsed = None

                if not parsed:
                    print(f"--- ERROR on attempt {attempt + 1}: Could not parse JSON after repair + fixer. Retrying... ---")
                    continue
                    
                # Stage 2: Rebuild the dictionary to ensure perfect structure
                rebuilt_report = repair_and_rebuild_json(parsed, ground_truth_data)

                # Stage 3: coerce types (recommended)
                rebuilt_report = coerce_numbers_inplace(rebuilt_report, ground_truth_data)

                if not is_report_all_zeros(rebuilt_report):
                    print(f"--- SUCCESS on attempt {attempt + 1}: LLM response parsed and rebuilt successfully. ---")
                    llm_report = rebuilt_report
                    break
                else:
                    print(f"--- WARNING on attempt {attempt + 1}: All-zeros report. Retrying... ---")
            
            # This code now runs for both successful and failed games.
            raw_output_path = os.path.join(results_base_dir, difficulty, "text", f"{game_key}.txt")
            with open(raw_output_path, 'w', encoding='utf-8') as f:
                f.write(raw_response_str or "")
            print(f"Saved original raw response to: {raw_output_path}")

            # --- Process, save, and evaluate the final, rebuilt report ---
            if llm_report:
                total_successful_games += 1
                json_output_path = os.path.join(results_base_dir, difficulty, "json", f"{game_key}.json")
                with open(json_output_path, 'w', encoding='utf-8') as f:
                    json.dump(llm_report, f, indent=4, ensure_ascii=False)
                print(f"Saved rebuilt report to: {json_output_path}")

                # compute all evaluation types and store per-type results
                per_type_results = {}
                for et in EVAL_TYPES:
                    acc, disc = evaluate_reports(llm_report, ground_truth_data, eval_type=et)
                    per_type_results[et] = (acc, disc)
                    if difficulty in results_by_difficulty:
                        results_by_difficulty[difficulty]["accuracies"][et].append(acc)
                        if disc:
                            results_by_difficulty[difficulty]["discrepancies"][et][game_key] = disc

                for et, (acc, disc) in per_type_results.items():
                    print(f"--- RESULT for {game_key} ({et}): Accuracy = {acc:.2f}% ---")
            else:
                total_failed_games += 1
                print(f"--- FAILURE for {game_key}: Could not get a valid report after {max_retries} attempts. SKIPPING. ---")
                if difficulty in results_by_difficulty:
                        results_by_difficulty[difficulty]["discrepancies"][game_key] = [f"Failed after {max_retries} retries. See raw text file for details."]

            # --- Final Summary ---
            print(f"\n\n{'='*20} FINAL SUMMARY {'='*20}")
            
            final_summary = {
                "total_games_attempted": len(all_examples_data),
                "successful_games": total_successful_games,
                "failed_games": total_failed_games,
                "overall_average_accuracy": "N/A",
                "evaluation_type": EVAL_TYPES,
                "results_by_difficulty": {}
            }

            print(f"Total Games Attempted: {total_successful_games + total_failed_games}")
            print(f"Successful Games: {total_successful_games}")
            print(f"Failed Games: {total_failed_games}")
            
            all_successful_accuracies = {et: [] for et in EVAL_TYPES}
            for difficulty, results in results_by_difficulty.items():
                per_type_summary = {}
                print(f"\n--- Difficulty: {difficulty.upper()} ---")
                for et in EVAL_TYPES:
                    acc_list = results["accuracies"].get(et, [])
                    num_games_succeeded = len(acc_list)
                    avg_acc = (sum(acc_list) / num_games_succeeded) if num_games_succeeded > 0 else 0.0
                    per_type_summary[et] = {
                        "average_accuracy": f"{avg_acc:.2f}%",
                        "games_succeeded": num_games_succeeded,
                        "discrepancies": results["discrepancies"].get(et, {})
                    }
                    all_successful_accuracies[et].extend(acc_list)
                    print(f"  [{et}] Games Succeeded: {num_games_succeeded}  Average: {avg_acc:.2f}%")

                final_summary["results_by_difficulty"][difficulty] = per_type_summary
            
            # Calculate and print the overall average accuracy
            # overall averages per evaluation type
            overall_avgs = {}
            for et in EVAL_TYPES:
                lst = all_successful_accuracies.get(et, [])
                if lst:
                    overall_avgs[et] = f"{(sum(lst)/len(lst)):.2f}%"
                    print(f"\nOVERALL AVERAGE ACCURACY ({et}) (on {len(lst)} successful games): {overall_avgs[et]}")
                else:
                    overall_avgs[et] = "N/A"

            final_summary["overall_average_accuracy"] = overall_avgs

            summary_path = os.path.join(data_dir, "summary.json")
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(final_summary, f, indent=4, ensure_ascii=False)
            print(f"\nFull summary saved to: {summary_path}")