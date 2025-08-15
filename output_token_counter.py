import os
import json
import math
from statistics import mean, median

# ---- CONFIG ----
RESPONSES_DIR = "data/llm_responses"  # Where your model outputs (JSON files) are stored
MODEL_NAME = "gpt-4o"  # e.g., "gemini/gemini-2.5-flash", "gemini/gemini-1.5-flash", etc.

# ---- TOKEN COUNTER (LLM-aware, with fallbacks) ----
def count_tokens(text: str, model_name: str) -> int:
    # 1) Try litellm.token_counter (supports Gemini as well)
    try:
        from litellm.utils import token_counter
        return int(token_counter(model=model_name, text=text))
    except Exception:
        pass

    # 2) Try tiktoken (OpenAI official)
    try:
        import tiktoken
        try:
            enc = tiktoken.encoding_for_model(model_name)
        except Exception:
            # For unknown models (including Gemini) – fall back to a similar base
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        pass

    # 3) Last-resort approximation – token ~ word (rough)
    return len(text.split())

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return json.dumps(data, ensure_ascii=False)
        except json.JSONDecodeError:
            f.seek(0)
            return f.read()

def round_up_to_multiple(x: int, base: int = 256) -> int:
    return int(math.ceil(x / base) * base)

def summarize_tokens_per_dir(root_dir: str, model_name: str):
    # Traverse all subdirectories and collect JSON files (basic/medium/hard/json/*.json)
    token_counts = []
    per_file = []

    for root, _, files in os.walk(root_dir):
        for fn in files:
            if fn.lower().endswith(".json"):
                path = os.path.join(root, fn)
                try:
                    text = load_text(path)
                    n = count_tokens(text, model_name)
                    token_counts.append(n)
                    per_file.append((path, n))
                except Exception as e:
                    print(f"Skipping {path}: {e}")

    if not token_counts:
        print("No JSON files found to scan.")
        return

    token_counts.sort()
    n = len(token_counts)
    p95_idx = max(0, int(0.95 * n) - 1)
    p95 = token_counts[p95_idx]

    stats = {
        "files_scanned": n,
        "min": token_counts[0],
        "median": int(median(token_counts)),
        "avg": int(mean(token_counts)),
        "p95": p95,
        "max": token_counts[-1],
    }

    # Suggested max_tokens: p95 * 1.25, rounded up to nearest 256, capped at 8192
    suggested = min(8192, round_up_to_multiple(int(p95 * 1.25), 256))
    stats["suggested_max_tokens"] = suggested

    # Pretty print
    print("\n=== Token Stats (outputs) ===")
    print(f"Model: {model_name}")
    print(f"Scanned dir: {root_dir}")
    for k in ["files_scanned", "min", "median", "avg", "p95", "max", "suggested_max_tokens"]:
        print(f"{k}: {stats[k]}")

    # Top 10 largest outputs
    largest = sorted(per_file, key=lambda x: x[1], reverse=True)[:10]
    print("\nTop 10 largest outputs (by tokens):")
    for path, n in largest:
        print(f"{n:>6}  {path}")

if __name__ == "__main__":
    summarize_tokens_per_dir(RESPONSES_DIR, MODEL_NAME)
