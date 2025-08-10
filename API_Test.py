import os
from dotenv import load_dotenv
import google.generativeai as genai

# 1. Load and configure the API Key
load_dotenv(override=True)
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is missing")
genai.configure(api_key=api_key)


# 2. Create the model instance (This is the standard, simple way)
# Note: The model is 'gemini-1.5-flash', not 2.5
model = genai.GenerativeModel('gemini-1.5-flash')


# 3. Call generate_content on the model object, passing the config
response = model.generate_content(
    "Explain how AI works in under 5 words.",
    generation_config=genai.types.GenerationConfig(
        max_output_tokens=5
    )
)

print(response.text.strip())