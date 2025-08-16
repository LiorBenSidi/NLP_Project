import os
import litellm
from dotenv import load_dotenv
load_dotenv(override=True)

MODEL_TO_TEST = "deepseek/deepseek-coder"

def get_litellm_response(model_name, messages):
    """Calls any LLM using the LiteLLM library and returns the response content."""
    try:
        print(f"\nSending request to model: {model_name} via LiteLLM...")

        # --- Call the LiteLLM API ---
        response = litellm.completion(
            model=model_name,
            messages=messages,
            tools=None,  # No tools needed for this task
        )

        print("Response received.")
        return response.choices[0].message.content # type: ignore

    except Exception as e:
        print(f"An unexpected error occurred during LiteLLM API call: {e}")
        return None
    
get_litellm_response(MODEL_TO_TEST, [{"role": "user", "content": "Hello, how are you?"}])