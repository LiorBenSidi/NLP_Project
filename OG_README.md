### **Project Proposal: Narrative-to-Box-Score: A Full Statistical Synthesis Challenge**

**Project Goal (מטרת הפרויקט):**
To test an LLM's ability to synthesize a complete, structured, multi-faceted statistical report (a "box score") from a qualitative, narrative event log of a basketball game. This advanced task requires the model to perform parallel state tracking for multiple entities (teams, players) across numerous statistical categories (points, assists, fouls). The project measures the model's ability to accurately attribute stats, filter irrelevant information, and perform calculations (e.g., percentages), a critical test of its potential as a reliable "unstructured-to-structured" data transformation engine.

### **Fulfilling the "Excellent Project" Requirements:**

#### **1. Infinitely Automatable Generation (`generate_data.py`)**

The game simulator becomes more sophisticated, tracking a rich, nested state for every entity.

**Python Implementation Blueprint (Generative Grammar):**



#### **2. Meta-Data and Difficulty Scaling**

*   **Easy (קל):** Few events, focused on a single stat (e.g., only player points). The model only needs to track one number per player.
*   **Medium (בינוני):** Introduces linked stats (assists + points) and fouls. The model must update multiple stats for multiple players from a single sentence.
*   **Hard (קשה):** More events, complex plays (e.g., a steal leading to a fast break score with a foul), and requires a final calculation step (Free Throw Percentage). This tests the model's ability to perform multi-step, multi-entity data synthesis and basic math.

#### **3. Easy and Reliable Evaluation (`evaluation.py`)**

This is the most critical innovation. By instructing the model to output JSON, the evaluation becomes incredibly robust and easy.


### **Meaningful Conclusion from Failure**

This design allows for a very rich analysis of failure modes in your final report:

*   **Format Errors:** The model is incapable of following structural output instructions, a fundamental failure for any API-like usage.
*   **Data Errors:** The model produces valid JSON, but the information is wrong. This is the more interesting failure. You can pinpoint specific weaknesses:
    *   **Attribution Errors:** Did it give points to the wrong player?
    *   **Aggregation Errors:** Do the player points not sum up to the team's total score?
    *   **Calculation Errors:** Was the Free Throw Percentage calculated incorrectly?
    *   **Synthesis Errors:** Did it fail to link an assist to the corresponding points?

Your conclusion could be powerful: *The model's performance as an unstructured-to-structured data engine is highly brittle. While capable of generating syntactically correct JSON, it frequently commits data errors, particularly in attributing stats from complex sentences involving multiple players. Its inability to maintain an accurate internal ledger demonstrates that it is not performing true state tracking but rather a shallow semantic association, making it unsuitable for high-fidelity data extraction and synthesis tasks that require perfect accuracy.*