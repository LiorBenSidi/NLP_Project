### **Project Proposal: Narrative-to-Box-Score: A Full Statistical Synthesis Challenge**

**Project Goal (מטרת הפרויקט):**
To test an LLM's ability to synthesize a complete, structured, multi-faceted statistical report (a "box score") from a qualitative, narrative event log of a basketball game. This advanced task requires the model to perform parallel state tracking for multiple entities (teams, players) across numerous statistical categories (points, assists, fouls). The project measures the model's ability to accurately attribute stats, filter irrelevant information, and perform calculations (e.g., percentages), a critical test of its potential as a reliable "unstructured-to-structured" data transformation engine.

### **Fulfilling the "Excellent Project" Requirements:**

#### **1. Infinitely Automatable Generation (`generate_data.py`)**

The game simulator becomes more sophisticated, tracking a rich, nested state for every entity.

**Python Implementation Blueprint (Generative Grammar):**

```python
import random
import json

class BoxScoreGenerator:
    def __init__(self):
        self.team_names = ["Titans", "Vipers", "Raptors", "Comets"]
        self.player_surnames = ["Johnson", "Chen", "Garcia", "Patel", "Williams", "Smith"]
        
        # Events now have complex, multi-stat effects
        self.event_templates = {
            "assist_and_score_2pt": {
                "template": "{player_A} delivers a sharp pass to {player_B}, who finishes with a 2-point layup.",
                "effect": lambda state, pA, pB, team: (
                    state[team]['score'] + 2,
                    state[team]['players'][pA]['assists'] + 1,
                    state[team]['players'][pB]['points'] + 2
                )
            },
            "assist_and_score_3pt": {
                "template": "{player_A} finds {player_B} open on the perimeter for a successful 3-point shot.",
                "effect": lambda state, pA, pB, team: (
                    state[team]['score'] + 3,
                    state[team]['players'][pA]['assists'] + 1,
                    state[team]['players'][pB]['points'] + 3
                )
            },
            "shooting_foul": {
                "template": "{player_A} is fouled by {player_B} while attempting a shot. {player_A} makes 1 of 2 free throws.",
                "effect": lambda state, pA, pB, teamA, teamB: (
                    state[teamA]['score'] + 1,
                    state[teamA]['players'][pA]['points'] + 1,
                    state[teamA]['players'][pA]['ft_made'] + 1,
                    state[teamA]['players'][pA]['ft_attempted'] + 2,
                    state[teamB]['players'][pB]['fouls'] + 1
                )
            },
            "defensive_play": {
                "template": "{player_A} steals the ball from {player_B}, leading to a fast break.",
                "effect": lambda state, pA, pB: (
                    state[pA_team]['players'][pA]['steals'] + 1
                )
            },
            # ... many more event types: blocks, missed shots, turnovers, etc.
        }

    def _initialize_stats(self, teams, players):
        # Helper to create the complex nested dictionary for tracking ground truth
        stats = {}
        for team in teams:
            stats[team] = {"score": 0, "players": {}}
            for player in players[team]:
                stats[team]['players'][player] = {
                    "points": 0, "assists": 0, "fouls": 0, "steals": 0,
                    "blocks": 0, "ft_made": 0, "ft_attempted": 0
                }
        return stats

    def generate_task(self, difficulty='medium'):
        # ... setup teams and players ...
        # stats = self._initialize_stats(...)

        # ... loop to generate narrative events, but the core logic
        # is now to call the 'effect' lambda function to update the nested stats dict ...

        # CRUCIAL: The prompt now instructs the model to return structured data
        prompt = (f"Here is the event log for a game...\n{narrative}\n\n"
                  f"Task: Based *only* on the events listed, provide a complete statistical report. "
                  f"Format your entire response as a single, valid JSON object, with no other text before or after. "
                  f"The JSON should have a key for each team, containing 'total_score' and a 'players' object.")

        # The correct answer is the final, ground-truth stats dictionary itself
        # We will serialize it to JSON for the final check.
        # Add calculated stats like FT%
        for team in stats:
            for player in stats[team]['players']:
                if stats[team]['players'][player]['ft_attempted'] > 0:
                    ft_pct = stats[team]['players'][player]['ft_made'] / stats[team]['players'][player]['ft_attempted']
                    stats[team]['players'][player]['ft_percentage'] = round(ft_pct, 2)
                else:
                    stats[team]['players'][player]['ft_percentage'] = 0.0

        correct_answer_json = json.dumps(stats, sort_keys=True)

        return {
            "id": f"task_{random.randint(1000, 9999)}",
            "prompt": prompt,
            "correct_answer": correct_answer_json,
            "difficulty": difficulty,
            "category": "Unstructured-to-Structured-Synthesis"
        }
```

#### **2. Meta-Data and Difficulty Scaling**

*   **Easy (קל):** Few events, focused on a single stat (e.g., only player points). The model only needs to track one number per player.
*   **Medium (בינוני):** Introduces linked stats (assists + points) and fouls. The model must update multiple stats for multiple players from a single sentence.
*   **Hard (קשה):** More events, complex plays (e.g., a steal leading to a fast break score with a foul), and requires a final calculation step (Free Throw Percentage). This tests the model's ability to perform multi-step, multi-entity data synthesis and basic math.

#### **3. Easy and Reliable Evaluation (`evaluation.py`)**

This is the most critical innovation. By instructing the model to output JSON, the evaluation becomes incredibly robust and easy.

**The Reliable `evaluation.py`:**
```python
import json

def evaluate_response(model_response, correct_answer_json):
    """
    Evaluates the model's structured data output against the ground truth.

    Returns a string indicating the result: 'PERFECT_MATCH', 'FORMAT_ERROR', or 'DATA_ERROR'.
    """
    # Step 1: Check if the response is valid JSON.
    try:
        model_dict = json.loads(model_response)
    except json.JSONDecodeError:
        return 'FORMAT_ERROR' # The model failed the most basic instruction.

    # Step 2: Load the ground truth JSON.
    correct_answer_dict = json.loads(correct_answer_json)
    
    # Step 3: Compare the two Python dictionaries. This is a perfect, unambiguous check.
    # We sort keys in the generator to ensure consistent comparison.
    # To be fully robust, we can sort the parsed model dict too if needed.
    
    if model_dict == correct_answer_dict:
        return 'PERFECT_MATCH'
    else:
        # You could even add logic here to find *where* they differ,
        # e.g., team score was right but player stats were wrong.
        return 'DATA_ERROR'
```

### **Meaningful Conclusion from Failure**

This design allows for a very rich analysis of failure modes in your final report:

*   **Format Errors:** The model is incapable of following structural output instructions, a fundamental failure for any API-like usage.
*   **Data Errors:** The model produces valid JSON, but the information is wrong. This is the more interesting failure. You can pinpoint specific weaknesses:
    *   **Attribution Errors:** Did it give points to the wrong player?
    *   **Aggregation Errors:** Do the player points not sum up to the team's total score?
    *   **Calculation Errors:** Was the Free Throw Percentage calculated incorrectly?
    *   **Synthesis Errors:** Did it fail to link an assist to the corresponding points?

Your conclusion could be powerful: *The model's performance as an unstructured-to-structured data engine is highly brittle. While capable of generating syntactically correct JSON, it frequently commits data errors, particularly in attributing stats from complex sentences involving multiple players. Its inability to maintain an accurate internal ledger demonstrates that it is not performing true state tracking but rather a shallow semantic association, making it unsuitable for high-fidelity data extraction and synthesis tasks that require perfect accuracy.*