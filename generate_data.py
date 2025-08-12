# generate_data.py

# TODO: Assumptions for simplicity:
# 1. There is no limit to number of fouls per player.
# 

# TODO: Need to add:
# 1. Support for different types of fouls (e.g., shooting foul, technical foul)
# 2. Call for timeout and after that immediately return to the game
# 3. After a timeout, the game resumes with the same possession
# 4. Support for different types of 2pt shots (e.g., layup, dunk, jump shot, tried for 3pt but step on the line)
# 5. Support for different types of 3pt shots (e.g., corner three, from the half court like Steph Curry)
# 6. Add VAR (Video Assistant Referee) support for reviewing close calls. If an event has been canceled or overturned, it should be reflected in the game state.

import random
import json
import os

class BasketballReportGenerator:

    def __init__(self):
        # Initialize teams with head coach and players

        # head coaches
        self.Maccabi_Tel_Aviv_head_coach = "Oded Kattash"
        self.Hapoel_Tel_Aviv_head_coach = "Dimitrios Itoudis"
        self.Hapoel_Jerusalem_head_coach = "Yonatan Alon"
        self.DDS_Dream_Team_head_coach = "Sagi Dvir"

        # players
        self.Maccabi_Tel_Aviv_players = ["Tal Brody", "Miki Berkovich", "Motti Aroesti", "Doron Jamchi", "Derrick Sharp",
                                         "Anthony Parker", "David Blu", "Guy Pnini", "Omri Casspi", "Lior Eliyahu"]
        #self.Maccabi_Tel_Aviv_players = ["MACCABI_TLV-" + player for player in self.Maccabi_Tel_Aviv_players]
        self.Hapoel_Tel_Aviv_players = ["Raviv Limonad", "Matan Naor", "Tamir Blatt", "Tomer Ginat", "Nate Robinson",
                                       "Bar Timor", "Yaniv Green", "Patrick Beverley", "Meir Tapiro", "Yam Madar"]
        #self.Hapoel_Tel_Aviv_players = ["HAPOEL_TLV-" + player for player in self.Hapoel_Tel_Aviv_players]
        self.Hapoel_Jerusalem_players = ["Yotam Halperin", "Alex Tyus", "Amar'e Stoudemire", "Will Solomon", "Adi Gordon",
                                         "Itay Segev", "Nimrod Levi", "Yovel Zoosman", "Adam Ariel", "Rafi Menco"]
        #self.Hapoel_Jerusalem_players = ["HAPOEL_JER-" + player for player in self.Hapoel_Jerusalem_players]
        self.DDS_Dream_Team_players = ["Sagi Dvir", "Lior Ben Sidi", "Nir Chauser", "Shahaf Wieder", "Barak Sharon",
                            "Gal Ofir", "Yarin Katan", "Alon Krichely", "Ido Avital", "Ofek Bernstein"]

        # Combine all teams into a single dictionary
        self.teams = {"Maccabi Tel Aviv": {"head_coach": self.Maccabi_Tel_Aviv_head_coach,
                                            "players": self.Maccabi_Tel_Aviv_players},
                      "Hapoel Tel Aviv": {"head_coach": self.Hapoel_Tel_Aviv_head_coach,
                                            "players": self.Hapoel_Tel_Aviv_players},
                      "Hapoel Jerusalem": {"head_coach": self.Hapoel_Jerusalem_head_coach,
                                            "players": self.Hapoel_Jerusalem_players},
                      "DDS Dream Team": {"head_coach": self.DDS_Dream_Team_head_coach,
                                        "players": self.DDS_Dream_Team_players}}

        # Event templates for generating play-by-play commentary
        self.event_templates = {
            # --- Scoring Events ---
            "assist_and_score_2pt": {
                "template": "{player_A} delivers a sharp pass to {player_B}, who finishes with a 2-point layup.",
                "effect": lambda state, pA, pB, team: (
                    state[team]['stats'].update({'score': state[team]['stats']['score'] + 2, 'assists': state[team]['stats']['assists'] + 1}),
                    state[team]['players'][pA].update({'assists': state[team]['players'][pA]['assists'] + 1}),
                    state[team]['players'][pB].update({
                        'points': state[team]['players'][pB]['points'] + 2,
                        '2pt_shots_made': state[team]['players'][pB]['2pt_shots_made'] + 1,
                        '2pt_shots_attempted': state[team]['players'][pB]['2pt_shots_attempted'] + 1,
                    })
                )
            },
            "assist_and_score_3pt": {
                "template": "{player_A} finds {player_B} open on the perimeter for a successful 3-point shot.",
                "effect": lambda state, pA, pB, team: (
                    state[team]['stats'].update({'score': state[team]['stats']['score'] + 3, 'assists': state[team]['stats']['assists'] + 1}),
                    state[team]['players'][pA].update({'assists': state[team]['players'][pA]['assists'] + 1}),
                    state[team]['players'][pB].update({
                        'points': state[team]['players'][pB]['points'] + 3,
                        '3pt_shots_made': state[team]['players'][pB]['3pt_shots_made'] + 1,
                        '3pt_shots_attempted': state[team]['players'][pB]['3pt_shots_attempted'] + 1,
                    })
                )
            },
            
            # --- Missed Shot Events ---
            "miss_2pt": {
                "template": "{player_A} attempts a 2-point shot but misses.",
                "effect": lambda state, pA, team: (
                    state[team]['players'][pA].update({
                        '2pt_shots_attempted': state[team]['players'][pA]['2pt_shots_attempted'] + 1,
                    })
                )
            },
            "miss_3pt": {
                "template": "{player_A} attempts a 3-point shot but misses.",
                "effect": lambda state, pA, team: (
                    state[team]['players'][pA].update({
                        '3pt_shots_attempted': state[team]['players'][pA]['3pt_shots_attempted'] + 1,
                    })
                )
            },
            
            # --- VAR ---
            # "VAR-The_referee_Cancels_the_last_shot": {
            #     "template": "The referee is reviewing the play for a potential violation. He cancels the last shot."
            # },

            # --- Foul Events ---
            "shooting_foul_for_2pt_and_score_0_of_2": {
                "template": "{player_A} is fouled by {player_B} while attempting a 2pt shot. {player_A} makes 0 of 2 free throws.",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    state[teamA]['stats'].update({'score': state[teamA]['stats']['score'] + 0}),
                    state[teamA]['players'][pA].update({
                        'points': state[teamA]['players'][pA]['points'] + 0,
                        'ft_made': state[teamA]['players'][pA]['ft_made'] + 0,
                        'ft_attempted': state[teamA]['players'][pA]['ft_attempted'] + 2,
                    }),
                    state[teamB]['stats'].update({'fouls': state[teamB]['stats']['fouls'] + 1}),
                    state[teamB]['players'][pB].update({'fouls': state[teamB]['players'][pB]['fouls'] + 1})
                )
            },
            "shooting_foul_for_2pt_and_score_1_of_2": {
                "template": "{player_A} is fouled by {player_B} while attempting a 2pt shot. {player_A} makes 1 of 2 free throws.",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    state[teamA]['stats'].update({'score': state[teamA]['stats']['score'] + 1}),
                    state[teamA]['players'][pA].update({
                        'points': state[teamA]['players'][pA]['points'] + 1,
                        'ft_made': state[teamA]['players'][pA]['ft_made'] + 1,
                        'ft_attempted': state[teamA]['players'][pA]['ft_attempted'] + 2,
                    }),
                    state[teamB]['stats'].update({'fouls': state[teamB]['stats']['fouls'] + 1}),
                    state[teamB]['players'][pB].update({'fouls': state[teamB]['players'][pB]['fouls'] + 1})
                )
            },
            "shooting_foul_for_2pt_and_score_2_of_2": {
                "template": "{player_A} is fouled by {player_B} while attempting a 2pt shot. {player_A} makes 2 of 2 free throws.",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    state[teamA]['stats'].update({'score': state[teamA]['stats']['score'] + 2}),
                    state[teamA]['players'][pA].update({
                        'points': state[teamA]['players'][pA]['points'] + 2,
                        'ft_made': state[teamA]['players'][pA]['ft_made'] + 2,
                        'ft_attempted': state[teamA]['players'][pA]['ft_attempted'] + 2,
                    }),
                    state[teamB]['stats'].update({'fouls': state[teamB]['stats']['fouls'] + 1}),
                    state[teamB]['players'][pB].update({'fouls': state[teamB]['players'][pB]['fouls'] + 1})
                )
            },
            "shooting_foul_for_3pt_and_score_0_of_3": {
                "template": "{player_A} is fouled by {player_B} while attempting a 3pt shot. {player_A} makes 0 of 3 free throws.",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    state[teamA]['stats'].update({'score': state[teamA]['stats']['score'] + 0}),
                    state[teamA]['players'][pA].update({
                        'points': state[teamA]['players'][pA]['points'] + 0,
                        'ft_made': state[teamA]['players'][pA]['ft_made'] + 0,
                        'ft_attempted': state[teamA]['players'][pA]['ft_attempted'] + 3,
                    }),
                    state[teamB]['stats'].update({'fouls': state[teamB]['stats']['fouls'] + 1}),
                    state[teamB]['players'][pB].update({'fouls': state[teamB]['players'][pB]['fouls'] + 1})
                )
            },
            "shooting_foul_for_3pt_and_score_1_of_3": {
                "template": "{player_A} is fouled by {player_B} while attempting a 3pt shot. {player_A} makes 1 of 3 free throws.",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    state[teamA]['stats'].update({'score': state[teamA]['stats']['score'] + 1}),
                    state[teamA]['players'][pA].update({
                        'points': state[teamA]['players'][pA]['points'] + 1,
                        'ft_made': state[teamA]['players'][pA]['ft_made'] + 1,
                        'ft_attempted': state[teamA]['players'][pA]['ft_attempted'] + 3,
                    }),
                    state[teamB]['stats'].update({'fouls': state[teamB]['stats']['fouls'] + 1}),
                    state[teamB]['players'][pB].update({'fouls': state[teamB]['players'][pB]['fouls'] + 1})
                )
            },
            "shooting_foul_for_3pt_and_score_2_of_3": {
                "template": "{player_A} is fouled by {player_B} while attempting a 3pt shot. {player_A} makes 2 of 3 free throws.",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    state[teamA]['stats'].update({'score': state[teamA]['stats']['score'] + 2}),
                    state[teamA]['players'][pA].update({
                        'points': state[teamA]['players'][pA]['points'] + 2,
                        'ft_made': state[teamA]['players'][pA]['ft_made'] + 2,
                        'ft_attempted': state[teamA]['players'][pA]['ft_attempted'] + 3,
                    }),
                    state[teamB]['stats'].update({'fouls': state[teamB]['stats']['fouls'] + 1}),
                    state[teamB]['players'][pB].update({'fouls': state[teamB]['players'][pB]['fouls'] + 1})
                )
            },
            "shooting_foul_for_3pt_and_score_3_of_3": {
                "template": "{player_A} is fouled by {player_B} while attempting a 3pt shot. {player_A} makes 3 of 3 free throws.",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    state[teamA]['stats'].update({'score': state[teamA]['stats']['score'] + 3}),
                    state[teamA]['players'][pA].update({
                        'points': state[teamA]['players'][pA]['points'] + 3,
                        'ft_made': state[teamA]['players'][pA]['ft_made'] + 3,
                        'ft_attempted': state[teamA]['players'][pA]['ft_attempted'] + 3,
                    }),
                    state[teamB]['stats'].update({'fouls': state[teamB]['stats']['fouls'] + 1}),
                    state[teamB]['players'][pB].update({'fouls': state[teamB]['players'][pB]['fouls'] + 1})
                )
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
            "block_on_2pt_shot": {
                "template": "{player_A} blocks the 2pt shot from {player_B}!",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    state[teamA]['stats'].update({'blocks': state[teamA]['stats']['blocks'] + 1}),
                    state[teamA]['players'][pA].update({'blocks': state[teamA]['players'][pA]['blocks'] + 1}),
                    state[teamB]['players'][pB].update({
                        '2pt_shots_attempted': state[teamB]['players'][pB]['2pt_shots_attempted'] + 1,
                    })
                )
            },
            "block_on_3pt_shot": {
                "template": "{player_A} blocks the 3pt shot from {player_B}!",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    state[teamA]['stats'].update({'blocks': state[teamA]['stats']['blocks'] + 1}),
                    state[teamA]['players'][pA].update({'blocks': state[teamA]['players'][pA]['blocks'] + 1}),
                    state[teamB]['players'][pB].update({
                        '3pt_shots_attempted': state[teamB]['players'][pB]['3pt_shots_attempted'] + 1,
                    })
                )
            },
            "turnover_by_bad_pass": {
                "template": "A bad pass from {player_A} results in a turnover.",
                "effect": lambda state, pA, team: (
                    state[team]['stats'].update({'turnovers': state[team]['stats']['turnovers'] + 1}),
                    state[team]['players'][pA].update({'turnovers': state[team]['players'][pA]['turnovers'] + 1})
                )
            },
            
            # --- Rebound Events ---
            "rebound_defensive": {
                "template": "Defensive rebound by {player_A}.",
                "effect": lambda state, pA, team: (
                    state[team]['stats'].update({'rebounds': state[team]['stats']['rebounds'] + 1}),
                    state[team]['players'][pA].update({'rebounds': state[team]['players'][pA]['rebounds'] + 1})
                )
            },
            "rebound_offensive": {
                "template": "Offensive rebound by {player_A}!",
                "effect": lambda state, pA, team: (
                    state[team]['stats'].update({'rebounds': state[team]['stats']['rebounds'] + 1}),
                    state[team]['players'][pA].update({'rebounds': state[team]['players'][pA]['rebounds'] + 1})
                )
            }
        }
    
    def _get_colored_name(self, name, team_name):
        """Returns the name wrapped in ANSI color codes based on team."""
        COLORS = {
            'YELLOW': '\033[93m',    # Bright Yellow
            'RED': '\033[91m',        # Bright Red
            'MAGENTA': '\033[95m',    # Bright Magenta
            'BLUE': '\033[94m',      # Bright Blue
            'ENDC': '\033[0m'         # Reset
        }
        return name # Return uncolored

        if team_name == "Maccabi Tel Aviv":
            color = COLORS['YELLOW']
        elif team_name == "Hapoel Tel Aviv":
            color = COLORS['RED']
        elif team_name == "Hapoel Jerusalem":
            color = COLORS['MAGENTA']
        elif team_name == "DDS Dream Team":
            color = COLORS['BLUE']
        else:
            return name # Return uncolored if team is unknown
        
        return f"{color}{name}{COLORS['ENDC']}"

    def _initialize_stats(self):
        """Helper to create the complex nested dictionary for tracking ground truth."""
        game_state = {}
        for team_name, team_data in self.teams.items():
            # Initialize team-level stats
            game_state[team_name] = {
                "stats": {"score": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0},
                "players": {}
            }
            for player in team_data["players"]:
                # Initialize player-level stats
                game_state[team_name]['players'][player] = {
                    "points": 0, "assists": 0, "rebounds": 0, "fouls": 0, "steals": 0, "blocks": 0, "turnovers": 0,
                    "2pt_shots_made": 0, "2pt_shots_attempted": 0,
                    "3pt_shots_made": 0, "3pt_shots_attempted": 0,
                    "ft_made": 0, "ft_attempted": 0
                }
        return game_state

    def _handle_substitution(self, head_coach, team_name, game_lineups, play_by_play, cant_sub_player=None):
        """Randomly performs a substitution for a team if conditions are met."""
        # 50% chance of a substitution at any given opportunity
        if random.random() < 0.50:
            active_players = game_lineups[team_name]['active']
            bench_players = game_lineups[team_name]['bench']

            if not bench_players: return # Cannot sub if bench is empty

            # Player to be subbed out cannot be the one who was just involved in a foul
            sub_out_options = [p for p in active_players if p != cant_sub_player]
            if not sub_out_options: return # No one eligible to be subbed out

            player_out = random.choice(sub_out_options)
            player_in = random.choice(bench_players)

            # Perform the swap
            active_players.remove(player_out)
            bench_players.append(player_out)
            bench_players.remove(player_in)
            active_players.append(player_in)

            colored_player_in = self._get_colored_name(player_in, team_name)
            colored_player_out = self._get_colored_name(player_out, team_name)
            #play_by_play.append(f"Substitution by {head_coach}: {colored_player_in} comes in for {colored_player_out}.")
            play_by_play.append({
                "event_id": len(play_by_play) + 1,
                "description": f"Substitution by {head_coach}: {colored_player_in} comes in for {colored_player_out}."
            })

    def generate_report(self, num_events=20):
        team_names = random.sample(list(self.teams.keys()), 2)
        teamA_name, teamB_name = team_names[0], team_names[1]
        colored_teamA = self._get_colored_name(teamA_name, teamA_name)
        colored_teamB = self._get_colored_name(teamB_name, teamB_name)
        print(f"Generating report for {colored_teamA} vs {colored_teamB} with {num_events} events...")

        game_rosters = {
            teamA_name: self.teams[teamA_name],
            teamB_name: self.teams[teamB_name]
        }

        # --- Create and initialize game lineups ---
        game_lineups = {}
        for team_name in team_names:
            full_roster = list(game_rosters[team_name]["players"])
            random.shuffle(full_roster)
            game_lineups[team_name] = {
                'active': full_roster[:5],
                'bench': full_roster[5:]
            }
        original_game_lineups = game_lineups.copy()

        game_stats = self._initialize_stats()
        game_stats = {team: game_stats[team] for team in team_names}

        play_by_play = []

        # --- Initialize possession ---
        possession = random.choice(team_names)

        REBOUND_EVENTS = ["miss_2pt", "miss_3pt", "block_on_2pt_shot", "block_on_3pt_shot",
                          "shooting_foul_for_2pt_and_score_0_of_2", "shooting_foul_for_2pt_and_score_1_of_2",
                          "shooting_foul_for_3pt_and_score_0_of_3", "shooting_foul_for_3pt_and_score_1_of_3", "shooting_foul_for_3pt_and_score_2_of_3"]

        # To avoid infinite loops of non-possession-changing events, we'll categorize them.
        OFFENSIVE_EVENTS = [
            "assist_and_score_2pt", "assist_and_score_3pt", "miss_2pt", "miss_3pt",
            "turnover_by_bad_pass", "block_on_2pt_shot", "block_on_3pt_shot", "steal",
            "shooting_foul_for_2pt_and_score_0_of_2", "shooting_foul_for_2pt_and_score_1_of_2",
            "shooting_foul_for_2pt_and_score_2_of_2",
            "shooting_foul_for_3pt_and_score_0_of_3", "shooting_foul_for_3pt_and_score_1_of_3", "shooting_foul_for_3pt_and_score_2_of_3",
            "shooting_foul_for_3pt_and_score_3_of_3"
        ]

        for _ in range(num_events):
            # --- MINIMAL CHANGE 2: Choose an offensive event, not any event ---
            event_type = random.choice(OFFENSIVE_EVENTS)
            event = self.event_templates[event_type]
            
            shooting_team = None

            # --- Event Processing Logic with Possession ---

            # Category 1: Two players, same team (e.g., assist)
            if event_type in ["assist_and_score_2pt", "assist_and_score_3pt"]:
                # --- MINIMAL CHANGE 3: Use possession, don't randomize team ---
                acting_team = possession
                active_players = game_lineups[acting_team]['active']
                if len(active_players) < 2: continue
                pA, pB = random.sample(active_players, 2)
                event["effect"](game_stats, pA, pB, acting_team)
                colored_pA = self._get_colored_name(pA, acting_team)
                colored_pB = self._get_colored_name(pB, acting_team)
                #play_by_play.append(event["template"].format(player_A=colored_pA, player_B=colored_pB))
                play_by_play.append({
                    "event_id": len(play_by_play) + 1,
                    "description": event["template"].format(player_A=colored_pA, player_B=colored_pB)
                })
                # --- Update possession ---
                possession = teamB_name if acting_team == teamA_name else teamA_name
                head_coach_A = self.teams[teamA_name]["head_coach"]
                head_coach_B = self.teams[teamB_name]["head_coach"]
                self._handle_substitution(head_coach_A, teamA_name, game_lineups, play_by_play)
                self._handle_substitution(head_coach_B, teamB_name, game_lineups, play_by_play)

            # Category 2: One player, one team (e.g., miss, turnover)
            elif event_type in ["miss_2pt", "miss_3pt", "turnover_by_bad_pass"]:
                # Use possession
                acting_team = possession
                pA = random.choice(game_lineups[acting_team]['active'])
                event["effect"](game_stats, pA, acting_team)
                colored_pA = self._get_colored_name(pA, acting_team)
                #play_by_play.append(event["template"].format(player_A=colored_pA))
                play_by_play.append({
                    "event_id": len(play_by_play) + 1,
                    "description": event["template"].format(player_A=colored_pA)
                })
                if "miss" in event_type:
                    shooting_team = acting_team
                else: # Turnover
                    possession = teamB_name if acting_team == teamA_name else teamA_name
                    # Substitution for the team that committed the turnover
                    head_coach_A = self.teams[teamA_name]["head_coach"]
                    head_coach_B = self.teams[teamB_name]["head_coach"]
                    head_coach_acting_team = head_coach_A if acting_team == teamA_name else head_coach_B
                    self._handle_substitution(head_coach_acting_team, acting_team, game_lineups, play_by_play)


            # Category 3: Two players, two teams (e.g., foul, block, steal)
            elif "foul" in event_type or "block" in event_type or "steal" in event_type:
                # Use possession to define offensive (teamA) and defensive (teamB) teams
                teamA = possession # Offensive team
                teamB = teamB_name if teamA == teamA_name else teamA_name # Defensive team
                
                if "steal" in event_type:
                    # pA is the stealer (defensive), pB has the turnover (offensive)
                    pA = random.choice(game_lineups[teamB]['active'])
                    pB = random.choice(game_lineups[teamA]['active'])
                    event["effect"](game_stats, pA, pB, teamB, teamA)
                    colored_pA = self._get_colored_name(pA, teamB)
                    colored_pB = self._get_colored_name(pB, teamA)
                    #play_by_play.append(event["template"].format(player_A=colored_pA, player_B=colored_pB))
                    play_by_play.append({
                        "event_id": len(play_by_play) + 1,
                        "description": event["template"].format(player_A=colored_pA, player_B=colored_pB)
                    })
                    possession = teamB # Stealing team gets possession
                else: # Foul or Block
                    if "block" in event_type:
                        # For a block, pA is the blocker (from defensive team), pB is the shooter (from offensive team)
                        blocker = random.choice(game_lineups[teamB]['active']) # pA in template
                        shooter = random.choice(game_lineups[teamA]['active']) # pB in template
                        event["effect"](game_stats, blocker, shooter, teamB, teamA)
                        colored_blocker = self._get_colored_name(blocker, teamB)
                        colored_shooter = self._get_colored_name(shooter, teamA)
                        #play_by_play.append(event["template"].format(player_A=colored_blocker, player_B=colored_shooter))
                        play_by_play.append({
                            "event_id": len(play_by_play) + 1,
                            "description": event["template"].format(player_A=colored_blocker, player_B=colored_shooter)
                        })
                        shooting_team = teamA # The team that shot the ball
                    else: # Foul
                        # For a foul, pA is the shooter (offensive), pB is the defender
                        shooter = random.choice(game_lineups[teamA]['active']) # pA in template
                        defender = random.choice(game_lineups[teamB]['active']) # pB in template
                        event["effect"](game_stats, shooter, defender, teamA, teamB)
                        colored_shooter = self._get_colored_name(shooter, teamA)
                        colored_defender = self._get_colored_name(defender, teamB)
                        #play_by_play.append(event["template"].format(player_A=colored_shooter, player_B=colored_defender))
                        play_by_play.append({
                            "event_id": len(play_by_play) + 1,
                            "description": event["template"].format(player_A=colored_shooter, player_B=colored_defender)
                        })
                        shooting_team = teamA # The team that shot the ball

                        # Handle substitutions AFTER the foul is recorded
                        head_coach_A = self.teams[teamA]["head_coach"]
                        head_coach_B = self.teams[teamB]["head_coach"]
                        self._handle_substitution(head_coach_A, teamA, game_lineups, play_by_play, cant_sub_player=shooter)
                        self._handle_substitution(head_coach_B, teamB, game_lineups, play_by_play)

                        if event_type in ["shooting_foul_for_2pt_and_score_2_of_2", "shooting_foul_for_3pt_and_score_3_of_3"]:
                            # Last shot was MADE, possession changes
                            possession = teamB
                        else:
                            # Last shot was MISSED, a rebound will determine possession.
                            # The 'shooting_team' variable is already set to teamA, so the rebound logic will work.
                            pass

            # --- Rebound Logic (This part was mostly correct) ---
            if shooting_team and event_type in REBOUND_EVENTS:
                rebound_type = random.choices(["offensive", "defensive"], weights=[0.2, 0.8], k=1)[0]

                if rebound_type == "offensive":
                    rebound_team_name = shooting_team
                else: # defensive
                    rebound_team_name = teamB_name if shooting_team == teamA_name else teamA_name

                rebounder = random.choice(game_lineups[rebound_team_name]['active'])
                rebound_event_key = "rebound_" + rebound_type
                rebound_event = self.event_templates[rebound_event_key]

                rebound_event["effect"](game_stats, rebounder, rebound_team_name)
                colored_rebounder = self._get_colored_name(rebounder, rebound_team_name)
                #play_by_play.append(rebound_event["template"].format(player_A=colored_rebounder))
                play_by_play.append({
                    "event_id": len(play_by_play) + 1,
                    "description": rebound_event["template"].format(player_A=colored_rebounder)
                })
                # --- MINIMAL CHANGE 5: Update possession based on rebound ---
                possession = rebound_team_name

                # After a foul, possession is determined by rebound or made FT
                if "foul" in event_type:
                    # Made last FT
                    if event_type not in ["shooting_foul_for_2pt_and_score_0_of_2", "shooting_foul_for_2pt_and_score_1_of_2",
                                          "shooting_foul_for_3pt_and_score_0_of_3", "shooting_foul_for_3pt_and_score_1_of_3", "shooting_foul_for_3pt_and_score_2_of_3"]:
                         possession = teamB_name if shooting_team == teamA_name else teamA_name

        #return play_by_play, game_stats
        # --- Create a comprehensive game object to return ---
        game_summary = {
            "matchup": f"{teamA_name} vs {teamB_name}",
            "teams": {
                teamA_name: {
                    "coach": self.teams[teamA_name]["head_coach"],
                    "roster": self.teams[teamA_name]["players"],
                    "starting_lineup": original_game_lineups[teamA_name]['active'],
                    "bench": original_game_lineups[teamA_name]['bench']
                },
                teamB_name: {
                    "coach": self.teams[teamB_name]["head_coach"],
                    "roster": self.teams[teamB_name]["players"],
                    "starting_lineup": original_game_lineups[teamB_name]['active'],
                    "bench": original_game_lineups[teamB_name]['bench']
                }
            },
            "play_by_play": play_by_play,
            "final_stats": game_stats
        }

        return game_summary

if __name__ == "__main__":
    # Define the number of games to generate
    NUM_GAMES_TO_GENERATE = 5
    
    # 1. Initialize the generator once
    generator = BasketballReportGenerator()
    
    # Create dictionaries to hold all the game data
    all_examples_data = {}
    all_true_reports_data = {}

    print(f"--- Starting generation of {NUM_GAMES_TO_GENERATE} games ---")

    # 2. Loop to generate each game
    for i in range(NUM_GAMES_TO_GENERATE):
        game_index = i + 1
        print(f"Generating game {game_index}/{NUM_GAMES_TO_GENERATE}...")
        
        # A. Generate the comprehensive data for a single game
        game_data = generator.generate_report(num_events=10)
        
        # B. Create a unique key for this game
        game_key = f"game_{game_index}"

        # C. Construct the data for examples.json for this single game
        examples_data = {
            "matchup": game_data["matchup"],
            "teams": game_data["teams"],
            "play_by_play": game_data["play_by_play"]
        }
        
        # D. Construct the data for true_report.json for this single game
        team_names = list(game_data["final_stats"].keys())
        teamA_name = team_names[0]
        teamB_name = team_names[1]
        score_A = game_data["final_stats"][teamA_name]["stats"]["score"]
        score_B = game_data["final_stats"][teamB_name]["stats"]["score"]
        true_report_data = {
            "matchup": game_data["matchup"],
            "final_score": f"{teamA_name}: {score_A}, {teamB_name}: {score_B}",
            "teams": game_data["teams"],
            "final_stats": game_data["final_stats"]
        }

        # E. Add the data for this game to the main dictionaries
        all_examples_data[game_key] = examples_data
        all_true_reports_data[game_key] = true_report_data

    print(f"--- Finished generating {NUM_GAMES_TO_GENERATE} games ---\n")

    # 3. Save the complete dictionaries to JSON files (outside the loop)
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)

    examples_path = os.path.join(output_dir, "examples.json")
    true_report_path = os.path.join(output_dir, "true_report.json")

    # Save the examples file containing all 50 games
    try:
        with open(examples_path, 'w', encoding='utf-8') as f:
            json.dump(all_examples_data, f, indent=4, ensure_ascii=False)
        print(f"Successfully saved {NUM_GAMES_TO_GENERATE} game examples to {examples_path}")
    except Exception as e:
        print(f"Error saving to {examples_path}: {e}")

    # Save the true report file containing all 50 games
    try:
        with open(true_report_path, 'w', encoding='utf-8') as f:
            json.dump(all_true_reports_data, f, indent=4, ensure_ascii=False)
        print(f"Successfully saved {NUM_GAMES_TO_GENERATE} game stats to {true_report_path}")
    except Exception as e:
        print(f"Error saving to {true_report_path}: {e}")

# --- one iteration ---

# if __name__ == "__main__":
#     # 1. Generate the comprehensive game data object
#     generator = BasketballReportGenerator()
#     game_data = generator.generate_report(num_events=50) # Use num_possessions for clarity

#     # 2. Extract data for printing to the console
#     report = game_data["play_by_play"]
#     final_stats = game_data["final_stats"]
    
#     print(f"\n--- MATCHUP: {game_data['matchup']} ---")

#     print("\n--- PLAY-BY-PLAY REPORT ---")
#     for event in report:
#         print(f"{event['event_id']}. {event['description']}")

#     print("\n\n--- FINAL BOX SCORE ---")
#     print(json.dumps(final_stats, indent=4))

#     # 3. Save the data to JSON files
#     output_dir = "data"
#     os.makedirs(output_dir, exist_ok=True)

#     examples_path = os.path.join(output_dir, "examples.json")
#     true_report_path = os.path.join(output_dir, "true_report.json")

#     # Create the object to be saved in examples.json
#     examples_data = {
#         "matchup": game_data["matchup"],
#         "teams": game_data["teams"],
#         "play_by_play": game_data["play_by_play"]
#     }
    
#     # Create the object to be saved in true_report.json
#     team_names = list(game_data["final_stats"].keys())
#     teamA_name = team_names[0]
#     teamB_name = team_names[1]
    
#     score_A = game_data["final_stats"][teamA_name]["stats"]["score"]
#     score_B = game_data["final_stats"][teamB_name]["stats"]["score"]

#     true_report_data = {
#         "matchup": game_data["matchup"],
#         "final_score": f"{teamA_name}: {score_A}, {teamB_name}: {score_B}",
#         "teams": game_data["teams"],
#         "final_stats": game_data["final_stats"]
#     }

#     # Save the examples file
#     try:
#         with open(examples_path, 'w', encoding='utf-8') as f:
#             json.dump(examples_data, f, indent=4, ensure_ascii=False)
#         print(f"\nSuccessfully saved play-by-play and rosters to {examples_path}")
#     except Exception as e:
#         print(f"Error saving to {examples_path}: {e}")

#     # Save the true report (stats) file
#     try:
#         with open(true_report_path, 'w', encoding='utf-8') as f:
#             json.dump(true_report_data, f, indent=4, ensure_ascii=False)
#         print(f"Successfully saved final stats and rosters to {true_report_path}")
#     except Exception as e:
#         print(f"Error saving to {true_report_path}: {e}")