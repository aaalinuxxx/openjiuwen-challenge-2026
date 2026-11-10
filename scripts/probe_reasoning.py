import os
import json
import httpx

api_key = os.environ.get("LLM_API_KEY", "sk-qxTfP0UOoB4TA9vtBb2QwA")
base_url = os.environ.get("LLM_BASE_URL", "https://api.neuraldeep.ru/v1").rstrip("/")
url = f"{base_url}/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

payload = {
    "model": "qwen3.8-27b",
    "messages": [
        {"role": "user", "content": "Solve: 2 + 2 * 2. Output ONLY the single final number."}
    ],
    "max_tokens": 128,
    "temperature": 0.0
}

print(f"???????? ??????? ? ?????? qwen3.8-27b...")
try:
    resp = httpx.post(url, headers=headers, json=payload, timeout=40.0)
    print(f"HTTP Status: {resp.status_code}")
    data = resp.json()
    print("\n--- Choices ---")
    print(json.dumps(data.get("choices", []), ensure_ascii=False, indent=2))
    print("\n--- Usage (???? ???????) ---")
    print(json.dumps(data.get("usage", {}), ensure_ascii=False, indent=2))
except Exception as e:
    print(f"?????? ??? ?????? API: {e}")