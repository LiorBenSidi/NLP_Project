import os
from dotenv import load_dotenv
import google.generativeai as genai

# 1. Load and configure the API Key
load_dotenv(override=True)
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is missing")
genai.configure(api_key=api_key) # type: ignore

model = genai.GenerativeModel(model_name="gemini-2.5-pro") # type: ignore

generation_config = {
    "temperature": 0.5,
    "max_output_tokens": 8192,
    "response_mime_type": "application/json",
}

resp = model.generate_content(
    "Return a JSON object with keys 'foo' and 'bar'.",
    generation_config=generation_config, # type: ignore
)
print(resp.text)