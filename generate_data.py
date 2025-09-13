"""
generate_data.py
================

Purpose
-------
Simulate a basketball game and produce two kinds of data:

1) Model input (play-by-play + team metadata without "participants") — saved to
   `data/examples.json` and `data/examples.jsonl`.

2) Ground-truth report with final box scores, full rosters, and "participants" (Optioanl)
   — saved to `data/true_report.json` and `data/examples.jsonl`.

The script generates games across difficulty levels ("basic", "medium", "hard"),
randomizes in-game events, updates team/player statistics, and returns fully structured JSONL.
At the end of a run it writes:
- `data/examples.json` and `data/true_report.json` (Optioanl)
- `data/examples.jsonl` — line-delimited: an {"type":"example"} row followed by an {"type":"true_report"} row for the same game_id (this layout is convenient for training/evaluation).

Game example schema
-------------------
{
  "matchup": "<TeamA> vs <TeamB>",
  "teams": {
    "<TeamA>": {
      "coach": "...",
      "roster": [12 names],
      "starting_lineup": [5 names],
      "bench": [7 names],
    },
    "<TeamB>": { ... }
  },
  "play_by_play": [
    {"event_id": "..." , "description": "..."},
    ... assorted plays (passes, shots, fouls, VAR, rebounds, substitutions) ...
  ],
}

Game true report schema
-----------------------
{
  "matchup": "<TeamA> vs <TeamB>",
  "difficulty": "...",
  "final_score": "<TeamA>: ..., <TeamB>: ...",
  "teams": {
    "<TeamA>": {
      "coach": "...",
      "roster": [12 names],
      "starting_lineup": [5 names],
      "bench": [7 names],
      "participants": [players who actually played]
    },
    "<TeamB>": { ... }
  },
  "final_stats": {
    "<TeamA>": {
      "stats": { "points": ..., "assists": ..., "rebounds": ..., "ft_made": ..., ... },
      "players": {
        "<PlayerName>": { "points": ..., "assists": ..., "rebounds": ..., "ft_made": ..., ... },
        ...
      }
    },
    "<TeamB>": { ... }
  }
}



  "final_stats": {
    "<TeamA>": {
      "stats": { "points": ..., "assists": ..., "rebounds": ..., "ft_made": ..., ... },
      "players": {
        "<PlayerName>": { "points": ..., "assists": ..., "rebounds": ..., "ft_made": ..., ... },
        ...
      }
    },
    "<TeamB>": { ... }
  }
}

* Team and player stat objects share the same fields (points/assists/rebounds/...
  including attempts/made for 2pt/3pt and free throws).
* VAR events can “undo” or modify shots (e.g., revert a made shot, convert a 3pt
  to a 2pt) and the code keeps attempts ≥ made consistent.

Run configuration
-----------------------
- GAMES_PER_DIFFICULTY: number of games per difficulty level
- DIFFICULTY_LEVELS: which levels to generate (["basic", "medium", "hard"])
- Outputs written at the end:
  - `data/examples.json` — all examples in one dict (Optioanl)
  - `data/true_report.json` — all ground-truth reports in one dict (Optioanl)
  - `data/examples.jsonl` — line-wise: example then true_report for each game_id
"""

import random
import json
import os

class BasketballReportGenerator:
    """
    Generates simulated basketball game data, including play-by-play commentary and detailed final statistics.

    This class simulates a basketball game between two randomly chosen teams, generating a sequence of events based on configurable difficulty levels.
    It tracks player and team stats throughout the game and produces a structured JSONL output containing the full game report.

    Key features:
    -------------
    - Dynamic generation of play-by-play events.
    - Statistical tracking for players and teams (points, assists, rebounds, etc.).
    - Configurable difficulty levels ("basic", "medium", "hard") that affect
      game complexity (e.g., substitutions, VAR reviews, event frequency).
    - Management of player substitutions, foul-outs, and team foul bonuses.
    - Output of a comprehensive game summary in JSONL format.

    Typical usage
    -------------
        generator = BasketballReportGenerator()
        game_data = generator.generate_report(difficulty="medium")

    Configuration knobs
    -------------------
    - FOUL_LIMIT (default 5): personal foul-out threshold.
    - TEAM_FOUL_LIMIT (default 5): team foul tracking per quarter (bonus FT — optional/disabled by default).
    - DEBUG_TEAM_FOULS: extra logging for team fouls.
    - create_jsonl_file: Save JSONL with alternating lines: example, then true_report
    - create_json_files: Save the complete dictionaries to 2 separate JSON file
    """

    def __init__(self):
        """
        Initializes the BasketballReportGenerator.

        Sets up game rules, team rosters, and event templates.
        """
        # --- Game Rules ---
        self.FOUL_LIMIT = 5  # Per-player foul limit before disqualification
        self.TEAM_FOUL_LIMIT = 5  # Per-quarter team foul limit for bonus free throws
        self.DEBUG_TEAM_FOULS = False  # If True, adds debug messages for team fouls

        # --- Team and Player Data ---
        # Head coaches for each team
        self.Israel_head_coach = "Ariel Beit-Halahmy"
        self.Iceland_head_coach = "Craig Pedersen"
        self.Poland_head_coach = "Igor Milicic"
        self.France_head_coach = "Frederic Fauthoux"
        self.Belgium_head_coach = "Dario Gjergja"
        self.Slovenia_head_coach = "Aleksander Sekulic"

        # Player rosters for each team
        self.Israel_players = [
            "Khadeen Carrington", "Itay Segev", "Deni Avdija", "Roman Sorkin", "Bar Timor", "Yam Madar", "Rafi Menco", "Nimrod Levi", "Ethan Burg", "Tomer Ginat", "Yovel Zoosman", "Guy Palatin"
            ]
        self.Iceland_players = [
            "Aegir Steinarsson", "Hilmar Henningsson", "Jon Axel Gudmundsson", "Elvar Fridriksson", "Almar Orri Atlason", "Karl Jonsson", "Kristinn Palsson", "Martin Hermannsson", "Orri Gunnarsson", "Tryggvi Hlinason", "Styrmir Thrastarson", "Sigtryggur Bjornsson"
            ]
        self.Poland_players = [
            "Andrzej Pluta", "Aleksander Balcerowski", "Michal Sokolowski", "Jordan Loyd", "Mateusz Ponitka", "Szymon Zapala", "Aleksander Dziewa", "Tomasz Gielo", "Kamil Laczynski", "Dominik Olejniczak", "Michal Michalak", "Przemyslaw Zolnierewicz"
            ]
        self.France_players = [
            "Sylvain Francisco", "Elie Okobo", "Nadir Hifi", "Timothe Luwawu-Cabarrot", "Guerschon Yabusele", "Isaia Cordinier", "Theo Maledon", "Mouhammadou Jaiteh", "Zaccharie Risacher", "Jaylen Hoard", "Alexandre Sarr", "Bilal Coulibaly"
            ]
        self.Belgium_players = [
            "Emmanuel Lecomte", "Jean-Marc Mwema", "Hans Vanwijn", "Loic Schwartz", "Kevin Tumba", "Ismael Bako", "Andy van Vliet", "Siebe Ledegen", "Niels Van Den Eynde", "Joppe Mennes", "Godwin Tshimanga", "Mamadou Guisse"
            ]
        self.Slovenia_players = [
            "Martin Krampelj", "Mark Padjen", "Aleksej Nikolic", "Klemen Prepelic", "Edo Muric", "Rok Radovic", "Robert Jurkovic", "Gregor Hrovat", "Luka Scuka", "Alen Omic", "Leon Stergar", "Luka Doncic"
            ]

        # Master dictionary of all teams
        self.teams = {
            "Israel": {"head_coach": self.Israel_head_coach, "players": self.Israel_players},
            "Iceland": {"head_coach": self.Iceland_head_coach, "players": self.Iceland_players},
            "Poland": {"head_coach": self.Poland_head_coach, "players": self.Poland_players},
            "France": {"head_coach": self.France_head_coach, "players": self.France_players},
            "Belgium": {"head_coach": self.Belgium_head_coach, "players": self.Belgium_players},
            "Slovenia": {"head_coach": self.Slovenia_head_coach, "players": self.Slovenia_players},
        }

        # --- Event Templates ---
        # Each event has a text template and an 'effect' lambda function to update game stats.
        self.event_templates = {
            # --- Scoring Events ---
            "assist_and_score_2pt": {
                "template": "{player_A} {pass_type} {player_B}, who {shot_description}",
                "effect": lambda state, pA, pB, team: (
                    state[team]['stats'].update({
                        'points': state[team]['stats']['points'] + 2,
                        'assists': state[team]['stats']['assists'] + 1,
                        '2pt_shots_made': state[team]['stats']['2pt_shots_made'] + 1,
                        '2pt_shots_attempted': state[team]['stats']['2pt_shots_attempted'] + 1,
                        }),
                    state[team]['players'][pA].update({
                        'assists': state[team]['players'][pA]['assists'] + 1
                        }),
                    state[team]['players'][pB].update({
                        'points': state[team]['players'][pB]['points'] + 2,
                        '2pt_shots_made': state[team]['players'][pB]['2pt_shots_made'] + 1,
                        '2pt_shots_attempted': state[team]['players'][pB]['2pt_shots_attempted'] + 1
                        })
                )
            },
            "assist_and_score_2pt_opposite": {
                "template": "{player_B} {opposite_pass_type} {player_A}, and {shot_description}",
                "effect": lambda state, pA, pB, team: (
                    state[team]['stats'].update({
                        'points': state[team]['stats']['points'] + 2,
                        'assists': state[team]['stats']['assists'] + 1,
                        '2pt_shots_made': state[team]['stats']['2pt_shots_made'] + 1,
                        '2pt_shots_attempted': state[team]['stats']['2pt_shots_attempted'] + 1,
                        }),
                    state[team]['players'][pA].update({
                        'assists': state[team]['players'][pA]['assists'] + 1
                        }),
                    state[team]['players'][pB].update({
                        'points': state[team]['players'][pB]['points'] + 2,
                        '2pt_shots_made': state[team]['players'][pB]['2pt_shots_made'] + 1,
                        '2pt_shots_attempted': state[team]['players'][pB]['2pt_shots_attempted'] + 1
                        })
                )
            },

            "assist_and_score_3pt": {
                "template": "{player_A} {pass_type} {player_B}, who {shot_description}",
                "effect": lambda state, pA, pB, team: (
                    state[team]['stats'].update({
                        'points': state[team]['stats']['points'] + 3,
                        'assists': state[team]['stats']['assists'] + 1,
                        '3pt_shots_made': state[team]['stats']['3pt_shots_made'] + 1,
                        '3pt_shots_attempted': state[team]['stats']['3pt_shots_attempted'] + 1,
                        }),
                    state[team]['players'][pA].update({
                        'assists': state[team]['players'][pA]['assists'] + 1
                        }),
                    state[team]['players'][pB].update({
                        'points': state[team]['players'][pB]['points'] + 3,
                        '3pt_shots_made': state[team]['players'][pB]['3pt_shots_made'] + 1,
                        '3pt_shots_attempted': state[team]['players'][pB]['3pt_shots_attempted'] + 1
                        })
                )
            },
            "assist_and_score_3pt_opposite": {
                "template": "{player_B} {opposite_pass_type} {player_A}, and {shot_description}",
                "effect": lambda state, pA, pB, team: (
                    state[team]['stats'].update({
                        'points': state[team]['stats']['points'] + 3,
                        'assists': state[team]['stats']['assists'] + 1,
                        '3pt_shots_made': state[team]['stats']['3pt_shots_made'] + 1,
                        '3pt_shots_attempted': state[team]['stats']['3pt_shots_attempted'] + 1,
                        }),
                    state[team]['players'][pA].update({
                        'assists': state[team]['players'][pA]['assists'] + 1
                        }),
                    state[team]['players'][pB].update({
                        'points': state[team]['players'][pB]['points'] + 3,
                        '3pt_shots_made': state[team]['players'][pB]['3pt_shots_made'] + 1,
                        '3pt_shots_attempted': state[team]['players'][pB]['3pt_shots_attempted'] + 1
                        })
                )
            },
            
            # --- Missed Shot Events ---
            "miss_2pt_from_pass": {
                "template": "{player_A} {pass_type} {player_B}, who {missed_shot_description}",
                "effect": lambda state, pA, pB, team: (
                    state[team]['stats'].update({
                        '2pt_shots_attempted': state[team]['stats']['2pt_shots_attempted'] + 1
                    }),
                    state[team]['players'][pB].update({
                        '2pt_shots_attempted': state[team]['players'][pB]['2pt_shots_attempted'] + 1,
                    })
                )
            },
            "miss_3pt_from_pass": {
                "template": "{player_A} {pass_type} {player_B}, who {missed_shot_description}",
                "effect": lambda state, pA, pB, team: (
                    state[team]['stats'].update({
                        '3pt_shots_attempted': state[team]['stats']['3pt_shots_attempted'] + 1
                    }),
                    state[team]['players'][pB].update({
                        '3pt_shots_attempted': state[team]['players'][pB]['3pt_shots_attempted'] + 1,
                    })
                )
            },

            # --- Passing Events ---
            "inbound_pass": {
                "template": "{player_A} inbounds the ball to {player_B} to start the possession.",
                "effect": lambda state, pA, pB, team: None # No statistical effect
            },
            "pass_ball": {
                "template": "{player_A} {pass_type} {player_B}.",
                "effect": lambda state, pA, pB, team: None # No statistical effect
            },

            # --- VAR Events ---
            "var_overturn_2pt": {
                "template": "After a VAR review, the previous basket by {player_B} is overturned due to an offensive foul committed by {player_B} against {player_C} before the shot.",
                "effect": lambda state, pA, pB, team: (
                    # 1. Update Team Stats: reverse score/assist, add foul/turnover
                    state[team]['stats'].update({
                        'points': max(0, state[team]['stats']['points'] - 2),
                        'assists': max(0, state[team]['stats']['assists'] - 1),
                        'fouls': state[team]['stats']['fouls'] + 1,
                        'turnovers': state[team]['stats']['turnovers'] + 1,
                        '2pt_shots_made': max(0, state[team]['stats']['2pt_shots_made'] - 1),
                        '2pt_shots_attempted': max(0, state[team]['stats']['2pt_shots_attempted'] - 1),
                    }),
                    # 2. Update Passer (pA): just reverse the assist
                    state[team]['players'][pA].update({
                        'assists': max(0, state[team]['players'][pA]['assists'] - 1)
                    }),
                    # 3. Update Shooter (pB): reverse the shot, add the foul and turnover
                    state[team]['players'][pB].update({
                        'points': max(0, state[team]['players'][pB]['points'] - 2),
                        'fouls': state[team]['players'][pB]['fouls'] + 1,
                        'turnovers': state[team]['players'][pB]['turnovers'] + 1,
                        '2pt_shots_made': max(0, state[team]['players'][pB]['2pt_shots_made'] - 1),
                        '2pt_shots_attempted': max(0, state[team]['players'][pB]['2pt_shots_attempted'] - 1),
                    }),
                    # attempts ≥ made
                    state[team]['stats'].__setitem__('2pt_shots_attempted', max(state[team]['stats']['2pt_shots_attempted'], state[team]['stats']['2pt_shots_made'])),
                    state[team]['players'][pB].__setitem__('2pt_shots_attempted', max(state[team]['players'][pB]['2pt_shots_attempted'], state[team]['players'][pB]['2pt_shots_made'])),
                )
            },
            "var_overturn_3pt": {
                "template": "The referees go to the monitor. After VAR review, the 3-point shot by {player_B} is waved off due to a shot clock violation.",
                "effect": lambda state, pA, pB, team: (
                     # 1. Update Team Stats: reverse score/assist, add turnover
                    state[team]['stats'].update({
                        'points': max(0, state[team]['stats']['points'] - 3),
                        'assists': max(0, state[team]['stats']['assists'] - 1),
                        'turnovers': state[team]['stats']['turnovers'] + 1,
                        '3pt_shots_made': max(0, state[team]['stats']['3pt_shots_made'] - 1),
                        '3pt_shots_attempted': max(0, state[team]['stats']['3pt_shots_attempted'] - 1),
                    }),
                    # 2. Update Passer (pA): just reverse the assist
                    state[team]['players'][pA].update({
                        'assists': max(0, state[team]['players'][pA]['assists'] - 1)
                    }),
                    # 3. Update Shooter (pB): reverse the shot, add the turnover
                    state[team]['players'][pB].update({
                        'points': max(0, state[team]['players'][pB]['points'] - 3),
                        'turnovers': state[team]['players'][pB]['turnovers'] + 1,
                        '3pt_shots_made': max(0, state[team]['players'][pB]['3pt_shots_made'] - 1),
                        '3pt_shots_attempted': max(0, state[team]['players'][pB]['3pt_shots_attempted'] - 1),
                    }),
                    # attempts ≥ made
                    state[team]['stats'].__setitem__('3pt_shots_attempted', max(state[team]['stats']['3pt_shots_attempted'], state[team]['stats']['3pt_shots_made'])),
                    state[team]['players'][pB].__setitem__('3pt_shots_attempted', max(state[team]['players'][pB]['3pt_shots_attempted'], state[team]['players'][pB]['3pt_shots_made'])),
                )
            },
            "var_overturn_3pt_another": {
                "template": "VAR review: the shot by {player_B} was released after the buzzer. The 3-point basket does not count.",
                # Params: pA = passer on the made basket, pB = shooter, team = shooter's team
                "effect": lambda state, pA, pB, team: (
                    # Team: remove the 3 points and the assist; add a turnover to the offense (late release)
                    state[team]['stats'].update({
                        'points': max(0, state[team]['stats']['points'] - 3),
                        'assists': max(0, state[team]['stats']['assists'] - 1),
                        'turnovers': state[team]['stats']['turnovers'] + 1,
                        '3pt_shots_made': max(0, state[team]['stats']['3pt_shots_made'] - 1),
                        '3pt_shots_attempted': max(0, state[team]['stats']['3pt_shots_attempted'] - 1),
                    }),
                    # Passer: remove the assist
                    state[team]['players'][pA].update({
                        'assists': max(0, state[team]['players'][pA]['assists'] - 1)
                    }),
                    # Shooter: remove the 3PT make/attempt; credit a turnover for the violation
                    state[team]['players'][pB].update({
                        'points': max(0, state[team]['players'][pB]['points'] - 3),
                        'turnovers': state[team]['players'][pB]['turnovers'] + 1,
                        '3pt_shots_made': max(0, state[team]['players'][pB]['3pt_shots_made'] - 1),
                        '3pt_shots_attempted': max(0, state[team]['players'][pB]['3pt_shots_attempted'] - 1),
                    }),
                    # attempts ≥ made
                    state[team]['stats'].__setitem__('3pt_shots_attempted', max(state[team]['stats']['3pt_shots_attempted'], state[team]['stats']['3pt_shots_made'])),
                    state[team]['players'][pB].__setitem__('3pt_shots_attempted', max(state[team]['players'][pB]['3pt_shots_attempted'], state[team]['players'][pB]['3pt_shots_made'])),
                )
            },

            "var_change_3_to_2": {
                "template": "After a VAR review, {player_B}'s basket is downgraded from three to two points (toe on the line).",
                # Params: pA = passer on the made basket, pB = shooter, team = shooter's team
                "effect": lambda state, pA, pB, team: (
                    # Team: -1 point (3→2), assist unchanged
                    state[team]['stats'].update({
                        'points': max(0, state[team]['stats']['points'] - 1),
                        '3pt_shots_made': max(0, state[team]['stats']['3pt_shots_made'] - 1),
                        '3pt_shots_attempted': max(0, state[team]['stats']['3pt_shots_attempted'] - 1),
                        '2pt_shots_made': state[team]['stats']['2pt_shots_made'] + 1,
                        '2pt_shots_attempted': state[team]['stats']['2pt_shots_attempted'] + 1,
                    }),
                    # Shooter: convert a recorded 3PT make to a 2PT make
                    state[team]['players'][pB].update({
                        'points': max(0, state[team]['players'][pB]['points'] - 1),
                        '3pt_shots_made': max(0, state[team]['players'][pB]['3pt_shots_made'] - 1),
                        '3pt_shots_attempted': max(0, state[team]['players'][pB]['3pt_shots_attempted'] - 1),
                        '2pt_shots_made': state[team]['players'][pB]['2pt_shots_made'] + 1,
                        '2pt_shots_attempted': state[team]['players'][pB]['2pt_shots_attempted'] + 1,
                    }),
                    # attempts ≥ made
                    state[team]['stats'].__setitem__('3pt_shots_attempted', max(state[team]['stats']['3pt_shots_attempted'], state[team]['stats']['3pt_shots_made'])),
                    state[team]['players'][pB].__setitem__('3pt_shots_attempted', max(state[team]['players'][pB]['3pt_shots_attempted'], state[team]['players'][pB]['3pt_shots_made'])),
                    state[team]['stats'].__setitem__('2pt_shots_attempted', max(state[team]['stats']['2pt_shots_attempted'], state[team]['stats']['2pt_shots_made'])),
                    state[team]['players'][pB].__setitem__('2pt_shots_attempted', max(state[team]['players'][pB]['2pt_shots_attempted'], state[team]['players'][pB]['2pt_shots_made'])),

                    # Note: passer assist stays as-is
                )
            },

            # --- Shooting Foul and Free Throw Events ---
            "shooting_foul_2pt": {
                "template": "{player_A} is fouled by {player_B} on a 2-point attempt and will go to the line for two shots.",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    # This event only records the foul and the shot attempt. No points or FTs yet.
                    state[teamA]['stats'].update({'2pt_shots_attempted': state[teamA]['stats']['2pt_shots_attempted'] + 1}),
                    state[teamA]['players'][pA].update({'2pt_shots_attempted': state[teamA]['players'][pA]['2pt_shots_attempted'] + 1}),
                    state[teamB]['stats'].update({'fouls': state[teamB]['stats']['fouls'] + 1}),
                    state[teamB]['players'][pB].update({'fouls': state[teamB]['players'][pB]['fouls'] + 1})
                )
            },
            "shooting_foul_3pt": {
                "template": "{player_A} is fouled by {player_B} on a 3-point attempt and will go to the line for three shots.",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    # This event only records the foul and the shot attempt. No points or FTs yet.
                    state[teamA]['stats'].update({'3pt_shots_attempted': state[teamA]['stats']['3pt_shots_attempted'] + 1}),
                    state[teamA]['players'][pA].update({'3pt_shots_attempted': state[teamA]['players'][pA]['3pt_shots_attempted'] + 1}),
                    state[teamB]['stats'].update({'fouls': state[teamB]['stats']['fouls'] + 1}),
                    state[teamB]['players'][pB].update({'fouls': state[teamB]['players'][pB]['fouls'] + 1})
                )
            },
            "ft_made": {
                "template": "{player_A} makes the {shot_ordinal} free throw.",
                "effect": lambda state, pA, team: (
                    state[team]['stats'].update({
                        'points': state[team]['stats']['points'] + 1,
                        'ft_made': state[team]['stats']['ft_made'] + 1,
                        'ft_attempted': state[team]['stats']['ft_attempted'] + 1
                        }),
                    state[team]['players'][pA].update({
                        'points': state[team]['players'][pA]['points'] + 1,
                        'ft_made': state[team]['players'][pA]['ft_made'] + 1,
                        'ft_attempted': state[team]['players'][pA]['ft_attempted'] + 1
                    })
                )
            },
            "ft_missed": {
                "template": "{player_A} misses the {shot_ordinal} free throw.",
                "effect": lambda state, pA, team: (
                    state[team]['stats'].update({
                        'ft_attempted': state[team]['stats']['ft_attempted'] + 1
                    }),
                    state[team]['players'][pA].update({
                        'ft_attempted': state[team]['players'][pA]['ft_attempted'] + 1
                    })
                )
            },

            # --- Timeout Event ---
            "timeout": {
                "template": "{coach} calls a timeout.",
                "effect": lambda state, coach, team: None  # No statistical effect; used to allow substitutions and pause play
            },

            # --- Game Resume Event ---
            "game_resume": {
                "template": "The game resumes after a timeout.",
                "effect": lambda state: None
            },

            # --- Defensive Events ---
            "steal": {
                "template": "{player_A} steals the ball from {player_B}!",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    state[teamA]['stats'].update({'steals': state[teamA]['stats']['steals'] + 1}),
                    state[teamB]['stats'].update({'turnovers': state[teamB]['stats']['turnovers'] + 1}),
                    state[teamA]['players'][pA].update({'steals': state[teamA]['players'][pA]['steals'] + 1}),
                    state[teamB]['players'][pB].update({'turnovers': state[teamB]['players'][pB]['turnovers'] + 1})
                )
            },
            "turnover_by_bad_pass": {
                "template": "A bad pass from {player_A} results in a turnover.",
                "effect": lambda state, pA, team: (
                    state[team]['stats'].update({'turnovers': state[team]['stats']['turnovers'] + 1}),
                    state[team]['players'][pA].update({'turnovers': state[team]['players'][pA]['turnovers'] + 1})
                )
            },
            "block_on_2pt_shot": {
                "template": "{player_B} tries a 2-point shot, but is blocked by {player_A}!",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    state[teamA]['stats'].update({'blocks': state[teamA]['stats']['blocks'] + 1}),
                    state[teamA]['players'][pA].update({'blocks': state[teamA]['players'][pA]['blocks'] + 1}),
                    state[teamB]['stats'].update({'2pt_shots_attempted': state[teamB]['stats']['2pt_shots_attempted'] + 1}),
                    state[teamB]['players'][pB].update({'2pt_shots_attempted': state[teamB]['players'][pB]['2pt_shots_attempted'] + 1})
                )
            },
            "block_on_3pt_shot": {
                "template": "{player_B} tries a 3-point shot, but is blocked by {player_A}!",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    state[teamA]['stats'].update({'blocks': state[teamA]['stats']['blocks'] + 1}),
                    state[teamA]['players'][pA].update({'blocks': state[teamA]['players'][pA]['blocks'] + 1}),
                    state[teamB]['stats'].update({'3pt_shots_attempted': state[teamB]['stats']['3pt_shots_attempted'] + 1}),
                    state[teamB]['players'][pB].update({'3pt_shots_attempted': state[teamB]['players'][pB]['3pt_shots_attempted'] + 1})
                )
            },
            
            # --- Rebound Events ---
            "rebound_defensive": {
                "template": "Defensive rebound by {player_A}.",
                "effect": lambda state, pA, team: (
                    state[team]['stats'].update({
                        'rebounds': state[team]['stats']['rebounds'] + 1,
                        'defensive_rebounds': state[team]['stats']['defensive_rebounds'] + 1,
                    }),
                    state[team]['players'][pA].update({
                        'rebounds': state[team]['players'][pA]['rebounds'] + 1,
                        'defensive_rebounds': state[team]['players'][pA]['defensive_rebounds'] + 1,
                    })
                )
            },
            "rebound_offensive": {
                "template": "Offensive rebound by {player_A}!",
                "effect": lambda state, pA, team: (
                    state[team]['stats'].update({
                        'rebounds': state[team]['stats']['rebounds'] + 1,
                        'offensive_rebounds': state[team]['stats']['offensive_rebounds'] + 1,
                    }),
                    state[team]['players'][pA].update({
                        'rebounds': state[team]['players'][pA]['rebounds'] + 1,
                        'offensive_rebounds': state[team]['players'][pA]['offensive_rebounds'] + 1,
                    })
                )
            },

            # --- Game Start and End Events ---
            "jump_ball": {
                "template": "The game starts with a jump ball between {player_A} and {player_B}. {winner} wins possession.",
                "effect": lambda state, pA, pB, team: None # No statistical effect
            },
            "end_of_game": {
                "template": "End of game.",
                "effect": lambda state: None # No statistical effect
            }
        }
    
    def _available_players_count(self, team_name, game_lineups):
        """Count available players (active + bench) for a team.

        Args:
            team_name (str): Team name.
            game_lineups (dict): Lineup state:
                {'Team': {'active': [...], 'bench': [...], 'disqualified': [...]}}

        Returns:
            int: Number of available (non-disqualified) players.
        """
        team = game_lineups[team_name]
        return len(team.get('active', [])) + len(team.get('bench', []))

    def _team_can_commit_fouls(self, team_name, game_lineups):
        """Check whether the team can still commit fouls (at least one bench player).

        Rationale:
            Fouls can lead to foul-outs and require a substitution path.
        """
        return bool(game_lineups[team_name].get('bench'))

    def _force_foul_out_substitution(self, team_name, player_out, game_lineups, play_by_play, game_participants):
        """Force a substitution for a player who fouled out (FOUL_LIMIT reached).

        Effects:
            - Marks the player as 'disqualified' (cannot return).
            - If the player was on court: replaces them from the bench, or logs a short-handed state if no bench is available.

        Side effects:
            Mutates `game_lineups`, `play_by_play`, and `game_participants` in place.
        """
        # Ensure the 'disqualified' list exists for the team
        game_lineups[team_name].setdefault('disqualified', [])

        was_active = False
        if player_out in game_lineups[team_name]['active']:
            game_lineups[team_name]['active'].remove(player_out)
            was_active = True
        elif player_out in game_lineups[team_name]['bench']:
            game_lineups[team_name]['bench'].remove(player_out)

        # Mark as disqualified to prevent re-entry
        if player_out not in game_lineups[team_name]['disqualified']:
            game_lineups[team_name]['disqualified'].append(player_out)

        # Log the foul-out event
        avail = self._available_players_count(team_name, game_lineups)
        play_by_play.append({
            "event_id": len(play_by_play) + 1,
            "description": (
                f"{player_out} commits a {self.FOUL_LIMIT}th foul and is disqualified. "
                f"{team_name} available players: {avail}."
            )
        })

        # If the player was on the court, perform a substitution if possible.
        if was_active:
            bench = game_lineups[team_name]['bench']
            if bench:
                player_in = random.choice(bench)
                bench.remove(player_in)
                game_lineups[team_name]['active'].append(player_in)
                game_participants[team_name].add(player_in)
                coach = self.teams[team_name]['head_coach']
                play_by_play.append({
                    "event_id": len(play_by_play) + 1,
                    "description": f"Substitution by {coach}: {player_in} comes in for {player_out} (fouled out)."
                })
            else:
                # If no substitutes are available, the team plays short-handed.
                play_by_play.append({
                    "event_id": len(play_by_play) + 1,
                    "description": f"{team_name} has no eligible substitutes and will continue short-handed."
                })

    def _check_and_handle_foul_out(self, team_name, player_name, game_stats, game_lineups, play_by_play, game_participants):
        """Check if a player has reached FOUL_LIMIT and, if so, trigger foul-out handling.

        Returns:
            bool: True if the player was disqualified and processed now; False otherwise.
        """
        # Already disqualified -> Nothing to do.
        if player_name in game_lineups[team_name].get('disqualified', []):
            return False
        fouls = game_stats[team_name]['players'][player_name]['fouls']
        if fouls >= self.FOUL_LIMIT:
            self._force_foul_out_substitution(team_name, player_name, game_lineups, play_by_play, game_participants)
            return True
        return False

    def _initialize_stats(self):
        """Create a zeroed stats skeleton for all teams/players defined by the class.

        Returns:
            dict: Stats structure with keys per team and nested 'stats'/'players' maps of zeros.

        Note:
            Later, the final game summary narrows to the two selected teams.
        """
        game_state = {}
        for team_name, team_data in self.teams.items():
            # Initialize team-level stats
            game_state[team_name] = {
                "stats": {
                    "points": 0, "assists": 0, "rebounds": 0, "defensive_rebounds": 0, "offensive_rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0,
                    "2pt_shots_made": 0, "2pt_shots_attempted": 0,
                    "3pt_shots_made": 0, "3pt_shots_attempted": 0,
                    "ft_made": 0, "ft_attempted": 0
                    },
                "players": {}
            }
            for player in team_data["players"]:
                # Initialize player-level stats
                game_state[team_name]['players'][player] = {
                    "points": 0, "assists": 0, "rebounds": 0, "defensive_rebounds": 0, "offensive_rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0,
                    "2pt_shots_made": 0, "2pt_shots_attempted": 0,
                    "3pt_shots_made": 0, "3pt_shots_attempted": 0,
                    "ft_made": 0, "ft_attempted": 0
                }
        return game_state

    def _handle_substitution(self, head_coach, team_name, game_lineups, play_by_play, game_participants, sub_chance=0.0, cant_sub_player=None):
        """Attempt a random substitution according to probability.

        Conditions:
            - Requires at least one bench player.
            - If `cant_sub_player` is provided, avoid swapping that player in/out.

        Side effects:
            - Updates active/bench groups, adds a new participant if someone enters from the bench, and appends a human-readable event.
        """
        # Decide whether to substitute based on probability
        if random.random() < sub_chance:
            active_players = game_lineups[team_name]['active']
            bench_players = game_lineups[team_name]['bench']

            if not bench_players: return # Cannot sub if bench is empty

            # Player to be subbed out cannot be the one who was just involved in a foul
            sub_out_options = [p for p in active_players if p != cant_sub_player]
            if not sub_out_options: return # No one eligible to be subbed out

            player_out = random.choice(sub_out_options)
            player_in = random.choice(bench_players)
            game_participants[team_name].add(player_in)

            # Perform the swap between active and bench lists
            active_players.remove(player_out)
            bench_players.append(player_out)
            bench_players.remove(player_in)
            active_players.append(player_in)

            # Log the substitution event
            play_by_play.append({
                "event_id": len(play_by_play) + 1,
                "description": f"Substitution by {head_coach}: {player_in} comes in for {player_out}."
            })

    def generate_report(self, difficulty="medium"):
        """
        Generates a full basketball game report based on a specified difficulty.

        Flow
        ----
        1) Pick two random teams and build starting lineups/benches.
        2) Simulate quarters (and OT if needed) with assorted events: passes,
           shots, misses, fouls, VAR, rebounds, substitutions.
        3) Track personal/team fouls, including foul-out with forced substitutions.
        4) Update team/player stats consistently (attempts ≥ made), including after VAR.
        5) Assemble the `game_summary` with:
           - "teams": roster/starting lineup/bench/participants
           - "play_by_play": ordered event descriptions with incremental event_id
           - "final_stats": final team and per-player box scores

        Args:
            difficulty (str): The difficulty level of the game to generate.
                Accepts "basic", "medium", or "hard". This controls the complexity of the game simulation.

        Returns:
            dict: A dictionary containing the complete game summary.
        """
        # --- generate lexicons for varied wording ---        
        pass_types = ["passed the ball to", "dished it to", "fed", "kicked it out to", "delivered the ball to", "lobbed it to", "swung it over to", "found", "dropped it off to", "set up"]
        opposite_pass_types = ["gets a sharp pass from", "receives a quick pass from", "is set up by", "catches a perfect pass from", "takes a pass from", "is found by", "is fed by", "is delivered the ball by", "is kicked the ball by"]

        regular_ball_pass_types = [ "passes to", "sends it to", "plays it to", "moves it to", "rotates it to", "pushes it to"]

        Successful_2pt_types = ["finishes with a mid-range jump shot.", "finishes with a layup at the rim.", "knocks down a successful 2-point jump shot.", "attempted a 3-pointer and made it, but stepped on the 3-point line.",
                                "dunks with one hand.", "dunks with two hands.", "drives to the basket and scores with a layup.", "pulls up for a mid-range jumper and hits it."]
        Successful_3pt_types = ["is open on the perimeter for a successful 3-point shot.", "is in the corner, and makes the 3-point shot.", "catches and shoots a successful 3-pointer.",
                                "drives and kicks out to a 3-point shooter, who nails it.", "tries a very difficult 3-pointer, but makes it.", "tries a very difficult 3-pointer, but nails it."]
        Missed_2pt_types = ["attempts an easy 2-point shot, but misses.", "misses a mid-range jump shot.", "misses a layup at the rim.", "misses a 2-point jump shot.", "attempted a 3-pointer but stepped on the 3-point line and missed.",
                             "goes up for a dunk but misses.", "attempts a dunk but misses.", "drives to the basket but misses the layup.", "pulls up for a mid-range jumper but misses."]
        Missed_3pt_types = ["attempts an easy 3-point shot, but misses.", "is open on the perimeter for a 3-point shot, but misses.", "is in the corner, and misses the 3-point shot.", "catches and shoots a 3-pointer, but misses.",
                             "drives and kicks out to a 3-point shooter, who misses.", "tries a very easy 3-pointer, but misses.", "tries a very easy 3-pointer, but misses."]

        # --- 1. Difficulty Level Configuration ---
        # Set parameters based on the chosen difficulty level.
        # EVENT_WEIGHTS order MUST match OFFENSIVE_EVENTS:
        # [ turnover_by_bad_pass, steal, timeout,
        #   assist_and_score_2pt, assist_and_score_2pt_opposite,
        #   assist_and_score_3pt, assist_and_score_3pt_opposite,
        #   miss_2pt_from_pass, block_on_2pt_shot, shooting_foul_2pt,
        #   miss_3pt_from_pass, block_on_3pt_shot, shooting_foul_3pt ]
        if difficulty == "basic":
            target_events = 150
            difficulty_max_passes = 5
            adversarial_assist_bias  = False
            allow_substitutions = True
            difficulty_sub_chance = 0.05  # 5% chance to substitute players
            allow_var = False
            difficulty_var_chance = 0  # No VAR
            num_pass_types = max(2, len(pass_types)//4)
            num_opposite_pass_types = max(2, len(opposite_pass_types)//4)
            num_2pt_types = max(2, len(Successful_2pt_types)//4)
            num_3pt_types = max(2, len(Successful_3pt_types)//4)
            num_missed_2pt_types = max(2, len(Missed_2pt_types)//4)
            num_missed_3pt_types = max(2, len(Missed_3pt_types)//4)
            EVENT_WEIGHTS = [
                # General Events
                4,  # turnover_by_bad_pass
                5,  # steal
                4,  # timeout
                # Successful 2PT
                3,  # assist_and_score_2pt
                0,  # assist_and_score_2pt_opposite
                # Successful 3PT
                3,  # assist_and_score_3pt
                0,  # assist_and_score_3pt_opposite
                # Unsuccessful 2PT
                10, # miss_2pt_from_pass
                8,  # block_on_2pt_shot
                8,  # shooting_foul_2pt
                # Unsuccessful 3PT
                9,  # miss_3pt_from_pass
                8,  # block_on_3pt_shot
                7,  # shooting_foul_3pt
            ]

        elif difficulty == "medium":
            target_events = 600
            difficulty_max_passes = 3
            adversarial_assist_bias  = True
            allow_substitutions = True
            difficulty_sub_chance = 0.1  # 10% chance to substitute players
            allow_var = True
            difficulty_var_chance = 0.05  # 5% chance to use VAR
            num_pass_types = max(4, len(pass_types)//2)
            num_opposite_pass_types = max(4, len(opposite_pass_types)//2)
            num_2pt_types = max(4, len(Successful_2pt_types)//2)
            num_3pt_types = max(4, len(Successful_3pt_types)//2)
            num_missed_2pt_types = max(4, len(Missed_2pt_types)//2)
            num_missed_3pt_types = max(4, len(Missed_3pt_types)//2)
            EVENT_WEIGHTS = [
                # General Events
                3,  # turnover_by_bad_pass
                5,  # steal
                3,  # timeout
                # Successful 2PT
                7,  # assist_and_score_2pt
                5,  # assist_and_score_2pt_opposite
                # Successful 3PT
                7,  # assist_and_score_3pt
                5,  # assist_and_score_3pt_opposite
                # Unsuccessful 2PT
                8,  # miss_2pt_from_pass
                6,  # block_on_2pt_shot
                5,  # shooting_foul_2pt
                # Unsuccessful 3PT
                7,  # miss_3pt_from_pass
                6,  # block_on_3pt_shot
                5,  # shooting_foul_3pt
            ]

        else:  # hard
            target_events = 900
            difficulty_max_passes = 1
            adversarial_assist_bias = True
            allow_substitutions = True
            difficulty_sub_chance = 0.15  # 15% chance to substitute players
            allow_var = True
            difficulty_var_chance = 0.1  # 10% chance to use VAR
            num_pass_types = len(pass_types)
            num_opposite_pass_types = len(opposite_pass_types)
            num_2pt_types = len(Successful_2pt_types)
            num_3pt_types = len(Successful_3pt_types)
            num_missed_2pt_types = len(Missed_2pt_types)
            num_missed_3pt_types = len(Missed_3pt_types)
            EVENT_WEIGHTS = [
                # General Events
                2,  # turnover_by_bad_pass
                5,  # steal
                2,  # timeout
                # Successful 2PT
                9,  # assist_and_score_2pt
                7,  # assist_and_score_2pt_opposite
                # Successful 3PT
                9,  # assist_and_score_3pt
                7,  # assist_and_score_3pt_opposite
                # Unsuccessful 2PT
                6,  # miss_2pt_from_pass
                4,  # block_on_2pt_shot
                3,  # shooting_foul_2pt
                # Unsuccessful 3PT
                5,  # miss_3pt_from_pass
                4,  # block_on_3pt_shot
                3,  # shooting_foul_3pt
            ]
        
        # --- Build per-run lexicons for wording (pick random subsets by difficulty) ---
        actual_pass_types = random.sample(pass_types, k=min(max(1, num_pass_types), len(pass_types)))
        actual_opposite_pass_types = random.sample(opposite_pass_types, k=min(max(1, num_opposite_pass_types), len(opposite_pass_types)))

        actual_regular_ball_pass_types = actual_pass_types if adversarial_assist_bias else regular_ball_pass_types

        actual_2pt_desc  = random.sample(Successful_2pt_types, k=min(max(1, num_2pt_types), len(Successful_2pt_types)))
        actual_3pt_desc  = random.sample(Successful_3pt_types, k=min(max(1, num_3pt_types), len(Successful_3pt_types)))
        actual_missed_2pt_desc = random.sample(Missed_2pt_types, k=min(max(1, num_missed_2pt_types), len(Missed_2pt_types)))
        actual_missed_3pt_desc = random.sample(Missed_3pt_types, k=min(max(1, num_missed_3pt_types), len(Missed_3pt_types)))

        # --- 2. Game Setup ---
        # Randomly select two teams to play
        team_names = random.sample(list(self.teams.keys()), 2)
        teamA_name, teamB_name = team_names[0], team_names[1]
        
        # Create initial lineups (5 active, rest on bench)
        game_lineups = {}
        for team_name in team_names:
            full_roster = list(self.teams[team_name]["players"])
            random.shuffle(full_roster)
            game_lineups[team_name] = {'active': full_roster[:5], 'bench': full_roster[5:], 'disqualified': []}
        
        # Store initial lineups and create sets for tracking all participants
        initial_lineups = {tn: {'starting_lineup': list(gl['active']), 'bench': list(gl['bench'])} for tn, gl in game_lineups.items()}
        game_participants = {
            teamA_name: set(initial_lineups[teamA_name]['starting_lineup']),
            teamB_name: set(initial_lineups[teamB_name]['starting_lineup'])
        }
        # Initialize the statistics tracker for the two selected teams
        game_stats = self._initialize_stats()
        game_stats = {team: game_stats[team] for team in team_names}

        # --- 3. Game Simulation Initialization ---
        play_by_play = []
        last_score_event_details = None # Used for VAR checks
        player_with_ball = None

        # --- Start the game with a jump ball ---
        jumper_A = random.choice(game_lineups[teamA_name]['active'])
        jumper_B = random.choice(game_lineups[teamB_name]['active'])
        
        # Randomly determine the winner of the jump ball
        winner_team = random.choice([teamA_name, teamB_name])
        winner_player = jumper_A if winner_team == teamA_name else jumper_B

        # The winner gets the first possession
        possession = winner_team
        player_with_ball = winner_player # This prevents an inbound pass on the first play

        # Log the jump ball event
        jump_ball_event = self.event_templates["jump_ball"]
        play_by_play.append({
            "event_id": len(play_by_play) + 1,
            "description": jump_ball_event["template"].format(player_A=jumper_A, player_B=jumper_B, winner=winner_player)
        })

        # --- Quarters: Q1/Q3 = winner, Q2/Q4 = other ---
        other_team = teamB_name if winner_team == teamA_name else teamA_name
        quarter_starters = [winner_team, other_team, winner_team, other_team] # Alternating possession
        # Distribute the target number of events across four quarters
        base = max(0, target_events // 4)
        rem = target_events % 4
        quarter_targets = [base + (1 if i < rem else 0) for i in range(4)]
        quarter = 1
        # Log the start of the first quarter
        play_by_play.append({"event_id": len(play_by_play) + 1, "description": "Start of Q1."})
        # Per-quarter team foul counters (reset each quarter)
        team_fouls_in_quarter = {teamA_name: 0, teamB_name: 0}
        # Counters to track the number of generated events against the target
        billed_total = 0            # Total events generated for the whole game
        billed_in_quarter = 0       # Events generated in the current quarter
        ot_num = 0                  # Number of overtimes played

        # --- Event Categories for easier selection ---
        Successful_2pt_events = ["assist_and_score_2pt", "assist_and_score_2pt_opposite",]
        Successful_3pt_events = ["assist_and_score_3pt", "assist_and_score_3pt_opposite",]
        unsuccessful_2pt_events = ["miss_2pt_from_pass", "block_on_2pt_shot", "shooting_foul_2pt"]
        unsuccessful_3pt_events = ["miss_3pt_from_pass", "block_on_3pt_shot", "shooting_foul_3pt"]

        two_offense_player_events = Successful_2pt_events + Successful_3pt_events + ["miss_2pt_from_pass", "miss_3pt_from_pass"]

        OFFENSIVE_EVENTS = ["turnover_by_bad_pass", "steal", "timeout"]
        OFFENSIVE_EVENTS += Successful_2pt_events + Successful_3pt_events + unsuccessful_2pt_events + unsuccessful_3pt_events

        # --- 4. Main Game Loop ---
        # The loop continues until the target number of events has been generated.
        while billed_total < target_events:
            prev_len = len(play_by_play)
            offensive_team = possession
            defensive_team = teamB_name if offensive_team == teamA_name else teamA_name
            active_players = game_lineups[offensive_team]['active']

            # --- Start of Possession: Inbound if necessary ---
            if player_with_ball is None:
                inbounder = random.choice(game_lineups[offensive_team]['active'])
                receiver_options = [p for p in active_players if p != inbounder]
                receiver = random.choice(receiver_options) if receiver_options else inbounder # fallback if no receiver (not possible situation, but just in case)
                inbound_event = self.event_templates["inbound_pass"]
                play_by_play.append({"event_id": len(play_by_play) + 1, "description": inbound_event["template"].format(player_A=inbounder, player_B=receiver)})
                player_with_ball = receiver

            # --- Ball Movement: Simulate passes ---
            num_passes = random.randint(0, difficulty_max_passes)
            for _ in range(num_passes):
                passer = player_with_ball
                options = [p for p in active_players if p != passer]
                if not options: # stop passing when no one else to pass to (not possible situation, but just in case)
                    break
                receiver = random.choice(options)
                pass_event = self.event_templates["pass_ball"]
                
                # Build description safely; inject {pass_type} only if the template expects it
                tmpl = pass_event["template"]
                fmt  = {"player_A": passer, "player_B": receiver}

                if "{pass_type}" in tmpl:
                    # Use neutral wording unless we intentionally want assist-scented verbs
                    fmt["pass_type"] = random.choice(actual_regular_ball_pass_types) if actual_regular_ball_pass_types else "passes to"

                # # (harmless) if we ever add a receiver-centric template:
                # elif "{opposite_pass_type}" in tmpl:
                #     fmt["opposite_pass_type"] = random.choice(actual_opposite_pass_types) if actual_opposite_pass_types else "receives a pass from"

                desc = tmpl.format(**fmt)
                play_by_play.append({"event_id": len(play_by_play) + 1, "description": desc})

                player_with_ball = receiver

            # --- End of Possession: Choose and execute an event ---
            # Filter possible events based on game state (e.g., can't foul if no bench players)
            pairs = []
            for et, w in zip(OFFENSIVE_EVENTS, EVENT_WEIGHTS):
                # Offense needs at least two players for assisted shots
                if len(active_players) < 2 and et in two_offense_player_events:
                    continue
                # A team can only commit a shooting foul if they have players on the bench
                if "shooting_foul" in et and not self._team_can_commit_fouls(defensive_team, game_lineups):
                    continue
                # A team can only commit an offensive foul if they have players on the bench
                if "offensive_foul" in et and not self._team_can_commit_fouls(offensive_team, game_lineups):
                    continue
                pairs.append((et, w))
            
            # Select an event based on the weighted probabilities
            if pairs:
                events, weights = zip(*pairs)
                event_type = random.choices(events, weights=weights, k=1)[0]
            else:
                # Fallback to a timeout if no other event is possible
                event_type = "timeout"
            event = self.event_templates[event_type]
            action_player = player_with_ball
            # Flag to track if the possession ended with a shot attempt
            ended_with_shot_attempt = False
            
            Successful_events = Successful_2pt_events + Successful_3pt_events

            # --- Event Execution ---
            if event_type in Successful_events:
                passer = action_player
                scorer_options = [p for p in active_players if p != action_player]
                if not scorer_options:
                    # Shouldn't happen due to selection filter; safe fallback (not possible situation, but just in case)
                    scorer_options = [action_player]
                scorer = random.choice(scorer_options)
                last_score_event_details = {'type': event_type, 'pA': passer, 'pB': scorer, 'team': offensive_team}
                event["effect"](game_stats, passer, scorer, offensive_team)

                # Generic description formatter:
                # Fills {pass_type} and/or {shot_description} ONLY if the template contains them.
                tmpl = event["template"]
                fmt  = {"player_A": passer, "player_B": scorer}

                # If the template expects a pass-type token (A -> B wording)
                if "{pass_type}" in tmpl:
                    fmt["pass_type"] = random.choice(actual_pass_types) if actual_pass_types else "passes to"

                # If the template expects an opposite-pass token (B <- A wording)
                if "{opposite_pass_type}" in tmpl:
                    fmt["opposite_pass_type"] = random.choice(actual_opposite_pass_types) if actual_opposite_pass_types else "receives a pass from"

                # If the template expects a shot description, choose from 2PT/3PT pools accordingly
                if "{shot_description}" in tmpl:
                    pool = actual_2pt_desc if event_type in Successful_2pt_events else actual_3pt_desc
                    fmt["shot_description"] = random.choice(pool)

                desc = tmpl.format(**fmt)

                play_by_play.append({"event_id": len(play_by_play) + 1, "description": desc})

                ended_with_shot_attempt = True

                possession = defensive_team # Possession changes after a score
                
                # --- Optional: VAR Review ---
                if allow_var and random.random() < difficulty_var_chance: # Check for VAR
                    last_type = last_score_event_details['type']
                    if last_type in Successful_2pt_events:
                        var_candidates = ["var_overturn_2pt"] #, "var_change_2_to_3"]
                    else:  # last_type in Successful_3pt_events
                        var_candidates = ["var_overturn_3pt", "var_overturn_3pt_another", "var_change_3_to_2"]
                    var_event_type = random.choice(var_candidates)
                    pA_v, pB_v, team_v = last_score_event_details['pA'], last_score_event_details['pB'], last_score_event_details['team']
                    # Only skip if this VAR would assign an OFFENSIVE FOUL and the team cannot commit fouls (no bench)
                    offensive_foul_var = {"var_overturn_2pt"}
                    if not (var_event_type in offensive_foul_var and not self._team_can_commit_fouls(team_v, game_lineups)):
                        var_event = self.event_templates[var_event_type]
                        var_event["effect"](game_stats, pA_v, pB_v, team_v)
                        # Identify the fouled defender (victim) on the opposing team
                        opponent_team = teamB_name if team_v == teamA_name else teamA_name
                        victim = random.choice(game_lineups[opponent_team]['active'])
                        play_by_play.append({
                            "event_id": len(play_by_play) + 1,
                            "description": var_event["template"].format(
                                player_A=pA_v,
                                player_B=pB_v,
                                player_C=victim
                            )
                        })
                        # If VAR created an offensive foul, check foul-out
                        if var_event_type in offensive_foul_var:
                            self._check_and_handle_foul_out(team_v, pB_v, game_stats, game_lineups, play_by_play, game_participants)
                            # Count team foul for the offensive team
                            team_fouls_in_quarter[team_v] += 1
                            if self.DEBUG_TEAM_FOULS:
                                play_by_play.append({
                                    "event_id": len(play_by_play) + 1,
                                    "description": f"Team fouls this quarter – {team_v}: {team_fouls_in_quarter[team_v]}/{self.TEAM_FOUL_LIMIT}."
                                })
                            # Even If in bonus, do not award two free throws to the opponent !!!
                            if False and (team_fouls_in_quarter[team_v] >= self.TEAM_FOUL_LIMIT):
                                if self.DEBUG_TEAM_FOULS:
                                    play_by_play.append({
                                        "event_id": len(play_by_play) + 1,
                                        "description": "Bonus in effect: two free throws for the non-fouling team."
                                    })
                                bonus_team = opponent_team
                                # The fouled player (victim) takes the free throws
                                ft_shooter = victim
                                play_by_play.append({
                                    "event_id": len(play_by_play) + 1,
                                    "description": f"{ft_shooter} is awarded two free throws (team fouls in bonus)."
                                })
                                ordinals = ["first", "second"]
                                for i in range(2):
                                    is_last_shot = (i == 1)
                                    if random.random() <= 0.5:
                                        self.event_templates['ft_made']['effect'](game_stats, ft_shooter, bonus_team)
                                        desc = self.event_templates['ft_made']['template'].format(player_A=ft_shooter, shot_ordinal=ordinals[i])
                                        play_by_play.append({"event_id": len(play_by_play) + 1, "description": desc})
                                        if is_last_shot:
                                            # After a made last FT, possession goes to the fouling team
                                            possession = team_v
                                            player_with_ball = None
                                    else:
                                        self.event_templates['ft_missed']['effect'](game_stats, ft_shooter, bonus_team)
                                        desc = self.event_templates['ft_missed']['template'].format(player_A=ft_shooter, shot_ordinal=ordinals[i])
                                        play_by_play.append({"event_id": len(play_by_play) + 1, "description": desc})
                                        if is_last_shot:
                                            # On a missed last FT, the ball is live for a rebound
                                            rebound_type = random.choices(["offensive", "defensive"], weights=[0.2, 0.8])[0]
                                            rebound_team = bonus_team if rebound_type == "offensive" else team_v
                                            rebounder = random.choice(game_lineups[rebound_team]['active'])
                                            rebound_event = self.event_templates[f"rebound_{rebound_type}"]
                                            rebound_event["effect"](game_stats, rebounder, rebound_team)
                                            play_by_play.append({"event_id": len(play_by_play) + 1, "description": rebound_event["template"].format(player_A=rebounder)})
                                            possession = rebound_team
                                            player_with_ball = rebounder

                if allow_substitutions:
                    self._handle_substitution(self.teams[teamA_name]['head_coach'], teamA_name, game_lineups, play_by_play, game_participants, sub_chance=difficulty_sub_chance)
                    self._handle_substitution(self.teams[teamB_name]['head_coach'], teamB_name, game_lineups, play_by_play, game_participants, sub_chance=difficulty_sub_chance)
                
                player_with_ball = None # Reset player with ball after change of possession

            elif event_type == "timeout":
                coach_name = self.teams[offensive_team]['head_coach']
                play_by_play.append({"event_id": len(play_by_play) + 1, "description": event["template"].format(coach=coach_name)})

                # Allow both teams to make substitutions after a timeout
                if allow_substitutions:
                    self._handle_substitution(self.teams[teamA_name]['head_coach'], teamA_name, game_lineups, play_by_play, game_participants, sub_chance=difficulty_sub_chance)
                    self._handle_substitution(self.teams[teamB_name]['head_coach'], teamB_name, game_lineups, play_by_play, game_participants, sub_chance=difficulty_sub_chance)

                # After timeout, play resumes with an inbound pass
                resume_event = self.event_templates.get("game_resume")
                if resume_event:
                    play_by_play.append({"event_id": len(play_by_play) + 1, "description": resume_event["template"]})

                inbounder = random.choice(game_lineups[offensive_team]['active'])
                receiver_options = [p for p in game_lineups[offensive_team]['active'] if p != inbounder]
                receiver = random.choice(receiver_options) if receiver_options else inbounder
                inbound_event = self.event_templates["inbound_pass"]
                play_by_play.append({"event_id": len(play_by_play) + 1, "description": inbound_event["template"].format(player_A=inbounder, player_B=receiver)})
                player_with_ball = receiver
                # Possession does not change on a timeout
                # possession remains unchanged

            elif event_type in ["miss_2pt_from_pass", "miss_3pt_from_pass"]:
                passer = action_player
                shooter_options = [p for p in active_players if p != action_player]

                if not shooter_options:
                    # Selection filter should avoid this; safe fallback (not possible situation, but just in case)
                    shooter_options = [action_player]
                shooter = random.choice(shooter_options)
                event["effect"](game_stats, passer, shooter, offensive_team)
                
                # Build the format dict and inject a per-run pass phrase if needed
                tmpl = event["template"]
                fmt = {"player_A": passer, "player_B": shooter}

                if "{pass_type}" in tmpl:
                    fmt["pass_type"] = random.choice(actual_pass_types) if actual_pass_types else "passes to"

                if "{missed_shot_description}" in tmpl:
                    pool = actual_missed_2pt_desc if event_type == "miss_2pt_from_pass" else actual_missed_3pt_desc
                    fmt["missed_shot_description"] = random.choice(pool) if pool else "attempts a shot but misses."

                desc = tmpl.format(**fmt)
                play_by_play.append({"event_id": len(play_by_play) + 1, "description": desc})

                rebound_type = random.choices(["offensive", "defensive"], weights=[0.2, 0.8])[0]
                rebound_team = offensive_team if rebound_type == "offensive" else defensive_team
                rebounder = random.choice(game_lineups[rebound_team]['active'])
                rebound_event = self.event_templates[f"rebound_{rebound_type}"]
                rebound_event["effect"](game_stats, rebounder, rebound_team)
                play_by_play.append({"event_id": len(play_by_play) + 1, "description": rebound_event["template"].format(player_A=rebounder)})
                possession = rebound_team
                player_with_ball = rebounder # Rebounder now has the ball
                ended_with_shot_attempt = True

            elif event_type in ["turnover_by_bad_pass", "steal"]:
                turnover_player = action_player
                
                if event_type == "steal":
                    stealer = random.choice(game_lineups[defensive_team]['active'])
                    event["effect"](game_stats, stealer, turnover_player, defensive_team, offensive_team)
                    play_by_play.append({
                        "event_id": len(play_by_play) + 1,
                        "description": event["template"].format(player_A=stealer, player_B=turnover_player)
                    })
                    possession = defensive_team
                    # The player who got the steal now has the ball
                    player_with_ball = stealer 
                
                else: # A bad pass results in a dead ball and an inbound
                    event["effect"](game_stats, turnover_player, offensive_team)
                    play_by_play.append({
                        "event_id": len(play_by_play) + 1,
                        "description": event["template"].format(player_A=turnover_player)
                    })
                    possession = defensive_team

                    # Substitutions are allowed after this kind of turnover
                    if allow_substitutions:
                        self._handle_substitution(self.teams[offensive_team]['head_coach'], offensive_team, game_lineups, play_by_play, game_participants, sub_chance=difficulty_sub_chance)

                    # The ball is dead, so the next possession will start with an inbound
                    player_with_ball = None

            elif event_type in ["block_on_2pt_shot", "block_on_3pt_shot"]:
                shooter, blocker = action_player, random.choice(game_lineups[defensive_team]['active'])
                event["effect"](game_stats, blocker, shooter, defensive_team, offensive_team)
                play_by_play.append({"event_id": len(play_by_play) + 1, "description": event["template"].format(player_A=blocker, player_B=shooter)})
                rebound_type = random.choices(["offensive", "defensive"], weights=[0.2, 0.8])[0]
                rebound_team = offensive_team if rebound_type == "offensive" else defensive_team
                rebounder = random.choice(game_lineups[rebound_team]['active'])
                rebound_event = self.event_templates[f"rebound_{rebound_type}"]
                rebound_event["effect"](game_stats, rebounder, rebound_team)
                play_by_play.append({"event_id": len(play_by_play) + 1, "description": rebound_event["template"].format(player_A=rebounder)})
                possession = rebound_team
                player_with_ball = rebounder # Rebounder now has the ball
                ended_with_shot_attempt = True

            elif "shooting_foul" in event_type:
                shooter, defender = action_player, random.choice(game_lineups[defensive_team]['active'])

                # Safety: if defensive team can't commit fouls, skip (should be filtered above)
                if not self._team_can_commit_fouls(defensive_team, game_lineups):
                     continue
                
                event["effect"](game_stats, shooter, defender, offensive_team, defensive_team)
                play_by_play.append({"event_id": len(play_by_play) + 1, "description": event["template"].format(player_A=shooter, player_B=defender)})
                ended_with_shot_attempt = True  # shooting foul counts as a shot attempt

                # Immediate foul-out check for the defender
                self._check_and_handle_foul_out(defensive_team, defender, game_stats, game_lineups, play_by_play, game_participants)
                
                # Count team foul for the defensive team
                team_fouls_in_quarter[defensive_team] += 1
                if self.DEBUG_TEAM_FOULS:
                    play_by_play.append({
                        "event_id": len(play_by_play) + 1,
                        "description": f"Team fouls this quarter – {defensive_team}: {team_fouls_in_quarter[defensive_team]}/{self.TEAM_FOUL_LIMIT}."
                    })

                # Shooting fouls result in 2 or 3 free throws
                num_shots = 3 if event_type == "shooting_foul_3pt" else 2
                ordinals = ["first", "second", "third"]
                for i in range(num_shots):
                    is_last_shot = (i + 1) == num_shots
                    if random.random() <= 0.5: # Made FT
                        self.event_templates['ft_made']['effect'](game_stats, shooter, offensive_team)
                        desc = self.event_templates['ft_made']['template'].format(player_A=shooter, shot_ordinal=ordinals[i])
                        play_by_play.append({"event_id": len(play_by_play) + 1, "description": desc})
                        if is_last_shot:
                            possession = defensive_team
                            player_with_ball = None # Reset
                    else: # Missed FT
                        self.event_templates['ft_missed']['effect'](game_stats, shooter, offensive_team)
                        desc = self.event_templates['ft_missed']['template'].format(player_A=shooter, shot_ordinal=ordinals[i])
                        play_by_play.append({"event_id": len(play_by_play) + 1, "description": desc})
                        if is_last_shot:
                            rebound_type = random.choices(["offensive", "defensive"], weights=[0.2, 0.8])[0]
                            rebound_team = offensive_team if rebound_type == "offensive" else defensive_team
                            rebounder = random.choice(game_lineups[rebound_team]['active'])
                            rebound_event = self.event_templates[f"rebound_{rebound_type}"]
                            rebound_event["effect"](game_stats, rebounder, rebound_team)
                            play_by_play.append({"event_id": len(play_by_play) + 1, "description": rebound_event["template"].format(player_A=rebounder)})
                            possession = rebound_team
                            player_with_ball = rebounder # Rebounder has the ball
                    
                    if not is_last_shot and allow_substitutions:
                        # Only the shooting team must keep the shooter on the floor
                        self._handle_substitution(self.teams[offensive_team]['head_coach'], offensive_team,
                                                  game_lineups, play_by_play, game_participants,
                                                  sub_chance=difficulty_sub_chance, cant_sub_player=shooter)
                        self._handle_substitution(self.teams[defensive_team]['head_coach'], defensive_team,
                                                  game_lineups, play_by_play, game_participants,
                                                  sub_chance=difficulty_sub_chance)            
            # --- Event Billing ---
            # Count the generated events towards the quarter's target.
            added_this_iter = len(play_by_play) - prev_len
            if added_this_iter > 0:
                can_bill = max(0, quarter_targets[quarter - 1] - billed_in_quarter)
                bill_now = min(added_this_iter, can_bill)

                # Q4 like the others: don't let Q4 hit its CAP unless THIS play ended with a shot attempt.
                if quarter >= 4 and not ended_with_shot_attempt and billed_in_quarter + bill_now >= quarter_targets[quarter - 1]:
                    # Hold back one unit so the loop stays alive until a shot attempt closes Q4
                    bill_now = max(0, quarter_targets[quarter - 1] - billed_in_quarter - 1)

                billed_in_quarter += bill_now
                billed_total += bill_now


            # --- Quarter Boundary Check ---
            # Check if the quarter should end.
            if quarter < 4 and ended_with_shot_attempt and billed_in_quarter >= quarter_targets[quarter - 1]:
                play_by_play.append({"event_id": len(play_by_play) + 1, "description": f"End of Q{quarter}."})
                quarter += 1
                billed_in_quarter = 0  # Reset event counter for the new quarter
                # Set possession for the start of the next quarter
                possession = quarter_starters[quarter - 1]
                player_with_ball = None  # Force an inbound pass
                play_by_play.append({"event_id": len(play_by_play) + 1, "description": f"Start of Q{quarter}."})
                # Reset team fouls for the new quarter
                team_fouls_in_quarter[teamA_name] = 0
                team_fouls_in_quarter[teamB_name] = 0
                if self.DEBUG_TEAM_FOULS:
                    play_by_play.append({"event_id": len(play_by_play) + 1, "description": "Team fouls reset for new quarter."})

                last_score_event_details = None
                continue

            # --- Overtime trigger: simulate another “mini-quarter” (half length) starting with a jump ball ---
            # If we exhausted the current target and the game is tied (after Q4 or any OT), extend budget for a new OT.
            if billed_total >= target_events and quarter >= 4:
                pointsA = game_stats[teamA_name]['stats']['points']
                pointsB = game_stats[teamB_name]['stats']['points']
                if pointsA == pointsB:
                    next_ot = ot_num + 1

                    if quarter == 4:
                        # Close regulation and announce tie → OT1
                        if not any(ev.get("description") == "End of Q4." for ev in play_by_play):
                            play_by_play.append({"event_id": len(play_by_play) + 1, "description": "End of Q4."})
                        play_by_play.append({
                            "event_id": len(play_by_play) + 1,
                            "description": f"Q4 ends in a tie. Going to OT{next_ot}."
                        })
                    else:
                        # Close previous OT and announce tie → next OT
                        if ot_num > 0 and not any(ev.get("description") == f"End of OT{ot_num}." for ev in play_by_play):
                            play_by_play.append({"event_id": len(play_by_play) + 1, "description": f"End of OT{ot_num}."})
                        play_by_play.append({
                            "event_id": len(play_by_play) + 1,
                            "description": f"OT{ot_num} ends in a tie. Going to OT{next_ot}."
                        })                    

                    # Create a new OT “period” with half a quarter’s cap (min 1)
                    ot_num += 1
                    ot_cap = max(1, quarter_targets[0] // 2)
                    target_events += ot_cap
                    quarter_targets.append(ot_cap)
                    billed_in_quarter = 0
                    # Reset team fouls for the new OT
                    team_fouls_in_quarter[teamA_name] = 0
                    team_fouls_in_quarter[teamB_name] = 0
                    # OT jump ball → winner gets the ball (no inbound)
                    jA = random.choice(game_lineups[teamA_name]['active'])
                    jB = random.choice(game_lineups[teamB_name]['active'])
                    win_team = random.choice([teamA_name, teamB_name])
                    win_player = jA if win_team == teamA_name else jB
                    play_by_play.append({"event_id": len(play_by_play) + 1,
                                         "description": f"Overtime {ot_num} jump ball between {jA} and {jB}. {win_player} wins the tip."})
                    play_by_play.append({"event_id": len(play_by_play) + 1,
                                         "description": f"Start of OT{ot_num}."})
                    quarter += 1
                    possession = win_team
                    player_with_ball = win_player
                    # fall-through: next loop iterations generate OT plays

            last_score_event_details = None

        # --- 5. Finalize Game ---
        # Ensure the end of Q4 is logged if not already present.
        if quarter == 4 and not any(ev.get("description") == "End of Q4." for ev in play_by_play):
            play_by_play.append({"event_id": len(play_by_play) + 1, "description": "End of Q4."})

        # If we had OT(s), close the last one
        if ot_num > 0 and not any(ev.get("description") == f"End of OT{ot_num}." for ev in play_by_play):
            play_by_play.append({"event_id": len(play_by_play) + 1, "description": f"End of OT{ot_num}."})

        # Add the final end-of-game event.
        end_event = self.event_templates["end_of_game"]
        play_by_play.append({
            "event_id": len(play_by_play) + 1,
            "description": end_event["template"]
        })

        # --- 6. Compile and Return Game Summary ---
        game_summary = {
            "matchup": f"{teamA_name} vs {teamB_name}",
            "teams": {
                teamA_name: {
                    "coach": self.teams[teamA_name]["head_coach"],
                    "roster": self.teams[teamA_name]["players"],
                    "starting_lineup": initial_lineups[teamA_name]['starting_lineup'],
                    "bench": initial_lineups[teamA_name]['bench'],
                    "participants": sorted(list(game_participants[teamA_name]))
                },
                teamB_name: {
                    "coach": self.teams[teamB_name]["head_coach"],
                    "roster": self.teams[teamB_name]["players"],
                    "starting_lineup": initial_lineups[teamB_name]['starting_lineup'],
                    "bench": initial_lineups[teamB_name]['bench'],
                    "participants": sorted(list(game_participants[teamB_name]))
                }
            },
            "play_by_play": play_by_play,
            "final_stats": game_stats
        }

        return game_summary

# # --- MAIN EXECUTION ---
if __name__ == "__main__":
    # --- Configuration ---
    # Define the number of games to generate per difficulty level.
    GAMES_PER_DIFFICULTY = 5  # Generates 5 games for each level (15 total)
    DIFFICULTY_LEVELS = ["basic", "medium", "hard"]

    # --- Initialization ---
    generator = BasketballReportGenerator()
    
    # Dictionaries to hold all generated data, keyed by a unique game ID.
    all_examples_data = {}
    all_true_reports_data = {}

    print(f"--- Starting generation of {GAMES_PER_DIFFICULTY * len(DIFFICULTY_LEVELS)} total games ---")

    # --- Data Generation Loop ---
    # Loop through each difficulty level.
    for difficulty in DIFFICULTY_LEVELS:
        print(f"\n{'='*20} GENERATING LEVEL: {difficulty.upper()} {'='*20}")
        
        # Generate the specified number of games for the current difficulty.
        for i in range(GAMES_PER_DIFFICULTY):
            game_index = i + 1
            # Create a unique key like "hard_game_1".
            game_key = f"{difficulty}_game_{game_index}"
            print(f"Generating {game_key}...")
            
            # Generate the game data.
            game_data = generator.generate_report(difficulty=difficulty)
            
            # --- Data Structuring ---
            # 1. `examples.json`: Data for the model's input.
            #    Participants are excluded as they are part of the ground truth.
            teams_no_participants = {
                team: {k: v for k, v in team_data.items() if k != "participants"}
                for team, team_data in game_data["teams"].items()
            }
            examples_data = {
                "matchup": game_data["matchup"],
                "teams": teams_no_participants,
                "play_by_play": game_data["play_by_play"],
            }
            
            # 2. `true_report.json`: The ground truth data for evaluation.
            #    Includes final stats and all participants.
            team_names = list(game_data["final_stats"].keys())
            points_A = game_data["final_stats"][team_names[0]]["stats"]["points"]
            points_B = game_data["final_stats"][team_names[1]]["stats"]["points"]
            true_report_data = {
                "matchup": game_data["matchup"],
                "difficulty": difficulty, # Add difficulty for metadata
                "final_score": f"{team_names[0]}: {points_A}, {team_names[1]}: {points_B}",
                "teams": game_data["teams"],
                "final_stats": game_data["final_stats"]
            }

            # Add the structured data to the main dictionaries.
            all_examples_data[game_key] = examples_data
            all_true_reports_data[game_key] = true_report_data

    print(f"\n--- Finished generating all games ---\n")

    # --- File Output ---
    
    # Save JSONL with alternating lines: example, then true_report
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    jsonl_path = os.path.join(output_dir, "examples.jsonl")

    try:
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for game_key in all_examples_data.keys():
                f.write(json.dumps({"game_id": game_key, "type": "example", "data": all_examples_data[game_key]}, ensure_ascii=False) + "\n")
                f.write(json.dumps({"game_id": game_key, "type": "true_report", "data": all_true_reports_data[game_key]}, ensure_ascii=False) + "\n")
        print(f"Successfully saved alternating JSONL to {jsonl_path}")
    except Exception as e:
        print(f"Error saving to {jsonl_path}: {e}")

    # Optoanal for readability only - Save the complete dictionaries to 2 separate JSON file
    create_json_files = False
    if create_json_files:
        output_dir = "data"
        os.makedirs(output_dir, exist_ok=True)
        examples_path = os.path.join(output_dir, "examples.json")
        true_report_path = os.path.join(output_dir, "true_report.json")

        try:
            with open(examples_path, 'w', encoding='utf-8') as f:
                json.dump(all_examples_data, f, indent=4, ensure_ascii=False)
            print(f"Successfully saved all game examples to {examples_path}")
        except Exception as e:
            print(f"Error saving to {examples_path}: {e}")

        try:
            with open(true_report_path, 'w', encoding='utf-8') as f:
                json.dump(all_true_reports_data, f, indent=4, ensure_ascii=False)
            print(f"Successfully saved all game stats to {true_report_path}")
        except Exception as e:
            print(f"Error saving to {true_report_path}: {e}")