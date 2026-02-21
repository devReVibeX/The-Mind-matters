# # # # # # # # # # # # # # # # # #!/usr/bin/env python3
# # # # # # # # # # # # # # # # # """
# # # # # # # # # # # # # # # # # api_chat.py

# # # # # # # # # # # # # # # # # A production-friendly Flask API that provides a therapy-aware chatbot endpoint.
# # # # # # # # # # # # # # # # # Features:
# # # # # # # # # # # # # # # # # - Auto-detects and prefers a local LLM server (LM Studio, Ollama, etc.).
# # # # # # # # # # # # # # # # # - Optional OpenAI integration (set OPENAI_API_KEY env var).
# # # # # # # # # # # # # # # # # - Safe, simple "system role" for therapy assistant (easy English, empathetic, safe).
# # # # # # # # # # # # # # # # # - Streaming endpoint (/chat/stream) that yields Server-Sent Events (SSE) for progressive replies.
# # # # # # # # # # # # # # # # # - Non-streaming endpoint (/chat) that returns the full reply JSON.
# # # # # # # # # # # # # # # # # - Rule-based fallback if no LLM is available (fully offline).
# # # # # # # # # # # # # # # # # - Uses Flask + flask_cors + requests (standard libs). Keep dependencies minimal.
# # # # # # # # # # # # # # # # # - Configurable via environment variables.
# # # # # # # # # # # # # # # # # """

# # # # # # # # # # # # # # # # # import os
# # # # # # # # # # # # # # # # # import time
# # # # # # # # # # # # # # # # # import json
# # # # # # # # # # # # # # # # # import logging
# # # # # # # # # # # # # # # # # from typing import Optional, Dict, Any, List
# # # # # # # # # # # # # # # # # from flask import Flask, request, jsonify, Response, stream_with_context
# # # # # # # # # # # # # # # # # from flask_cors import CORS
# # # # # # # # # # # # # # # # # import requests

# # # # # # # # # # # # # # # # # # -------------------------
# # # # # # # # # # # # # # # # # # Configuration (env)
# # # # # # # # # # # # # # # # # # -------------------------
# # # # # # # # # # # # # # # # # LOCAL_LLM_ENABLED = os.getenv("LOCAL_LLM_ENABLED", "true").lower() in ("1", "true", "yes")
# # # # # # # # # # # # # # # # # LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://127.0.0.1:1234/v1/chat/completions")
# # # # # # # # # # # # # # # # # # Example local LLM payload format compatible with many local servers that implement Chat-Completions style.
# # # # # # # # # # # # # # # # # # You can change path/port if using a different local server.

# # # # # # # # # # # # # # # # # OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# # # # # # # # # # # # # # # # # OPENAI_ENABLED = bool(OPENAI_API_KEY)

# # # # # # # # # # # # # # # # # # When both local and openai are available, prefer local by default.
# # # # # # # # # # # # # # # # # PREFER_LOCAL = os.getenv("PREFER_LOCAL", "true").lower() in ("1", "true", "yes")

# # # # # # # # # # # # # # # # # # Limits
# # # # # # # # # # # # # # # # # MAX_TOKENS = int(os.getenv("MAX_TOKENS", "350"))
# # # # # # # # # # # # # # # # # TIMEOUT_SEC = float(os.getenv("LLM_TIMEOUT", "15"))

# # # # # # # # # # # # # # # # # # Server
# # # # # # # # # # # # # # # # # HOST = os.getenv("CHAT_API_HOST", "0.0.0.0")
# # # # # # # # # # # # # # # # # PORT = int(os.getenv("CHAT_API_PORT", "5100"))

# # # # # # # # # # # # # # # # # # Logging
# # # # # # # # # # # # # # # # # logging.basicConfig(level=logging.INFO)
# # # # # # # # # # # # # # # # # log = logging.getLogger("api_chat")

# # # # # # # # # # # # # # # # # # -------------------------
# # # # # # # # # # # # # # # # # # Safety / System Role
# # # # # # # # # # # # # # # # # # -------------------------
# # # # # # # # # # # # # # # # # SYSTEM_PROMPT = (
# # # # # # # # # # # # # # # # #     "You are a compassionate, calm, supportive mental-health assistant. "
# # # # # # # # # # # # # # # # #     "Use very simple, friendly English. Keep replies short (2-6 sentences) unless user asks for more. "
# # # # # # # # # # # # # # # # #     "Do NOT provide medical instructions or diagnoses. Encourage seeking professional support when appropriate. "
# # # # # # # # # # # # # # # # #     "If user expresses self-harm or imminent danger, explicitly tell them to contact emergency services immediately. "
# # # # # # # # # # # # # # # # #     "Be empathetic, non-judgmental, and gently encourage therapy when needed."
# # # # # # # # # # # # # # # # # )

# # # # # # # # # # # # # # # # # # -------------------------
# # # # # # # # # # # # # # # # # # Flask app
# # # # # # # # # # # # # # # # # # -------------------------
# # # # # # # # # # # # # # # # # app = Flask(__name__)
# # # # # # # # # # # # # # # # # CORS(app)


# # # # # # # # # # # # # # # # # # -------------------------
# # # # # # # # # # # # # # # # # # Utility helpers
# # # # # # # # # # # # # # # # # # -------------------------
# # # # # # # # # # # # # # # # # def safe_json(obj):
# # # # # # # # # # # # # # # # #     try:
# # # # # # # # # # # # # # # # #         return json.dumps(obj, ensure_ascii=False)
# # # # # # # # # # # # # # # # #     except Exception:
# # # # # # # # # # # # # # # # #         return json.dumps({"error": "serialization error"})


# # # # # # # # # # # # # # # # # def check_local_llm_available() -> bool:
# # # # # # # # # # # # # # # # #     if not LOCAL_LLM_ENABLED:
# # # # # # # # # # # # # # # # #         return False
# # # # # # # # # # # # # # # # #     try:
# # # # # # # # # # # # # # # # #         # a small GET/HEAD check if supported
# # # # # # # # # # # # # # # # #         r = requests.get(LOCAL_LLM_URL, timeout=2)
# # # # # # # # # # # # # # # # #         # many local LLM servers will return 405 or 200; we consider any response as "available"
# # # # # # # # # # # # # # # # #         return r.status_code < 500
# # # # # # # # # # # # # # # # #     except Exception:
# # # # # # # # # # # # # # # # #         return False


# # # # # # # # # # # # # # # # # def call_local_llm_once(user_text: str, system_prompt: str = SYSTEM_PROMPT, max_tokens: int = MAX_TOKENS) -> str:
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     Call a local LLM server expecting a "chat/completions" style request/response (common with LM Studio / Ollama).
# # # # # # # # # # # # # # # # #     Adjust payload structure if your local server uses a different API.
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     payload = {
# # # # # # # # # # # # # # # # #         "model": "local-model",
# # # # # # # # # # # # # # # # #         "messages": [
# # # # # # # # # # # # # # # # #             {"role": "system", "content": system_prompt},
# # # # # # # # # # # # # # # # #             {"role": "user", "content": user_text}
# # # # # # # # # # # # # # # # #         ],
# # # # # # # # # # # # # # # # #         "max_tokens": max_tokens,
# # # # # # # # # # # # # # # # #         "temperature": 0.7,
# # # # # # # # # # # # # # # # #         # "stream": False  # for non-streaming
# # # # # # # # # # # # # # # # #     }
# # # # # # # # # # # # # # # # #     try:
# # # # # # # # # # # # # # # # #         r = requests.post(LOCAL_LLM_URL, json=payload, timeout=TIMEOUT_SEC)
# # # # # # # # # # # # # # # # #         r.raise_for_status()
# # # # # # # # # # # # # # # # #         data = r.json()
# # # # # # # # # # # # # # # # #         # Compatible with chat-completions style: data.choices[0].message.content
# # # # # # # # # # # # # # # # #         # But many local servers vary; try multiple fallbacks.
# # # # # # # # # # # # # # # # #         if isinstance(data, dict):
# # # # # # # # # # # # # # # # #             if "choices" in data and len(data["choices"]) > 0:
# # # # # # # # # # # # # # # # #                 first = data["choices"][0]
# # # # # # # # # # # # # # # # #                 if "message" in first and "content" in first["message"]:
# # # # # # # # # # # # # # # # #                     return first["message"]["content"].strip()
# # # # # # # # # # # # # # # # #                 if "text" in first:
# # # # # # # # # # # # # # # # #                     return first["text"].strip()
# # # # # # # # # # # # # # # # #             # some servers return `output` or `result`
# # # # # # # # # # # # # # # # #             for key in ("output", "result", "response"):
# # # # # # # # # # # # # # # # #                 if key in data and isinstance(data[key], str):
# # # # # # # # # # # # # # # # #                     return data[key].strip()
# # # # # # # # # # # # # # # # #         # fallback: return raw text
# # # # # # # # # # # # # # # # #         return r.text.strip()
# # # # # # # # # # # # # # # # #     except Exception as e:
# # # # # # # # # # # # # # # # #         log.exception("Local LLM call failed")
# # # # # # # # # # # # # # # # #         raise


# # # # # # # # # # # # # # # # # def stream_local_llm(user_text: str, system_prompt: str = SYSTEM_PROMPT, max_tokens: int = MAX_TOKENS):
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     Attempt streaming from local LLM if supported. We send stream=True if server supports it.
# # # # # # # # # # # # # # # # #     We'll yield SSE chunks.
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     payload = {
# # # # # # # # # # # # # # # # #         "model": "local-model",
# # # # # # # # # # # # # # # # #         "messages": [
# # # # # # # # # # # # # # # # #             {"role": "system", "content": system_prompt},
# # # # # # # # # # # # # # # # #             {"role": "user", "content": user_text}
# # # # # # # # # # # # # # # # #         ],
# # # # # # # # # # # # # # # # #         "max_tokens": max_tokens,
# # # # # # # # # # # # # # # # #         "temperature": 0.7,
# # # # # # # # # # # # # # # # #         "stream": True
# # # # # # # # # # # # # # # # #     }
# # # # # # # # # # # # # # # # #     try:
# # # # # # # # # # # # # # # # #         with requests.post(LOCAL_LLM_URL, json=payload, stream=True, timeout=(5, None)) as r:
# # # # # # # # # # # # # # # # #             r.raise_for_status()
# # # # # # # # # # # # # # # # #             # Many streaming LLM servers produce SSE or line-delimited JSON
# # # # # # # # # # # # # # # # #             for raw in r.iter_lines(decode_unicode=True):
# # # # # # # # # # # # # # # # #                 if raw is None:
# # # # # # # # # # # # # # # # #                     continue
# # # # # # # # # # # # # # # # #                 raw = raw.strip()
# # # # # # # # # # # # # # # # #                 if not raw:
# # # # # # # # # # # # # # # # #                     continue
# # # # # # # # # # # # # # # # #                 # Try parsing line-delimited JSON
# # # # # # # # # # # # # # # # #                 try:
# # # # # # # # # # # # # # # # #                     # Some servers send "data: {...}" or plain JSON
# # # # # # # # # # # # # # # # #                     line = raw
# # # # # # # # # # # # # # # # #                     if line.startswith("data:"):
# # # # # # # # # # # # # # # # #                         line = line[len("data:"):].strip()
# # # # # # # # # # # # # # # # #                     if line == "[DONE]":
# # # # # # # # # # # # # # # # #                         yield {"done": True}
# # # # # # # # # # # # # # # # #                         break
# # # # # # # # # # # # # # # # #                     obj = json.loads(line)
# # # # # # # # # # # # # # # # #                     # choose best keys
# # # # # # # # # # # # # # # # #                     if "choices" in obj:
# # # # # # # # # # # # # # # # #                         # streaming choices often contain delta
# # # # # # # # # # # # # # # # #                         ch = obj["choices"][0]
# # # # # # # # # # # # # # # # #                         if "delta" in ch:
# # # # # # # # # # # # # # # # #                             # delta may contain message/role/content
# # # # # # # # # # # # # # # # #                             delta = ch["delta"]
# # # # # # # # # # # # # # # # #                             if "content" in delta:
# # # # # # # # # # # # # # # # #                                 yield {"text": delta["content"]}
# # # # # # # # # # # # # # # # #                         elif "text" in ch:
# # # # # # # # # # # # # # # # #                             yield {"text": ch["text"]}
# # # # # # # # # # # # # # # # #                     elif "text" in obj:
# # # # # # # # # # # # # # # # #                         yield {"text": obj["text"]}
# # # # # # # # # # # # # # # # #                     else:
# # # # # # # # # # # # # # # # #                         # unknown JSON -> send as raw
# # # # # # # # # # # # # # # # #                         yield {"raw": line}
# # # # # # # # # # # # # # # # #                 except json.JSONDecodeError:
# # # # # # # # # # # # # # # # #                     # some servers stream plain text lines
# # # # # # # # # # # # # # # # #                     yield {"text": raw}
# # # # # # # # # # # # # # # # #     except Exception:
# # # # # # # # # # # # # # # # #         log.exception("Streaming local LLM failed")
# # # # # # # # # # # # # # # # #         raise


# # # # # # # # # # # # # # # # # def call_openai_once(user_text: str, system_prompt: str = SYSTEM_PROMPT, max_tokens: int = MAX_TOKENS) -> str:
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     Call OpenAI Chat Completions via REST. Use OPENAI_API_KEY env var.
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     if not OPENAI_API_KEY:
# # # # # # # # # # # # # # # # #         raise RuntimeError("OpenAI API key not set")
# # # # # # # # # # # # # # # # #     url = "https://api.openai.com/v1/chat/completions"
# # # # # # # # # # # # # # # # #     payload = {
# # # # # # # # # # # # # # # # #         "model": "gpt-4o-mini" if True else "gpt-4o",
# # # # # # # # # # # # # # # # #         "messages": [
# # # # # # # # # # # # # # # # #             {"role": "system", "content": system_prompt},
# # # # # # # # # # # # # # # # #             {"role": "user", "content": user_text}
# # # # # # # # # # # # # # # # #         ],
# # # # # # # # # # # # # # # # #         "max_tokens": max_tokens,
# # # # # # # # # # # # # # # # #         "temperature": 0.7
# # # # # # # # # # # # # # # # #     }
# # # # # # # # # # # # # # # # #     headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
# # # # # # # # # # # # # # # # #     r = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT_SEC)
# # # # # # # # # # # # # # # # #     r.raise_for_status()
# # # # # # # # # # # # # # # # #     data = r.json()
# # # # # # # # # # # # # # # # #     if "choices" in data and len(data["choices"]) > 0:
# # # # # # # # # # # # # # # # #         c = data["choices"][0]
# # # # # # # # # # # # # # # # #         if "message" in c and "content" in c["message"]:
# # # # # # # # # # # # # # # # #             return c["message"]["content"].strip()
# # # # # # # # # # # # # # # # #         if "text" in c:
# # # # # # # # # # # # # # # # #             return c["text"].strip()
# # # # # # # # # # # # # # # # #     # fallback
# # # # # # # # # # # # # # # # #     return r.text.strip()


# # # # # # # # # # # # # # # # # def stream_openai(user_text: str, system_prompt: str = SYSTEM_PROMPT, max_tokens: int = MAX_TOKENS):
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     Stream from OpenAI Chat completions (server-sent events).
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     if not OPENAI_API_KEY:
# # # # # # # # # # # # # # # # #         raise RuntimeError("OpenAI API key not set")
# # # # # # # # # # # # # # # # #     url = "https://api.openai.com/v1/chat/completions"
# # # # # # # # # # # # # # # # #     payload = {
# # # # # # # # # # # # # # # # #         "model": "gpt-4o-mini",
# # # # # # # # # # # # # # # # #         "messages": [
# # # # # # # # # # # # # # # # #             {"role": "system", "content": system_prompt},
# # # # # # # # # # # # # # # # #             {"role": "user", "content": user_text}
# # # # # # # # # # # # # # # # #         ],
# # # # # # # # # # # # # # # # #         "max_tokens": max_tokens,
# # # # # # # # # # # # # # # # #         "temperature": 0.7,
# # # # # # # # # # # # # # # # #         "stream": True
# # # # # # # # # # # # # # # # #     }
# # # # # # # # # # # # # # # # #     headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
# # # # # # # # # # # # # # # # #     with requests.post(url, json=payload, headers=headers, stream=True, timeout=(5, None)) as r:
# # # # # # # # # # # # # # # # #         r.raise_for_status()
# # # # # # # # # # # # # # # # #         for line in r.iter_lines(decode_unicode=True):
# # # # # # # # # # # # # # # # #             if not line:
# # # # # # # # # # # # # # # # #                 continue
# # # # # # # # # # # # # # # # #             line = line.strip()
# # # # # # # # # # # # # # # # #             if line.startswith("data:"):
# # # # # # # # # # # # # # # # #                 payload_line = line[len("data:"):].strip()
# # # # # # # # # # # # # # # # #             else:
# # # # # # # # # # # # # # # # #                 payload_line = line
# # # # # # # # # # # # # # # # #             if payload_line == "[DONE]":
# # # # # # # # # # # # # # # # #                 yield {"done": True}
# # # # # # # # # # # # # # # # #                 break
# # # # # # # # # # # # # # # # #             try:
# # # # # # # # # # # # # # # # #                 obj = json.loads(payload_line)
# # # # # # # # # # # # # # # # #                 # openai streaming: obj.choices[0].delta.content
# # # # # # # # # # # # # # # # #                 if "choices" in obj:
# # # # # # # # # # # # # # # # #                     ch = obj["choices"][0]
# # # # # # # # # # # # # # # # #                     if "delta" in ch and "content" in ch["delta"]:
# # # # # # # # # # # # # # # # #                         yield {"text": ch["delta"]["content"]}
# # # # # # # # # # # # # # # # #                     elif "text" in ch:
# # # # # # # # # # # # # # # # #                         yield {"text": ch["text"]}
# # # # # # # # # # # # # # # # #                 else:
# # # # # # # # # # # # # # # # #                     yield {"raw": payload_line}
# # # # # # # # # # # # # # # # #             except json.JSONDecodeError:
# # # # # # # # # # # # # # # # #                 yield {"text": payload_line}


# # # # # # # # # # # # # # # # # # -------------------------
# # # # # # # # # # # # # # # # # # Fallback rule-based assistant (offline)
# # # # # # # # # # # # # # # # # # -------------------------
# # # # # # # # # # # # # # # # # def fallback_therapy_reply(user_text: str) -> str:
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     A safe, short, empathetic rule-based fallback reply.
# # # # # # # # # # # # # # # # #     This is used when no LLM is available.
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     t = (user_text or "").lower()
# # # # # # # # # # # # # # # # #     # highest priority: self-harm
# # # # # # # # # # # # # # # # #     if any(kw in t for kw in ["suicide", "kill myself", "end my life", "want to die", "hurt myself"]):
# # # # # # # # # # # # # # # # #         return ("I'm really sorry you're feeling this way. If you are thinking of harming yourself, "
# # # # # # # # # # # # # # # # #                 "please contact emergency services or a crisis hotline immediately. "
# # # # # # # # # # # # # # # # #                 "I can help find local resources — would you like that?")
# # # # # # # # # # # # # # # # #     # anxiety
# # # # # # # # # # # # # # # # #     if any(kw in t for kw in ["anxious", "anxiety", "panic", "panic attack", "worried", "overthinking"]):
# # # # # # # # # # # # # # # # #         return ("It sounds like anxiety is troubling you. Try slow breathing: inhale 4s, exhale 6s for 2-3 minutes. "
# # # # # # # # # # # # # # # # #                 "If this continues, therapy can help. Would you like coping tips or therapist options?")
# # # # # # # # # # # # # # # # #     # depression/sadness
# # # # # # # # # # # # # # # # #     if any(kw in t for kw in ["sad", "depress", "hopeless", "empty", "unmotivated"]):
# # # # # # # # # # # # # # # # #         return ("I'm sorry you're feeling low. Small steps like a short walk, regular sleep, or talking to someone "
# # # # # # # # # # # # # # # # #                 "may help. If this lasts for weeks, a therapist can support you — would you like help finding one?")
# # # # # # # # # # # # # # # # #     # burnout/stress
# # # # # # # # # # # # # # # # #     if any(kw in t for kw in ["burnout", "exhausted", "overwork", "stressed", "stress"]):
# # # # # # # # # # # # # # # # #         return ("Burnout and stress are tough. Try scheduling a short break and lowering one task. "
# # # # # # # # # # # # # # # # #                 "Therapy is helpful for long-term recovery — shall I show options?")
# # # # # # # # # # # # # # # # #     # relationship issues
# # # # # # # # # # # # # # # # #     if any(kw in t for kw in ["relationship", "partner", "breakup", "argued", "alone"]):
# # # # # # # # # # # # # # # # #         return ("Relationship stress can feel heavy. Talking to a therapist or counsellor helps many people. "
# # # # # # # # # # # # # # # # #                 "Would you like a short coping plan or resources?")
# # # # # # # # # # # # # # # # #     # default gentle reply
# # # # # # # # # # # # # # # # #     return ("I hear you. I'm here to support you. I can offer grounding exercises, short coping tips, "
# # # # # # # # # # # # # # # # #             "or help you find a therapist. What would you like?")

# # # # # # # # # # # # # # # # # # -------------------------
# # # # # # # # # # # # # # # # # # Endpoints
# # # # # # # # # # # # # # # # # # -------------------------


# # # # # # # # # # # # # # # # # @app.route("/health", methods=["GET"])
# # # # # # # # # # # # # # # # # def health():
# # # # # # # # # # # # # # # # #     """Simple health check for orchestration."""
# # # # # # # # # # # # # # # # #     info = {
# # # # # # # # # # # # # # # # #         "status": "ok",
# # # # # # # # # # # # # # # # #         "local_llm": check_local_llm_available(),
# # # # # # # # # # # # # # # # #         "openai": bool(OPENAI_API_KEY),
# # # # # # # # # # # # # # # # #         "prefer_local": PREFER_LOCAL
# # # # # # # # # # # # # # # # #     }
# # # # # # # # # # # # # # # # #     return jsonify(info)


# # # # # # # # # # # # # # # # # @app.route("/chat", methods=["POST"])
# # # # # # # # # # # # # # # # # def chat_once():
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     Synchronous chat endpoint that returns a single JSON reply.
# # # # # # # # # # # # # # # # #     Request JSON:
# # # # # # # # # # # # # # # # #       { "text": "<user message>", "prefer": "local|openai|auto" }
# # # # # # # # # # # # # # # # #     Response JSON:
# # # # # # # # # # # # # # # # #       { "reply": "<assistant reply>", "source": "local|openai|fallback", "meta": {...} }
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     payload = request.get_json(force=True, silent=True) or {}
# # # # # # # # # # # # # # # # #     user_text = (payload.get("text") or "").strip()
# # # # # # # # # # # # # # # # #     prefer = (payload.get("prefer") or "auto").lower()

# # # # # # # # # # # # # # # # #     if not user_text:
# # # # # # # # # # # # # # # # #         return jsonify({"error": "empty text"}), 400

# # # # # # # # # # # # # # # # #     # Attempt flow: prefer param -> preferred config -> auto-detect order
# # # # # # # # # # # # # # # # #     strategies = []
# # # # # # # # # # # # # # # # #     if prefer == "local":
# # # # # # # # # # # # # # # # #         strategies = ["local", "openai", "fallback"]
# # # # # # # # # # # # # # # # #     elif prefer == "openai":
# # # # # # # # # # # # # # # # #         strategies = ["openai", "local", "fallback"]
# # # # # # # # # # # # # # # # #     else:  # auto
# # # # # # # # # # # # # # # # #         if PREFER_LOCAL:
# # # # # # # # # # # # # # # # #             strategies = ["local", "openai", "fallback"]
# # # # # # # # # # # # # # # # #         else:
# # # # # # # # # # # # # # # # #             strategies = ["openai", "local", "fallback"]

# # # # # # # # # # # # # # # # #     reply = None
# # # # # # # # # # # # # # # # #     source = "fallback"
# # # # # # # # # # # # # # # # #     meta: Dict[str, Any] = {"strategies": strategies}

# # # # # # # # # # # # # # # # #     for s in strategies:
# # # # # # # # # # # # # # # # #         try:
# # # # # # # # # # # # # # # # #             if s == "local" and LOCAL_LLM_ENABLED and check_local_llm_available():
# # # # # # # # # # # # # # # # #                 reply = call_local_llm_once(user_text)
# # # # # # # # # # # # # # # # #                 source = "local"
# # # # # # # # # # # # # # # # #                 break
# # # # # # # # # # # # # # # # #             if s == "openai" and OPENAI_ENABLED:
# # # # # # # # # # # # # # # # #                 reply = call_openai_once(user_text)
# # # # # # # # # # # # # # # # #                 source = "openai"
# # # # # # # # # # # # # # # # #                 break
# # # # # # # # # # # # # # # # #         except Exception as e:
# # # # # # # # # # # # # # # # #             log.warning("Strategy %s failed: %s", s, str(e))
# # # # # # # # # # # # # # # # #             continue

# # # # # # # # # # # # # # # # #     if reply is None:
# # # # # # # # # # # # # # # # #         # fallback
# # # # # # # # # # # # # # # # #         reply = fallback_therapy_reply(user_text)
# # # # # # # # # # # # # # # # #         source = "fallback"

# # # # # # # # # # # # # # # # #     # Build response
# # # # # # # # # # # # # # # # #     res = {
# # # # # # # # # # # # # # # # #         "reply": reply,
# # # # # # # # # # # # # # # # #         "source": source,
# # # # # # # # # # # # # # # # #         "meta": meta
# # # # # # # # # # # # # # # # #     }
# # # # # # # # # # # # # # # # #     return jsonify(res)


# # # # # # # # # # # # # # # # # @app.route("/chat/stream", methods=["POST"])
# # # # # # # # # # # # # # # # # def chat_stream():
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     Streaming chat endpoint using SSE (text/event-stream).
# # # # # # # # # # # # # # # # #     Client must consume events (each event is JSON text).
# # # # # # # # # # # # # # # # #     Request JSON same as /chat.
# # # # # # # # # # # # # # # # #     """
# # # # # # # # # # # # # # # # #     payload = request.get_json(force=True, silent=True) or {}
# # # # # # # # # # # # # # # # #     user_text = (payload.get("text") or "").strip()
# # # # # # # # # # # # # # # # #     prefer = (payload.get("prefer") or "auto").lower()

# # # # # # # # # # # # # # # # #     if not user_text:
# # # # # # # # # # # # # # # # #         return jsonify({"error": "empty text"}), 400

# # # # # # # # # # # # # # # # #     def event_stream():
# # # # # # # # # # # # # # # # #         # decide strategies like /chat
# # # # # # # # # # # # # # # # #         if prefer == "local":
# # # # # # # # # # # # # # # # #             strategies = ["local", "openai", "fallback"]
# # # # # # # # # # # # # # # # #         elif prefer == "openai":
# # # # # # # # # # # # # # # # #             strategies = ["openai", "local", "fallback"]
# # # # # # # # # # # # # # # # #         else:
# # # # # # # # # # # # # # # # #             strategies = ["local", "openai", "fallback"] if PREFER_LOCAL else ["openai", "local", "fallback"]

# # # # # # # # # # # # # # # # #         used = None
# # # # # # # # # # # # # # # # #         # try streaming from local first
# # # # # # # # # # # # # # # # #         for s in strategies:
# # # # # # # # # # # # # # # # #             if s == "local" and LOCAL_LLM_ENABLED and check_local_llm_available():
# # # # # # # # # # # # # # # # #                 used = "local"
# # # # # # # # # # # # # # # # #                 try:
# # # # # # # # # # # # # # # # #                     # stream from local if possible
# # # # # # # # # # # # # # # # #                     for chunk in stream_local_llm(user_text):
# # # # # # # # # # # # # # # # #                         if "text" in chunk:
# # # # # # # # # # # # # # # # #                             # SSE event with data: JSON
# # # # # # # # # # # # # # # # #                             data = {"type": "partial", "text": chunk["text"], "source": "local"}
# # # # # # # # # # # # # # # # #                             yield f"data: {safe_json(data)}\n\n"
# # # # # # # # # # # # # # # # #                         elif "raw" in chunk:
# # # # # # # # # # # # # # # # #                             data = {"type": "partial", "raw": chunk["raw"], "source": "local"}
# # # # # # # # # # # # # # # # #                             yield f"data: {safe_json(data)}\n\n"
# # # # # # # # # # # # # # # # #                         elif "done" in chunk:
# # # # # # # # # # # # # # # # #                             yield f"data: {safe_json({'type': 'done', 'source': 'local'})}\n\n"
# # # # # # # # # # # # # # # # #                             return
# # # # # # # # # # # # # # # # #                     # if local streaming didn't yield but returned OK, try a final single call
# # # # # # # # # # # # # # # # #                 except Exception:
# # # # # # # # # # # # # # # # #                     log.exception("Local stream failed, will fallback to other strategies")
# # # # # # # # # # # # # # # # #                     used = None
# # # # # # # # # # # # # # # # #                     # try next strategy
# # # # # # # # # # # # # # # # #             if s == "openai" and OPENAI_ENABLED:
# # # # # # # # # # # # # # # # #                 used = "openai"
# # # # # # # # # # # # # # # # #                 try:
# # # # # # # # # # # # # # # # #                     for chunk in stream_openai(user_text):
# # # # # # # # # # # # # # # # #                         if "text" in chunk:
# # # # # # # # # # # # # # # # #                             data = {"type": "partial", "text": chunk["text"], "source": "openai"}
# # # # # # # # # # # # # # # # #                             yield f"data: {safe_json(data)}\n\n"
# # # # # # # # # # # # # # # # #                         elif "raw" in chunk:
# # # # # # # # # # # # # # # # #                             data = {"type": "partial", "raw": chunk["raw"], "source": "openai"}
# # # # # # # # # # # # # # # # #                             yield f"data: {safe_json(data)}\n\n"
# # # # # # # # # # # # # # # # #                         elif "done" in chunk:
# # # # # # # # # # # # # # # # #                             yield f"data: {safe_json({'type': 'done', 'source': 'openai'})}\n\n"
# # # # # # # # # # # # # # # # #                             return
# # # # # # # # # # # # # # # # #                 except Exception:
# # # # # # # # # # # # # # # # #                     log.exception("OpenAI streaming failed, will fallback")
# # # # # # # # # # # # # # # # #                     used = None
# # # # # # # # # # # # # # # # #             # continue

# # # # # # # # # # # # # # # # #         # If we reach here, streaming strategies were not available or failed -> fallback single reply
# # # # # # # # # # # # # # # # #         try:
# # # # # # # # # # # # # # # # #             reply = None
# # # # # # # # # # # # # # # # #             if LOCAL_LLM_ENABLED and check_local_llm_available():
# # # # # # # # # # # # # # # # #                 try:
# # # # # # # # # # # # # # # # #                     reply = call_local_llm_once(user_text)
# # # # # # # # # # # # # # # # #                     used = "local"
# # # # # # # # # # # # # # # # #                 except Exception:
# # # # # # # # # # # # # # # # #                     pass
# # # # # # # # # # # # # # # # #             if reply is None and OPENAI_ENABLED:
# # # # # # # # # # # # # # # # #                 try:
# # # # # # # # # # # # # # # # #                     reply = call_openai_once(user_text)
# # # # # # # # # # # # # # # # #                     used = "openai"
# # # # # # # # # # # # # # # # #                 except Exception:
# # # # # # # # # # # # # # # # #                     pass
# # # # # # # # # # # # # # # # #             if reply is None:
# # # # # # # # # # # # # # # # #                 reply = fallback_therapy_reply(user_text)
# # # # # # # # # # # # # # # # #                 used = "fallback"

# # # # # # # # # # # # # # # # #             # send final reply as single 'done' message
# # # # # # # # # # # # # # # # #             yield f"data: {safe_json({'type': 'done', 'text': reply, 'source': used})}\n\n"
# # # # # # # # # # # # # # # # #         except Exception:
# # # # # # # # # # # # # # # # #             log.exception("Final fallback failed")
# # # # # # # # # # # # # # # # #             yield f"data: {safe_json({'type': 'error', 'message': 'internal server error'})}\n\n"

# # # # # # # # # # # # # # # # #     return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

# # # # # # # # # # # # # # # # # # -------------------------
# # # # # # # # # # # # # # # # # # Run server
# # # # # # # # # # # # # # # # # # -------------------------
# # # # # # # # # # # # # # # # # if __name__ == "__main__":
# # # # # # # # # # # # # # # # #     log.info("Starting api_chat.py — chat API")
# # # # # # # # # # # # # # # # #     log.info("Local LLM enabled: %s; Local LLM URL: %s", LOCAL_LLM_ENABLED, LOCAL_LLM_URL)
# # # # # # # # # # # # # # # # #     log.info("OpenAI enabled: %s", OPENAI_ENABLED)
# # # # # # # # # # # # # # # # #     app.run(host=HOST, port=PORT, debug=False)



# # # # # # # # # # # # # # # # import json
# # # # # # # # # # # # # # # # import time
# # # # # # # # # # # # # # # # import requests
# # # # # # # # # # # # # # # # from flask import Flask, request, Response
# # # # # # # # # # # # # # # # from flask_cors import CORS

# # # # # # # # # # # # # # # # # ============================================
# # # # # # # # # # # # # # # # #  PREMIUM THERAPY CHAT API
# # # # # # # # # # # # # # # # #  by THE MIND MATTERS
# # # # # # # # # # # # # # # # # ============================================

# # # # # # # # # # # # # # # # app = Flask(__name__)
# # # # # # # # # # # # # # # # CORS(app)

# # # # # # # # # # # # # # # # # --------------------------------------------
# # # # # # # # # # # # # # # # #  LOCAL LLM SETTINGS
# # # # # # # # # # # # # # # # #  (LM Studio / Ollama / Text Generation WebUI)
# # # # # # # # # # # # # # # # # --------------------------------------------
# # # # # # # # # # # # # # # # LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"

# # # # # # # # # # # # # # # # # ============================================
# # # # # # # # # # # # # # # # # SYSTEM PROMPT — THIS MAKES BOT "THERAPIST-LIKE"
# # # # # # # # # # # # # # # # # ============================================
# # # # # # # # # # # # # # # # SYSTEM_PROMPT = """
# # # # # # # # # # # # # # # # You are "THE MIND MATTERS — Therapy Assistant".

# # # # # # # # # # # # # # # # Your behaviour:
# # # # # # # # # # # # # # # # - Warm, empathetic, deeply human tone.
# # # # # # # # # # # # # # # # - Use **simple, clean English** (no heavy psychology terms).
# # # # # # # # # # # # # # # # - Short paragraphs (2–4 lines max).
# # # # # # # # # # # # # # # # - Do NOT repeat the same reply style.
# # # # # # # # # # # # # # # # - Each response must feel UNIQUE & PERSONAL.
# # # # # # # # # # # # # # # # - Ask gentle follow-up questions.
# # # # # # # # # # # # # # # # - Recognize sadness, anxiety, overthinking, burnout, guilt, shame.

# # # # # # # # # # # # # # # # Rules:
# # # # # # # # # # # # # # # # 1. Do NOT list options like a machine.
# # # # # # # # # # # # # # # # 2. Do NOT copy previous responses.
# # # # # # # # # # # # # # # # 3. Adapt based on the LAST user message.
# # # # # # # # # # # # # # # # 4. If user says "yes", "ok", "hmm" — continue the topic smoothly.
# # # # # # # # # # # # # # # # 5. If user expresses self-harm → respond with crisis guidance, but calm tone.
# # # # # # # # # # # # # # # # 6. Never judge. Never dismiss feelings.

# # # # # # # # # # # # # # # # Therapeutic style:
# # # # # # # # # # # # # # # # - Reflective listening.
# # # # # # # # # # # # # # # # - Emotional validation.
# # # # # # # # # # # # # # # # - Soft suggestions, step-by-step.
# # # # # # # # # # # # # # # # - Focus on comfort, clarity, and grounding.

# # # # # # # # # # # # # # # # Your mission:
# # # # # # # # # # # # # # # # Help the user understand their emotions and suggest gentle next steps.
# # # # # # # # # # # # # # # # """

# # # # # # # # # # # # # # # # # ============================================
# # # # # # # # # # # # # # # # # Utility: Convert history to ChatML format
# # # # # # # # # # # # # # # # # ============================================
# # # # # # # # # # # # # # # # def build_message_list(history, user_input):
# # # # # # # # # # # # # # # #     msgs = [{"role": "system", "content": SYSTEM_PROMPT}]

# # # # # # # # # # # # # # # #     for msg in history:
# # # # # # # # # # # # # # # #         role = "assistant" if msg["role"] == "assistant" else "user"
# # # # # # # # # # # # # # # #         msgs.append({"role": role, "content": msg["text"]})

# # # # # # # # # # # # # # # #     msgs.append({"role": "user", "content": user_input})
# # # # # # # # # # # # # # # #     return msgs


# # # # # # # # # # # # # # # # # ============================================
# # # # # # # # # # # # # # # # # STREAMING CHAT ENDPOINT
# # # # # # # # # # # # # # # # # ============================================
# # # # # # # # # # # # # # # # @app.route("/chat/stream", methods=["POST"])
# # # # # # # # # # # # # # # # def chat_stream():
# # # # # # # # # # # # # # # #     data = request.json
# # # # # # # # # # # # # # # #     user_message = data.get("message", "")
# # # # # # # # # # # # # # # #     history = data.get("history", [])

# # # # # # # # # # # # # # # #     # Build message list
# # # # # # # # # # # # # # # #     messages = build_message_list(history, user_message)

# # # # # # # # # # # # # # # #     # LLM payload
# # # # # # # # # # # # # # # #     payload = {
# # # # # # # # # # # # # # # #         "model": "local-model",
# # # # # # # # # # # # # # # #         "messages": messages,
# # # # # # # # # # # # # # # #         "temperature": 0.85,      # more natural / less repetitive
# # # # # # # # # # # # # # # #         "top_p": 0.9,
# # # # # # # # # # # # # # # #         "max_tokens": 300,
# # # # # # # # # # # # # # # #         "stream": True
# # # # # # # # # # # # # # # #     }

# # # # # # # # # # # # # # # #     # Stream generator
# # # # # # # # # # # # # # # #     def generate_stream():
# # # # # # # # # # # # # # # #         try:
# # # # # # # # # # # # # # # #             with requests.post(LOCAL_LLM_URL, json=payload, stream=True) as r:
# # # # # # # # # # # # # # # #                 for line in r.iter_lines():
# # # # # # # # # # # # # # # #                     if not line:
# # # # # # # # # # # # # # # #                         continue

# # # # # # # # # # # # # # # #                     try:
# # # # # # # # # # # # # # # #                         # LM Studio returns: "data: {json}"
# # # # # # # # # # # # # # # #                         raw = line.decode("utf-8")
# # # # # # # # # # # # # # # #                         if not raw.startswith("data:"):
# # # # # # # # # # # # # # # #                             continue

# # # # # # # # # # # # # # # #                         content_json = json.loads(raw[5:].strip())
# # # # # # # # # # # # # # # #                         delta = content_json["choices"][0]["delta"].get("content", "")

# # # # # # # # # # # # # # # #                         if delta:
# # # # # # # # # # # # # # # #                             yield delta

# # # # # # # # # # # # # # # #                     except Exception as e:
# # # # # # # # # # # # # # # #                         continue

# # # # # # # # # # # # # # # #         except Exception as e:
# # # # # # # # # # # # # # # #             yield "\nSorry, something went wrong connecting to the model."

# # # # # # # # # # # # # # # #     return Response(generate_stream(), mimetype="text/plain")


# # # # # # # # # # # # # # # # # ============================================
# # # # # # # # # # # # # # # # # API STATUS CHECK
# # # # # # # # # # # # # # # # # ============================================
# # # # # # # # # # # # # # # # @app.route("/chat/status", methods=["GET"])
# # # # # # # # # # # # # # # # def status():
# # # # # # # # # # # # # # # #     return {"status": "ok", "model_url": LOCAL_LLM_URL}


# # # # # # # # # # # # # # # # # ============================================
# # # # # # # # # # # # # # # # # START SERVER
# # # # # # # # # # # # # # # # # ============================================
# # # # # # # # # # # # # # # # if __name__ == "__main__":
# # # # # # # # # # # # # # # #     print("🔥 THE MIND MATTERS — Therapy Chat API Running at http://127.0.0.1:5100")
# # # # # # # # # # # # # # # #     app.run(host="0.0.0.0", port=5100)





# # # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # # # api_chat.py — FINAL STABLE VERSION (The Mind Matters)
# # # # # # # # # # # # # # # # Chat endpoint for Therapy Assistant (streaming supported)
# # # # # # # # # # # # # # # # ============================================================

# # # # # # # # # # # # # # # import json
# # # # # # # # # # # # # # # import time
# # # # # # # # # # # # # # # import logging
# # # # # # # # # # # # # # # import requests
# # # # # # # # # # # # # # # from flask import Flask, request, Response, jsonify
# # # # # # # # # # # # # # # from flask_cors import CORS

# # # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # # # CONFIG
# # # # # # # # # # # # # # # # ============================================================

# # # # # # # # # # # # # # # LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"  # LM Studio/Ollama
# # # # # # # # # # # # # # # USE_LOCAL_LLM = True  # Set False if you want to use OpenAI instead

# # # # # # # # # # # # # # # # For fallback
# # # # # # # # # # # # # # # FALLBACK_RESPONSES = [
# # # # # # # # # # # # # # #     "I’m here with you. Tell me more about what you're feeling.",
# # # # # # # # # # # # # # #     "I understand this is difficult. What triggered this feeling?",
# # # # # # # # # # # # # # #     "You're not alone. I'm listening. What happened recently?",
# # # # # # # # # # # # # # #     "Thank you for sharing. What do you feel you need right now?"
# # # # # # # # # # # # # # # ]

# # # # # # # # # # # # # # # logging.basicConfig(level=logging.INFO)
# # # # # # # # # # # # # # # log = logging.getLogger("api_chat")


# # # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # # # FLASK SETUP
# # # # # # # # # # # # # # # # ============================================================

# # # # # # # # # # # # # # # app = Flask(__name__)
# # # # # # # # # # # # # # # CORS(app)


# # # # # # # # # # # # # # # @app.route("/", methods=["GET"])
# # # # # # # # # # # # # # # def home():
# # # # # # # # # # # # # # #     return {"status": "OK", "message": "THE MIND MATTERS — Chat API Running"}


# # # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # # # SAFE GENERATOR (never crashes)
# # # # # # # # # # # # # # # # ============================================================

# # # # # # # # # # # # # # # def safe_yield(text):
# # # # # # # # # # # # # # #     """Yield data in proper SSE format."""
# # # # # # # # # # # # # # #     return f"data: {text}\n\n"


# # # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # # # LOCAL LLM REQUEST
# # # # # # # # # # # # # # # # ============================================================

# # # # # # # # # # # # # # # def call_local_llm(messages):
# # # # # # # # # # # # # # #     """Call LM Studio or Ollama."""
# # # # # # # # # # # # # # #     try:
# # # # # # # # # # # # # # #         response = requests.post(
# # # # # # # # # # # # # # #             LOCAL_LLM_URL,
# # # # # # # # # # # # # # #             json={
# # # # # # # # # # # # # # #                 "model": "local-model",
# # # # # # # # # # # # # # #                 "messages": messages,
# # # # # # # # # # # # # # #                 "temperature": 0.7,
# # # # # # # # # # # # # # #                 "stream": True
# # # # # # # # # # # # # # #             },
# # # # # # # # # # # # # # #             timeout=10,
# # # # # # # # # # # # # # #             stream=True
# # # # # # # # # # # # # # #         )
# # # # # # # # # # # # # # #         response.raise_for_status()
# # # # # # # # # # # # # # #         return response

# # # # # # # # # # # # # # #     except Exception as e:
# # # # # # # # # # # # # # #         log.error(f"Local LLM error: {e}")
# # # # # # # # # # # # # # #         return None


# # # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # # # STREAM ENDPOINT
# # # # # # # # # # # # # # # # ============================================================

# # # # # # # # # # # # # # # @app.route("/chat/stream", methods=["POST"])
# # # # # # # # # # # # # # # def chat_stream():

# # # # # # # # # # # # # # #     data = request.json
# # # # # # # # # # # # # # #     user_msg = data.get("message", "").strip()

# # # # # # # # # # # # # # #     if not user_msg:
# # # # # # # # # # # # # # #         return jsonify({"error": "Message cannot be empty"}), 400

# # # # # # # # # # # # # # #     # Conversation format
# # # # # # # # # # # # # # #     messages = [
# # # # # # # # # # # # # # #         {"role": "system", "content": "You are a compassionate therapy assistant."},
# # # # # # # # # # # # # # #         {"role": "user", "content": user_msg}
# # # # # # # # # # # # # # #     ]

# # # # # # # # # # # # # # #     def stream_reply():

# # # # # # # # # # # # # # #         # Try local LLM
# # # # # # # # # # # # # # #         if USE_LOCAL_LLM:
# # # # # # # # # # # # # # #             response = call_local_llm(messages)
# # # # # # # # # # # # # # #             if response:
# # # # # # # # # # # # # # #                 for line in response.iter_lines():
# # # # # # # # # # # # # # #                     if not line:
# # # # # # # # # # # # # # #                         continue
# # # # # # # # # # # # # # #                     try:
# # # # # # # # # # # # # # #                         decoded = json.loads(line.decode("utf-8").replace("data: ", ""))
# # # # # # # # # # # # # # #                         token = decoded["choices"][0]["delta"].get("content", "")
# # # # # # # # # # # # # # #                         if token:
# # # # # # # # # # # # # # #                             yield safe_yield(token)
# # # # # # # # # # # # # # #                     except:
# # # # # # # # # # # # # # #                         continue

# # # # # # # # # # # # # # #                 yield safe_yield("[END]")
# # # # # # # # # # # # # # #                 return

# # # # # # # # # # # # # # #         # FALLBACK — if local LLM fails
# # # # # # # # # # # # # # #         fallback = FALLBACK_RESPONSES[int(time.time()) % len(FALLBACK_RESPONSES)]
# # # # # # # # # # # # # # #         for ch in fallback:
# # # # # # # # # # # # # # #             yield safe_yield(ch)
# # # # # # # # # # # # # # #             time.sleep(0.03)

# # # # # # # # # # # # # # #         yield safe_yield("[END]")

# # # # # # # # # # # # # # #     return Response(stream_reply(), mimetype="text/event-stream")


# # # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # # # RUN SERVER
# # # # # # # # # # # # # # # # ============================================================

# # # # # # # # # # # # # # # if __name__ == "__main__":
# # # # # # # # # # # # # # #     log.info("Starting api_chat.py — chat API")
# # # # # # # # # # # # # # #     log.info(f"Local LLM enabled: {USE_LOCAL_LLM}; URL: {LOCAL_LLM_URL}")

# # # # # # # # # # # # # # #     app.run(host="0.0.0.0", port=5100, debug=False)
# # # # # # # # # # # # # # # # ============================================================







# # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # # api_chat.py — FINAL FIXED VERSION (CORS + STREAM + FALLBACK)
# # # # # # # # # # # # # # # ============================================================

# # # # # # # # # # # # # # import json
# # # # # # # # # # # # # # import logging
# # # # # # # # # # # # # # from flask import Flask, request, Response, jsonify
# # # # # # # # # # # # # # from flask_cors import CORS
# # # # # # # # # # # # # # import requests

# # # # # # # # # # # # # # logging.basicConfig(level=logging.INFO)
# # # # # # # # # # # # # # log = logging.getLogger("api_chat")

# # # # # # # # # # # # # # app = Flask(__name__)
# # # # # # # # # # # # # # CORS(app)   # 🔥 FIX 1: Enables full CORS support

# # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # # CONFIG
# # # # # # # # # # # # # # # ============================================================

# # # # # # # # # # # # # # LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"
# # # # # # # # # # # # # # USE_LOCAL = True

# # # # # # # # # # # # # # log.info("Starting api_chat.py — chat API")
# # # # # # # # # # # # # # log.info(f"Local LLM enabled: {USE_LOCAL}; URL: {LOCAL_LLM_URL}")


# # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # # STREAMING CHAT ENDPOINT
# # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # @app.route("/chat/stream", methods=["POST"])
# # # # # # # # # # # # # # def chat_stream():
# # # # # # # # # # # # # #     try:
# # # # # # # # # # # # # #         data = request.get_json(silent=True)

# # # # # # # # # # # # # #         if not data or "text" not in data:
# # # # # # # # # # # # # #             return jsonify({"error": "Missing 'text' field"}), 400

# # # # # # # # # # # # # #         user_msg = data["text"].strip()
# # # # # # # # # # # # # #         if not user_msg:
# # # # # # # # # # # # # #             return jsonify({"error": "Empty message"}), 400

# # # # # # # # # # # # # #         log.info(f"[STREAM] User: {user_msg}")

# # # # # # # # # # # # # #         payload = {
# # # # # # # # # # # # # #             "model": "local-model",
# # # # # # # # # # # # # #             "messages": [
# # # # # # # # # # # # # #                 {"role": "user", "content": user_msg}
# # # # # # # # # # # # # #             ],
# # # # # # # # # # # # # #             "stream": True
# # # # # # # # # # # # # #         }

# # # # # # # # # # # # # #         # STREAM REQUEST TO LOCAL LLM
# # # # # # # # # # # # # #         def stream_generator():
# # # # # # # # # # # # # #             try:
# # # # # # # # # # # # # #                 with requests.post(
# # # # # # # # # # # # # #                     LOCAL_LLM_URL,
# # # # # # # # # # # # # #                     json=payload,
# # # # # # # # # # # # # #                     stream=True
# # # # # # # # # # # # # #                 ) as r:

# # # # # # # # # # # # # #                     for line in r.iter_lines():
# # # # # # # # # # # # # #                         if not line:
# # # # # # # # # # # # # #                             continue

# # # # # # # # # # # # # #                         try:
# # # # # # # # # # # # # #                             decoded = line.decode("utf-8")

# # # # # # # # # # # # # #                             if decoded.startswith("data:"):
# # # # # # # # # # # # # #                                 decoded = decoded[5:].strip()

# # # # # # # # # # # # # #                             yield f"{decoded}\n"

# # # # # # # # # # # # # #                         except Exception:
# # # # # # # # # # # # # #                             continue

# # # # # # # # # # # # # #             except Exception as e:
# # # # # # # # # # # # # #                 log.error(f"STREAM ERROR: {e}")
# # # # # # # # # # # # # #                 yield json.dumps({"text": "Sorry, streaming failed."}) + "\n"

# # # # # # # # # # # # # #         return Response(stream_generator(), mimetype="text/event-stream")

# # # # # # # # # # # # # #     except Exception as e:
# # # # # # # # # # # # # #         log.error(f"STREAM EXCEPTION: {e}")
# # # # # # # # # # # # # #         return jsonify({"error": "Chat streaming failed"}), 500


# # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # # NON-STREAM FALLBACK
# # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # @app.route("/chat", methods=["POST"])
# # # # # # # # # # # # # # def chat_single():
# # # # # # # # # # # # # #     try:
# # # # # # # # # # # # # #         data = request.get_json(silent=True)

# # # # # # # # # # # # # #         if not data or "text" not in data:
# # # # # # # # # # # # # #             return jsonify({"error": "Missing 'text'"}), 400

# # # # # # # # # # # # # #         user_msg = data["text"].strip()
# # # # # # # # # # # # # #         if not user_msg:
# # # # # # # # # # # # # #             return jsonify({"error": "Empty message"}), 400

# # # # # # # # # # # # # #         log.info(f"[FALLBACK] User: {user_msg}")

# # # # # # # # # # # # # #         payload = {
# # # # # # # # # # # # # #             "model": "local-model",
# # # # # # # # # # # # # #             "messages": [
# # # # # # # # # # # # # #                 {"role": "user", "content": user_msg}
# # # # # # # # # # # # # #             ]
# # # # # # # # # # # # # #         }

# # # # # # # # # # # # # #         r = requests.post(LOCAL_LLM_URL, json=payload)
# # # # # # # # # # # # # #         reply_json = r.json()

# # # # # # # # # # # # # #         # Try extracting content:
# # # # # # # # # # # # # #         reply = ""
# # # # # # # # # # # # # #         try:
# # # # # # # # # # # # # #             reply = reply_json["choices"][0]["message"]["content"]
# # # # # # # # # # # # # #         except:
# # # # # # # # # # # # # #             reply = reply_json.get("message") or reply_json.get("text") or "I'm here with you."

# # # # # # # # # # # # # #         return jsonify({"reply": reply})

# # # # # # # # # # # # # #     except Exception as e:
# # # # # # # # # # # # # #         log.error(f"CHAT ERROR: {e}")
# # # # # # # # # # # # # #         return jsonify({"error": "Chat error"}), 500


# # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # # ROOT
# # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # @app.route("/", methods=["GET"])
# # # # # # # # # # # # # # def home():
# # # # # # # # # # # # # #     return {"status": "OK", "message": "Chat API Running"}


# # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # # RUN
# # # # # # # # # # # # # # # ============================================================
# # # # # # # # # # # # # # if __name__ == "__main__":
# # # # # # # # # # # # # #     log.info("Chat server running on 127.0.0.1:5100 ...")
# # # # # # # # # # # # # #     app.run(host="0.0.0.0", port=5100, debug=False)





# # # # # # # # # # # # # # =====================================================================
# # # # # # # # # # # # # # api_chat.py  —  FULL FIXED VERSION (Streaming + CORS + Fallback)
# # # # # # # # # # # # # # =====================================================================

# # # # # # # # # # # # # import os
# # # # # # # # # # # # # import json
# # # # # # # # # # # # # import time
# # # # # # # # # # # # # import logging
# # # # # # # # # # # # # import requests
# # # # # # # # # # # # # from flask import Flask, request, Response, jsonify
# # # # # # # # # # # # # from flask_cors import CORS

# # # # # # # # # # # # # logging.basicConfig(level=logging.INFO)
# # # # # # # # # # # # # log = logging.getLogger("api_chat")

# # # # # # # # # # # # # app = Flask(__name__)

# # # # # # # # # # # # # # FULL CORS ENABLE
# # # # # # # # # # # # # CORS(app,
# # # # # # # # # # # # #      resources={r"/*": {"origins": "*"}},
# # # # # # # # # # # # #      supports_credentials=True,
# # # # # # # # # # # # #      allow_headers=["Content-Type"],
# # # # # # # # # # # # #      methods=["GET", "POST", "OPTIONS"]
# # # # # # # # # # # # # )

# # # # # # # # # # # # # # ==============================================================
# # # # # # # # # # # # # # SETTINGS
# # # # # # # # # # # # # # ==============================================================

# # # # # # # # # # # # # LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"
# # # # # # # # # # # # # USE_LOCAL = True     # True = LM Studio / Ollama / Local LLM
# # # # # # # # # # # # # USE_OPENAI = False   # Switch → False if no OpenAI key

# # # # # # # # # # # # # OPENAI_KEY = os.getenv("OPENAI_API_KEY", None)

# # # # # # # # # # # # # log.info("Starting api_chat.py — streaming chat server")
# # # # # # # # # # # # # log.info(f"Local LLM Enabled: {USE_LOCAL}; URL = {LOCAL_LLM_URL}")


# # # # # # # # # # # # # # ==============================================================
# # # # # # # # # # # # # # ROOT CHECK
# # # # # # # # # # # # # # ==============================================================

# # # # # # # # # # # # # @app.route("/", methods=["GET"])
# # # # # # # # # # # # # def home():
# # # # # # # # # # # # #     return {"status": "chat_api_ok"}


# # # # # # # # # # # # # # ==============================================================
# # # # # # # # # # # # # # STREAMING CHAT ENDPOINT
# # # # # # # # # # # # # # ==============================================================

# # # # # # # # # # # # # @app.route("/chat/stream", methods=["POST", "OPTIONS"])
# # # # # # # # # # # # # def chat_stream():

# # # # # # # # # # # # #     # Handle preflight OPTIONS request (IMPORTANT!)
# # # # # # # # # # # # #     if request.method == "OPTIONS":
# # # # # # # # # # # # #         return Response(status=200)

# # # # # # # # # # # # #     try:
# # # # # # # # # # # # #         data = request.get_json(silent=True) or {}
# # # # # # # # # # # # #         text = data.get("text", "").strip()

# # # # # # # # # # # # #         if not text:
# # # # # # # # # # # # #             return Response("data: {\"error\": \"empty text\"}\n\n", mimetype="text/event-stream")

# # # # # # # # # # # # #         # LOCAL LLM REQUEST BODY
# # # # # # # # # # # # #         payload = {
# # # # # # # # # # # # #             "model": "gpt-3.5-turbo",
# # # # # # # # # # # # #             "messages": [{"role": "user", "content": text}],
# # # # # # # # # # # # #             "max_tokens": 150,
# # # # # # # # # # # # #             "temperature": 0.8,
# # # # # # # # # # # # #             "stream": True
# # # # # # # # # # # # #         }

# # # # # # # # # # # # #         # STREAM GENERATOR
# # # # # # # # # # # # #         def generate():
# # # # # # # # # # # # #             try:
# # # # # # # # # # # # #                 with requests.post(
# # # # # # # # # # # # #                     LOCAL_LLM_URL,
# # # # # # # # # # # # #                     json=payload,
# # # # # # # # # # # # #                     stream=True,
# # # # # # # # # # # # #                     timeout=200
# # # # # # # # # # # # #                 ) as r:

# # # # # # # # # # # # #                     for line in r.iter_lines():
# # # # # # # # # # # # #                         if not line:
# # # # # # # # # # # # #                             continue

# # # # # # # # # # # # #                         decoded = line.decode("utf-8")

# # # # # # # # # # # # #                         if decoded.startswith("data:"):
# # # # # # # # # # # # #                             yield decoded + "\n"

# # # # # # # # # # # # #                         # LM Studio "text" key fallback
# # # # # # # # # # # # #                         elif decoded.startswith("{"):
# # # # # # # # # # # # #                             yield f"data: {decoded}\n"

# # # # # # # # # # # # #                         time.sleep(0.001)

# # # # # # # # # # # # #                 yield "data: [DONE]\n\n"

# # # # # # # # # # # # #             except Exception as e:
# # # # # # # # # # # # #                 log.error(f"Streaming error: {e}")
# # # # # # # # # # # # #                 yield f"data: {{\"error\": \"stream_failed\", \"detail\": \"{str(e)}\"}}\n\n"

# # # # # # # # # # # # #         return Response(generate(), mimetype="text/event-stream")

# # # # # # # # # # # # #     except Exception as ex:
# # # # # # # # # # # # #         return jsonify({"error": "fatal_error", "detail": str(ex)}), 500


# # # # # # # # # # # # # # ==============================================================
# # # # # # # # # # # # # # NON-STREAM (fallback)
# # # # # # # # # # # # # # ==============================================================

# # # # # # # # # # # # # @app.route("/chat", methods=["POST"])
# # # # # # # # # # # # # def chat_once():
# # # # # # # # # # # # #     try:
# # # # # # # # # # # # #         data = request.get_json(silent=True) or {}
# # # # # # # # # # # # #         text = data.get("text", "").strip()

# # # # # # # # # # # # #         if not text:
# # # # # # # # # # # # #             return jsonify({"reply": "I didn't receive any message."})

# # # # # # # # # # # # #         payload = {
# # # # # # # # # # # # #             "model": "gpt-3.5-turbo",
# # # # # # # # # # # # #             "messages": [{"role": "user", "content": text}],
# # # # # # # # # # # # #             "max_tokens": 150,
# # # # # # # # # # # # #             "temperature": 0.7
# # # # # # # # # # # # #         }

# # # # # # # # # # # # #         r = requests.post(LOCAL_LLM_URL, json=payload)
# # # # # # # # # # # # #         j = r.json()

# # # # # # # # # # # # #         reply = ""
# # # # # # # # # # # # #         try:
# # # # # # # # # # # # #             reply = j["choices"][0]["message"]["content"]
# # # # # # # # # # # # #         except:
# # # # # # # # # # # # #             reply = str(j)

# # # # # # # # # # # # #         return jsonify({"reply": reply})

# # # # # # # # # # # # #     except Exception as e:
# # # # # # # # # # # # #         return jsonify({"error": "chat_failed", "detail": str(e)})


# # # # # # # # # # # # # # ==============================================================
# # # # # # # # # # # # # # RUN
# # # # # # # # # # # # # # ==============================================================

# # # # # # # # # # # # # if __name__ == "__main__":
# # # # # # # # # # # # #     app.run(host="0.0.0.0", port=5100, debug=False)
# # # # # # # # # # # # # # =====================================================================




# # # # # # # # # # # # # ================================================
# # # # # # # # # # # # # FINAL — api_chat.py (STABLE STREAMING VERSION)
# # # # # # # # # # # # # ================================================

# # # # # # # # # # # # import time
# # # # # # # # # # # # import json
# # # # # # # # # # # # from flask import Flask, request, Response, jsonify
# # # # # # # # # # # # from flask_cors import CORS
# # # # # # # # # # # # import logging

# # # # # # # # # # # # # ------------------------------------------------
# # # # # # # # # # # # # SETUP
# # # # # # # # # # # # # ------------------------------------------------
# # # # # # # # # # # # app = Flask(__name__)
# # # # # # # # # # # # CORS(app)

# # # # # # # # # # # # logging.basicConfig(level=logging.INFO)
# # # # # # # # # # # # log = logging.getLogger("api_chat")

# # # # # # # # # # # # log.info("Starting api_chat.py — chat API")

# # # # # # # # # # # # # Dummy replies (you can replace with real LLM later)
# # # # # # # # # # # # def generate_reply(user_text):
# # # # # # # # # # # #     """Non-streaming reply (fallback)."""
# # # # # # # # # # # #     return f"I understand you said: '{user_text}'. How does that make you feel?"

# # # # # # # # # # # # def streaming_generator(user_text):
# # # # # # # # # # # #     """Streaming (SSE-like) response generator."""
# # # # # # # # # # # #     chunks = [
# # # # # # # # # # # #         "Okay, I hear you. ",
# # # # # # # # # # # #         "You are feeling like this: ",
# # # # # # # # # # # #         user_text,
# # # # # # # # # # # #         ". ",
# # # # # # # # # # # #         "I'm here to support you. ",
# # # # # # # # # # # #         "Tell me more..."
# # # # # # # # # # # #     ]

# # # # # # # # # # # #     for ch in chunks:
# # # # # # # # # # # #         data = json.dumps({"text": ch})
# # # # # # # # # # # #         yield f"data: {data}\n\n"
# # # # # # # # # # # #         time.sleep(0.25)


# # # # # # # # # # # # # ------------------------------------------------
# # # # # # # # # # # # # ROUTE: /chat/stream  (MAIN ENDPOINT)
# # # # # # # # # # # # # ------------------------------------------------
# # # # # # # # # # # # @app.route("/chat/stream", methods=["POST"])
# # # # # # # # # # # # def chat_stream():
# # # # # # # # # # # #     data = request.json or {}
# # # # # # # # # # # #     text = data.get("text", "").strip()

# # # # # # # # # # # #     if not text:
# # # # # # # # # # # #         log.error("Empty text received → returning 400")
# # # # # # # # # # # #         return jsonify({"error": "No text provided"}), 400

# # # # # # # # # # # #     log.info(f"Streaming chat request: {text}")

# # # # # # # # # # # #     return Response(streaming_generator(text),
# # # # # # # # # # # #                     mimetype="text/event-stream")


# # # # # # # # # # # # # ------------------------------------------------
# # # # # # # # # # # # # ROUTE: /chat  (fallback non-streaming)
# # # # # # # # # # # # # ------------------------------------------------
# # # # # # # # # # # # @app.route("/chat", methods=["POST"])
# # # # # # # # # # # # def chat_once():
# # # # # # # # # # # #     data = request.json or {}
# # # # # # # # # # # #     text = data.get("text", "").strip()

# # # # # # # # # # # #     if not text:
# # # # # # # # # # # #         return jsonify({"error": "No text provided"}), 400

# # # # # # # # # # # #     reply = generate_reply(text)
# # # # # # # # # # # #     return jsonify({"reply": reply})


# # # # # # # # # # # # # ------------------------------------------------
# # # # # # # # # # # # # TEST ROUTE
# # # # # # # # # # # # # ------------------------------------------------
# # # # # # # # # # # # @app.route("/", methods=["GET"])
# # # # # # # # # # # # def home():
# # # # # # # # # # # #     return {"status": "OK", "message": "Chat server running on 5100"}


# # # # # # # # # # # # # ------------------------------------------------
# # # # # # # # # # # # # START SERVER
# # # # # # # # # # # # # ------------------------------------------------
# # # # # # # # # # # # if __name__ == "__main__":
# # # # # # # # # # # #     print("Running chat API on http://127.0.0.1:5100 ...")
# # # # # # # # # # # #     app.run(host="0.0.0.0", port=5100, debug=False)
# # # # # # # # # # # # # ================================================





# # # # # # # # # # # # ===================================================================
# # # # # # # # # # # # api_chat.py — Therapy-aware chat API (streaming + analysis-aware)
# # # # # # # # # # # # ===================================================================
# # # # # # # # # # # # - Reads optional `analysis` JSON sent by the frontend (the output of api.py)
# # # # # # # # # # # # - If analysis indicates moderate/severe risk or repeated concerns, the
# # # # # # # # # # # #   assistant will recommend **paid therapy with "MindMatters"** (your brand)
# # # # # # # # # # # # - Streaming endpoint (/chat/stream) and fallback endpoint (/chat)
# # # # # # # # # # # # - Robust: will attempt to call a local LLM if configured; otherwise uses
# # # # # # # # # # # #   a smart offline reasoning fallback that produces varied, counselling-style replies
# # # # # # # # # # # #
# # # # # # # # # # # # USAGE:
# # # # # # # # # # # #   python api_chat.py
# # # # # # # # # # # # The frontend should POST JSON like:
# # # # # # # # # # # #   { "text": "I feel anxious", "analysis": { "mental_state": "...", "severity": "...", ... } }
# # # # # # # # # # # #
# # # # # # # # # # # # ===================================================================

# # # # # # # # # # # import time
# # # # # # # # # # # import json
# # # # # # # # # # # import logging
# # # # # # # # # # # import random
# # # # # # # # # # # from typing import Dict, Any
# # # # # # # # # # # from flask import Flask, request, Response, jsonify
# # # # # # # # # # # from flask_cors import CORS

# # # # # # # # # # # # -------------------------
# # # # # # # # # # # # Configuration
# # # # # # # # # # # # -------------------------
# # # # # # # # # # # LOCAL_LLM_ENABLED = False
# # # # # # # # # # # LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"  # if using LM Studio / Ollama set True and run server
# # # # # # # # # # # SERVER_PORT = 5100
# # # # # # # # # # # STREAM_DELAY = 0.18  # seconds between simulated chunks for fallback streaming

# # # # # # # # # # # # Therapy recommendation thresholds
# # # # # # # # # # # THERAPY_TRIGGER_SEVERITIES = {"moderate", "severe"}
# # # # # # # # # # # THERAPY_TRIGGER_RISKS = {"moderate", "high"}
# # # # # # # # # # # THERAPY_TRIGGER_INDICATOR_COUNT = 2  # if many indicators, suggest therapy

# # # # # # # # # # # # Simple persistent "seen concern" counter in memory (resets when process restarts)
# # # # # # # # # # # USER_STATE: Dict[str, Dict[str, Any]] = {}
# # # # # # # # # # # # Example usage: USER_STATE["default"] = {"concern_count": 0}

# # # # # # # # # # # # -------------------------
# # # # # # # # # # # # App init
# # # # # # # # # # # # -------------------------
# # # # # # # # # # # app = Flask(__name__)
# # # # # # # # # # # CORS(app, resources={r"/*": {"origins": "*"}})
# # # # # # # # # # # logging.basicConfig(level=logging.INFO)
# # # # # # # # # # # log = logging.getLogger("api_chat")

# # # # # # # # # # # log.info("Starting api_chat.py — therapy-aware chat API")
# # # # # # # # # # # log.info(f"Local LLM enabled: {LOCAL_LLM_ENABLED}; Local LLM URL: {LOCAL_LLM_URL}")

# # # # # # # # # # # # -------------------------
# # # # # # # # # # # # Utilities
# # # # # # # # # # # # -------------------------
# # # # # # # # # # # def safe_get_analysis_field(analysis: Dict[str, Any], key: str, default=None):
# # # # # # # # # # #     if not analysis:
# # # # # # # # # # #         return default
# # # # # # # # # # #     return analysis.get(key, default)

# # # # # # # # # # # def join_indicators(indicators):
# # # # # # # # # # #     if not indicators:
# # # # # # # # # # #         return "none"
# # # # # # # # # # #     if isinstance(indicators, list):
# # # # # # # # # # #         return ", ".join(indicators)
# # # # # # # # # # #     if isinstance(indicators, str):
# # # # # # # # # # #         return indicators
# # # # # # # # # # #     return str(indicators)

# # # # # # # # # # # def escalate_needed(analysis: Dict[str, Any]) -> bool:
# # # # # # # # # # #     """Return True if therapy recommendation should be strongly suggested."""
# # # # # # # # # # #     if not analysis:
# # # # # # # # # # #         return False
# # # # # # # # # # #     sev = str(safe_get_analysis_field(analysis, "severity", "")).lower()
# # # # # # # # # # #     risk = str(safe_get_analysis_field(analysis, "suicide_risk", "")).lower()
# # # # # # # # # # #     indicators = safe_get_analysis_field(analysis, "indicators", []) or []
# # # # # # # # # # #     if sev in THERAPY_TRIGGER_SEVERITIES:
# # # # # # # # # # #         return True
# # # # # # # # # # #     if risk in THERAPY_TRIGGER_RISKS:
# # # # # # # # # # #         return True
# # # # # # # # # # #     if isinstance(indicators, (list, tuple)) and len(indicators) >= THERAPY_TRIGGER_INDICATOR_COUNT:
# # # # # # # # # # #         return True
# # # # # # # # # # #     return False

# # # # # # # # # # # def therapy_recommendation_text(analysis: Dict[str, Any]) -> str:
# # # # # # # # # # #     """Return a polite, strong therapy recommendation message based on analysis."""
# # # # # # # # # # #     parts = []
# # # # # # # # # # #     sev = str(safe_get_analysis_field(analysis, "severity", "")).lower()
# # # # # # # # # # #     mental = str(safe_get_analysis_field(analysis, "mental_state", "")).lower()
# # # # # # # # # # #     risk = str(safe_get_analysis_field(analysis, "suicide_risk", "")).lower()
# # # # # # # # # # #     indicators = safe_get_analysis_field(analysis, "indicators", []) or []

# # # # # # # # # # #     parts.append("Based on the recent analysis, I recommend considering professional therapy with MindMatters.")
# # # # # # # # # # #     if sev in ("moderate", "severe"):
# # # # # # # # # # #         parts.append("Your severity level shows moderate-to-high emotional intensity; therapy can offer structured, long-term support.")
# # # # # # # # # # #     if risk in ("moderate", "high"):
# # # # # # # # # # #         parts.append("There are concerning risk signals. Please contact a therapist or local emergency services immediately if you feel unsafe.")
# # # # # # # # # # #     if mental:
# # # # # # # # # # #         parts.append(f"This analysis flagged: {mental}. A therapist can help you work through this with evidence-based approaches.")
# # # # # # # # # # #     if indicators:
# # # # # # # # # # #         parts.append(f"Observed indicators: {join_indicators(indicators)} — therapy often helps address these.")

# # # # # # # # # # #     # Call to action with brand & help
# # # # # # # # # # #     parts.append("Would you like me to help you find a paid MindMatters therapy session and prepare a short message to share with the therapist?")
# # # # # # # # # # #     return " ".join(parts)

# # # # # # # # # # # def friendly_clinical_opening(analysis: Dict[str, Any]) -> str:
# # # # # # # # # # #     """Return an opening sentence for the assistant rooted in the analysis context."""
# # # # # # # # # # #     if not analysis:
# # # # # # # # # # #         return random.choice([
# # # # # # # # # # #             "Thanks for sharing — I'm here to listen. Can you tell me more about what's been happening?",
# # # # # # # # # # #             "I hear you. Tell me a little about how often this has been happening."
# # # # # # # # # # #         ])
# # # # # # # # # # #     mental = str(safe_get_analysis_field(analysis, "mental_state", "")).lower()
# # # # # # # # # # #     emotion = str(safe_get_analysis_field(analysis, "emotion", "")).lower()
# # # # # # # # # # #     sev = str(safe_get_analysis_field(analysis, "severity", "")).lower()
# # # # # # # # # # #     risk = str(safe_get_analysis_field(analysis, "suicide_risk", "")).lower()
# # # # # # # # # # #     indicators = safe_get_analysis_field(analysis, "indicators", []) or []

# # # # # # # # # # #     # Compose empathetic contextual lines
# # # # # # # # # # #     lines = []
# # # # # # # # # # #     if mental:
# # # # # # # # # # #         lines.append(f"I see the analyzer detected *{mental}* — that can feel heavy. ")
# # # # # # # # # # #     if emotion:
# # # # # # # # # # #         lines.append(f"It also detected feelings of *{emotion}*. ")
# # # # # # # # # # #     if sev:
# # # # # # # # # # #         lines.append(f"Severity looks *{sev}* — I'll be careful and supportive. ")
# # # # # # # # # # #     if indicators:
# # # # # # # # # # #         lines.append(f"I noticed indicators like {join_indicators(indicators)}. ")

# # # # # # # # # # #     if lines:
# # # # # # # # # # #         # Combine with a follow-up question
# # # # # # # # # # #         lines.append("Would you like some immediate grounding exercises, or would you prefer to talk through what's been triggering this?")
# # # # # # # # # # #         return " ".join(lines)

# # # # # # # # # # #     return "Thanks for sharing — tell me more about what you've noticed recently."

# # # # # # # # # # # # -------------------------
# # # # # # # # # # # # Smart offline reply generator
# # # # # # # # # # # # -------------------------
# # # # # # # # # # # def make_offline_reply(user_text: str, analysis: Dict[str, Any], user_id: str = "default"):
# # # # # # # # # # #     """
# # # # # # # # # # #     Create a varied, context-sensitive counselling reply.
# # # # # # # # # # #     This is used when no LLM is available.
# # # # # # # # # # #     """
# # # # # # # # # # #     # Keep a small user-state to detect repeated concerns
# # # # # # # # # # #     st = USER_STATE.setdefault(user_id, {"concern_count": 0})
# # # # # # # # # # #     st["concern_count"] = st.get("concern_count", 0) + 1

# # # # # # # # # # #     open_line = friendly_clinical_opening(analysis)
# # # # # # # # # # #     followups = []

# # # # # # # # # # #     # Triage suggestions
# # # # # # # # # # #     if escalate_needed(analysis):
# # # # # # # # # # #         # Strong recommendation to consider paid therapy + short immediate supports
# # # # # # # # # # #         followups.append(therapy_recommendation_text(analysis))
# # # # # # # # # # #         # offer a small immediate coping step
# # # # # # # # # # #         followups.append(random.choice([
# # # # # # # # # # #             "For now, try a simple grounding exercise: look around and name five things you can see, four you can touch, three you can hear.",
# # # # # # # # # # #             "If you are feeling overwhelmed, try slowing your breath: 4 seconds in, 6 seconds out, repeat three times."
# # # # # # # # # # #         ]))
# # # # # # # # # # #     else:
# # # # # # # # # # #         # Mild / supportive responses
# # # # # # # # # # #         mental = str(safe_get_analysis_field(analysis, "mental_state", "")).lower()
# # # # # # # # # # #         emotion = str(safe_get_analysis_field(analysis, "emotion", "")).lower()
# # # # # # # # # # #         if mental in ("anxiety", "") and "anxiety" in (mental + " "):
# # # # # # # # # # #             followups.append("Would you like a short breathing exercise I can guide you through now?")
# # # # # # # # # # #             followups.append("We can also list 2 small actions you could try today to reduce stress — want that?")
# # # # # # # # # # #         elif mental == "burnout":
# # # # # # # # # # #             followups.append("Burnout often responds to small boundary changes. Can we plan 2 micro-actions for the next 48 hours?")
# # # # # # # # # # #         elif emotion == "guilt":
# # # # # # # # # # #             followups.append("Guilt can be heavy — it helps to name specific thoughts. Would you like to try a self-compassion exercise?")
# # # # # # # # # # #         else:
# # # # # # # # # # #             followups.append(random.choice([
# # # # # # # # # # #                 "I can help you with grounding, a short coping plan, or finding a therapist. Which would you prefer?",
# # # # # # # # # # #                 "Would you like a short breathing or grounding exercise, or would you prefer to talk through triggers?"
# # # # # # # # # # #             ]))

# # # # # # # # # # #     # Build reply with variation to avoid repetition
# # # # # # # # # # #     template_variants = [
# # # # # # # # # # #         "{open} {follow1} {follow2}",
# # # # # # # # # # #         "{open} {follow1} Also: {follow2}",
# # # # # # # # # # #         "{open} {follow2} {follow1}"
# # # # # # # # # # #     ]
# # # # # # # # # # #     chosen = random.choice(template_variants)
# # # # # # # # # # #     follow1 = followups[0] if followups else ""
# # # # # # # # # # #     follow2 = followups[1] if len(followups) > 1 else ""

# # # # # # # # # # #     reply = chosen.format(open=open_line, follow1=follow1, follow2=follow2)
# # # # # # # # # # #     # Slight cleaning
# # # # # # # # # # #     reply = " ".join(reply.split())
# # # # # # # # # # #     return reply

# # # # # # # # # # # # -------------------------
# # # # # # # # # # # # Streaming helpers
# # # # # # # # # # # # -------------------------
# # # # # # # # # # # def sse_format(data: dict) -> str:
# # # # # # # # # # #     """Format a dict as an SSE data: ... payload"""
# # # # # # # # # # #     return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

# # # # # # # # # # # def offline_stream_generator(text: str, analysis: Dict[str, Any], user_id: str = "default"):
# # # # # # # # # # #     """
# # # # # # # # # # #     Yield pieces of the reply with small delays to simulate streaming.
# # # # # # # # # # #     Varies fragments so responses aren't always identical.
# # # # # # # # # # #     """
# # # # # # # # # # #     # Create a reply using offline generator
# # # # # # # # # # #     full_reply = make_offline_reply(text, analysis, user_id)
# # # # # # # # # # #     # Split intelligently into chunks (by sentence / clause)
# # # # # # # # # # #     # Keep variety: sometimes small tokens, sometimes sentence fragments
# # # # # # # # # # #     if len(full_reply) < 120:
# # # # # # # # # # #         # short reply -> few medium chunks
# # # # # # # # # # #         pieces = [p.strip() for p in full_reply.split(". ") if p.strip()]
# # # # # # # # # # #     else:
# # # # # # # # # # #         # longer -> split by commas and sentences
# # # # # # # # # # #         pieces = []
# # # # # # # # # # #         for seg in full_reply.replace(", ", "||,||").split("||"):
# # # # # # # # # # #             seg = seg.strip()
# # # # # # # # # # #             if seg:
# # # # # # # # # # #                 pieces.append(seg)

# # # # # # # # # # #     # If pieces are empty fallback to single piece
# # # # # # # # # # #     if not pieces:
# # # # # # # # # # #         pieces = [full_reply]

# # # # # # # # # # #     # Randomize small filler in between occasionally to avoid identical output
# # # # # # # # # # #     for idx, p in enumerate(pieces):
# # # # # # # # # # #         payload = {"text": (p + (". " if not p.endswith((".", "!", "?")) else ""))}
# # # # # # # # # # #         yield sse_format(payload)
# # # # # # # # # # #         time.sleep(STREAM_DELAY + random.random() * 0.08)

# # # # # # # # # # #     # End marker (some clients expect a final JSON)
# # # # # # # # # # #     yield sse_format({"done": True, "text": ""})

# # # # # # # # # # # # -------------------------
# # # # # # # # # # # # Local LLM proxy (optional)
# # # # # # # # # # # # -------------------------
# # # # # # # # # # # def call_local_llm_stream(user_text: str, analysis: Dict[str, Any], user_id: str = "default"):
# # # # # # # # # # #     """
# # # # # # # # # # #     If LOCAL_LLM_ENABLED is True, this function should call the local model streaming
# # # # # # # # # # #     endpoint and stream responses through. For now we keep a placeholder — if the
# # # # # # # # # # #     server is unavailable we'll raise an exception and let caller fallback to offline.
# # # # # # # # # # #     """
# # # # # # # # # # #     # Placeholder - not implemented: raise to trigger fallback
# # # # # # # # # # #     raise ConnectionError("Local LLM proxy not configured or server unavailable.")


# # # # # # # # # # # # -------------------------
# # # # # # # # # # # # ROUTES
# # # # # # # # # # # # -------------------------
# # # # # # # # # # # @app.route("/", methods=["GET"])
# # # # # # # # # # # def home():
# # # # # # # # # # #     return {"status": "OK", "message": f"Chat server running on {SERVER_PORT}"}

# # # # # # # # # # # @app.route("/chat/stream", methods=["POST"])
# # # # # # # # # # # def chat_stream():
# # # # # # # # # # #     """
# # # # # # # # # # #     Streaming endpoint. Accepts JSON:
# # # # # # # # # # #       { "text": "...", "analysis": {...}, "user_id": "optional-id" }
# # # # # # # # # # #     Streams SSE "data: {json}\n\n" chunks containing {"text": "..."} fragments.
# # # # # # # # # # #     """
# # # # # # # # # # #     payload = request.get_json(force=True, silent=True) or {}
# # # # # # # # # # #     text = (payload.get("text") or "").strip()
# # # # # # # # # # #     analysis = payload.get("analysis") or {}
# # # # # # # # # # #     user_id = payload.get("user_id") or "default"

# # # # # # # # # # #     if not text:
# # # # # # # # # # #         return jsonify({"error": "No text provided"}), 400

# # # # # # # # # # #     log.info(f"[STREAM] User ({user_id}): {text} — analysis present: {bool(analysis)}")

# # # # # # # # # # #     # Try local model streaming first (if enabled)
# # # # # # # # # # #     if LOCAL_LLM_ENABLED:
# # # # # # # # # # #         try:
# # # # # # # # # # #             # call_local_llm_stream should yield SSE-formatted strings
# # # # # # # # # # #             return Response(call_local_llm_stream(text, analysis, user_id), content_type="text/event-stream")
# # # # # # # # # # #         except Exception as e:
# # # # # # # # # # #             log.error("STREAM ERROR (local LLM): %s", str(e))
# # # # # # # # # # #             # fallthrough -> offline generator

# # # # # # # # # # #     # Fallback: use offline streaming generator
# # # # # # # # # # #     return Response(offline_stream_generator(text, analysis, user_id), content_type="text/event-stream")

# # # # # # # # # # # @app.route("/chat", methods=["POST"])
# # # # # # # # # # # def chat_once():
# # # # # # # # # # #     """
# # # # # # # # # # #     Non-streaming fallback endpoint. Returns JSON:
# # # # # # # # # # #       { "reply": "..." }
# # # # # # # # # # #     Accepts JSON: { "text": "...", "analysis": {...}, "user_id": "..." }
# # # # # # # # # # #     """
# # # # # # # # # # #     payload = request.get_json(force=True, silent=True) or {}
# # # # # # # # # # #     text = (payload.get("text") or "").strip()
# # # # # # # # # # #     analysis = payload.get("analysis") or {}
# # # # # # # # # # #     user_id = payload.get("user_id") or "default"

# # # # # # # # # # #     if not text:
# # # # # # # # # # #         return jsonify({"error": "No text provided"}), 400

# # # # # # # # # # #     log.info(f"[ONCE] User ({user_id}): {text} — analysis present: {bool(analysis)}")

# # # # # # # # # # #     # If local LLM is enabled we could call it synchronously (not implemented here)
# # # # # # # # # # #     if LOCAL_LLM_ENABLED:
# # # # # # # # # # #         try:
# # # # # # # # # # #             # Placeholder: local LLM call would go here
# # # # # # # # # # #             raise ConnectionError("Local LLM sync call not implemented in this shim.")
# # # # # # # # # # #         except Exception as e:
# # # # # # # # # # #             log.error("Local LLM (sync) failed: %s — falling back", e)

# # # # # # # # # # #     # Offline reply
# # # # # # # # # # #     reply = make_offline_reply(text, analysis, user_id)
# # # # # # # # # # #     return jsonify({"reply": reply})

# # # # # # # # # # # # -------------------------
# # # # # # # # # # # # Run server
# # # # # # # # # # # # -------------------------
# # # # # # # # # # # if __name__ == "__main__":
# # # # # # # # # # #     log.info(f"Chat server running on {SERVER_PORT} ...")
# # # # # # # # # # #     app.run(host="0.0.0.0", port=SERVER_PORT, debug=False)
# # # # # # # # # # # # ===================================================================






# # # # # # # # # # # ==============================================================
# # # # # # # # # # # api_chat.py — Therapy-Aware Chatbot API (FINAL VERSION)
# # # # # # # # # # # ==============================================================

# # # # # # # # # # import os
# # # # # # # # # # import json
# # # # # # # # # # import logging
# # # # # # # # # # from flask import Flask, request, Response, jsonify
# # # # # # # # # # from datetime import datetime

# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # # LOGGING
# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # logging.basicConfig(level=logging.INFO)
# # # # # # # # # # log = logging.getLogger("api_chat")

# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # # CONFIG
# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # USE_LOCAL_LLM = False
# # # # # # # # # # LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"

# # # # # # # # # # log.info("Starting api_chat.py — therapy-aware chat API")
# # # # # # # # # # log.info(f"Local LLM enabled: {USE_LOCAL_LLM}; Local LLM URL: {LOCAL_LLM_URL}")

# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # # FLASK
# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # app = Flask(__name__)

# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # # INTERNAL SIMPLE AI (fallback)
# # # # # # # # # # # --------------------------------------------------------------

# # # # # # # # # # def internal_ai_reply(user_msg, analysis=None):
# # # # # # # # # #     """
# # # # # # # # # #     Offline smart counselling logic (no LLM needed)
# # # # # # # # # #     """

# # # # # # # # # #     user = user_msg.lower().strip()
# # # # # # # # # #     mental = analysis.get("mental_state") if analysis else None
# # # # # # # # # #     emotion = analysis.get("emotion") if analysis else None
# # # # # # # # # #     severity = analysis.get("severity") if analysis else None
# # # # # # # # # #     risk = analysis.get("suicide_risk") if analysis else None

# # # # # # # # # #     # ---------------------------------------------
# # # # # # # # # #     # 1. Extreme risk detection
# # # # # # # # # #     # ---------------------------------------------
# # # # # # # # # #     if risk in ["high", "severe"]:
# # # # # # # # # #         return (
# # # # # # # # # #             "I can sense deep emotional pain in your words. "
# # # # # # # # # #             "Right now, the safest option is to talk to a professional immediately. "
# # # # # # # # # #             "Please consider reaching out to a suicide hotline or emergency services. "
# # # # # # # # # #             "If you want, I can also help you book a session with a therapist at MindMatters."
# # # # # # # # # #         )

# # # # # # # # # #     # ---------------------------------------------
# # # # # # # # # #     # 2. Moderate risk → suggest therapy strongly
# # # # # # # # # #     # ---------------------------------------------
# # # # # # # # # #     if risk in ["moderate"]:
# # # # # # # # # #         return (
# # # # # # # # # #             "Your analysis shows some concerning signs. "
# # # # # # # # # #             "You don’t need to handle this alone. A professional therapist can help you heal safely. "
# # # # # # # # # #             "Would you like me to guide you toward a MindMatters therapy session?"
# # # # # # # # # #         )

# # # # # # # # # #     # ---------------------------------------------
# # # # # # # # # #     # 3. Mental-state-based replies
# # # # # # # # # #     # ---------------------------------------------
# # # # # # # # # #     if mental == "depression":
# # # # # # # # # #         return (
# # # # # # # # # #             "It sounds really heavy on your heart. Depression often makes even simple things difficult. "
# # # # # # # # # #             "Try to be gentle with yourself. If you'd like, I can help you explore steps for recovery "
# # # # # # # # # #             "or guide you toward a professional therapy session with MindMatters."
# # # # # # # # # #         )

# # # # # # # # # #     if mental == "anxiety":
# # # # # # # # # #         return (
# # # # # # # # # #             "I understand how overwhelming anxiety can feel. "
# # # # # # # # # #             "Let’s take one slow breath together. "
# # # # # # # # # #             "If it has been affecting your daily life, therapy can help build long-term stability. "
# # # # # # # # # #             "Would you like guidance?"
# # # # # # # # # #         )

# # # # # # # # # #     if mental == "stress":
# # # # # # # # # #         return (
# # # # # # # # # #             "Stress can pile up silently. You’re doing better than you think. "
# # # # # # # # # #             "Small steps like rest, deep breathing, and talking to someone you trust can help. "
# # # # # # # # # #             "If you want, I can connect you with a therapist at MindMatters."
# # # # # # # # # #         )

# # # # # # # # # #     if mental == "burnout":
# # # # # # # # # #         return (
# # # # # # # # # #             "Burnout drains both energy and motivation. You deserve rest and proper support. "
# # # # # # # # # #             "A therapist can help you recover in a structured way. "
# # # # # # # # # #             "Would you like to explore therapy options?"
# # # # # # # # # #         )

# # # # # # # # # #     if mental == "trauma":
# # # # # # # # # #         return (
# # # # # # # # # #             "I'm really sorry if you are carrying painful memories. Trauma needs gentle, structured healing. "
# # # # # # # # # #             "Talking to a therapist can make recovery safer and faster. "
# # # # # # # # # #             "Would you like me to recommend therapy sessions?"
# # # # # # # # # #         )

# # # # # # # # # #     if mental == "normal":
# # # # # # # # # #         return (
# # # # # # # # # #             "You seem emotionally stable overall. Still, talking about your thoughts is always welcome. "
# # # # # # # # # #             "What’s on your mind right now?"
# # # # # # # # # #         )

# # # # # # # # # #     # ---------------------------------------------
# # # # # # # # # #     # 4. Emotion-based reply fallback
# # # # # # # # # #     # ---------------------------------------------
# # # # # # # # # #     if emotion == "sadness":
# # # # # # # # # #         return "I’m here with you. Sadness can be exhausting. Would you like some grounding tips?"

# # # # # # # # # #     if emotion == "fear":
# # # # # # # # # #         return "Fear can feel heavy. You’re not alone. Want to talk about what triggered it?"

# # # # # # # # # #     if emotion == "anger":
# # # # # # # # # #         return "Anger often hides deeper pain. I’m listening — what upset you most?"

# # # # # # # # # #     if emotion == "loneliness":
# # # # # # # # # #         return "Loneliness hurts in its own way. I’m here with you — tell me what’s weighing on you?"

# # # # # # # # # #     # ---------------------------------------------
# # # # # # # # # #     # 5. Default counselling-friendly reply
# # # # # # # # # #     # ---------------------------------------------
# # # # # # # # # #     return (
# # # # # # # # # #         "I hear you. I'm here to support you. "
# # # # # # # # # #         "If you want, I can help with coping steps or guide you toward a MindMatters therapy session."
# # # # # # # # # #     )

# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # # STREAMING ENDPOINT
# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # @app.route("/chat/stream", methods=["POST"])
# # # # # # # # # # def chat_stream():
# # # # # # # # # #     try:
# # # # # # # # # #         data = request.get_json(force=True)
# # # # # # # # # #         user_msg = data.get("text", "")
# # # # # # # # # #         analysis = data.get("analysis", {})

# # # # # # # # # #         log.info(f"[STREAM] User: {user_msg}")

# # # # # # # # # #         # Only internal AI logic (no external model)
# # # # # # # # # #         reply = internal_ai_reply(user_msg, analysis)

# # # # # # # # # #         def event_stream():
# # # # # # # # # #             # stream token-by-token for typing effect
# # # # # # # # # #             for token in reply.split():
# # # # # # # # # #                 yield token + " "
        
# # # # # # # # # #         return Response(event_stream(), mimetype="text/plain")

# # # # # # # # # #     except Exception as e:
# # # # # # # # # #         log.error(f"STREAM ERROR: {e}")
# # # # # # # # # #         return Response("Error in streaming", status=200, mimetype="text/plain")

# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # # NON-STREAMING ENDPOINT
# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # @app.route("/chat", methods=["POST"])
# # # # # # # # # # def chat_once():
# # # # # # # # # #     try:
# # # # # # # # # #         data = request.get_json(force=True)
# # # # # # # # # #         user_msg = data.get("text", "")
# # # # # # # # # #         analysis = data.get("analysis", {})

# # # # # # # # # #         reply = internal_ai_reply(user_msg, analysis)

# # # # # # # # # #         return jsonify({ "reply": reply })

# # # # # # # # # #     except Exception as e:
# # # # # # # # # #         return jsonify({"error": str(e)}), 500

# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # # HOME
# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # @app.route("/", methods=["GET"])
# # # # # # # # # # def home():
# # # # # # # # # #     return {"status": "OK", "message": "Chat API running"}

# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # # RUN
# # # # # # # # # # # --------------------------------------------------------------
# # # # # # # # # # if __name__ == "__main__":
# # # # # # # # # #     log.info("Chat server running on 5100 ...")
# # # # # # # # # #     app.run(host="0.0.0.0", port=5100, debug=False)







# # # # # # # # # # ================================================================
# # # # # # # # # # api_chat.py — Therapy-Aware Chat + CORS FIXED + Streaming FIXED
# # # # # # # # # # ================================================================

# # # # # # # # # import json
# # # # # # # # # import logging
# # # # # # # # # from flask import Flask, request, Response, jsonify
# # # # # # # # # from flask_cors import CORS
# # # # # # # # # import requests

# # # # # # # # # logging.basicConfig(level=logging.INFO)
# # # # # # # # # log = logging.getLogger("api_chat")

# # # # # # # # # # ================================================================
# # # # # # # # # # SETTINGS
# # # # # # # # # # ================================================================
# # # # # # # # # USE_LOCAL_LLM = False     # Tum chaho toh True karna
# # # # # # # # # LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"

# # # # # # # # # # ================================================================
# # # # # # # # # # FLASK SETUP + CORS FIX
# # # # # # # # # # ================================================================
# # # # # # # # # app = Flask(__name__)
# # # # # # # # # CORS(app, resources={r"/*": {"origins": "*"}})   # <-- FULL CORS UNLOCK

# # # # # # # # # log.info("Starting api_chat.py — therapy-aware chat API")
# # # # # # # # # log.info(f"Local LLM enabled: {USE_LOCAL_LLM}; Local LLM URL: {LOCAL_LLM_URL}")
# # # # # # # # # log.info("Chat server running on 5100 ...")

# # # # # # # # # # ================================================================
# # # # # # # # # # FALLBACK SAFE BOT (IF NO LLM)
# # # # # # # # # # ================================================================
# # # # # # # # # def simple_bot(user_msg, analysis=None):
# # # # # # # # #     """A very basic fallback response generator."""
# # # # # # # # #     base = ""

# # # # # # # # #     if analysis:
# # # # # # # # #         base += (
# # # # # # # # #             f"I see signs of {analysis.get('mental_state')} with "
# # # # # # # # #             f"emotion {analysis.get('emotion')} and severity "
# # # # # # # # #             f"{analysis.get('severity')}. "
# # # # # # # # #         )

# # # # # # # # #         # Therapy promotion logic
# # # # # # # # #         sev = (analysis.get("severity") or "").lower()
# # # # # # # # #         risk = (analysis.get("suicide_risk") or "").lower()

# # # # # # # # #         if sev in ["moderate", "severe"] or risk in ["moderate", "high"]:
# # # # # # # # #             base += (
# # # # # # # # #                 "This might be a good time to consider a paid therapy "
# # # # # # # # #                 "session with MindMatters. I can guide you if you wish. "
# # # # # # # # #             )

# # # # # # # # #     base += f"You said: {user_msg}. I'm here to support you."
# # # # # # # # #     return base

# # # # # # # # # # ================================================================
# # # # # # # # # # STREAM RESPONSE HELPERS
# # # # # # # # # # ================================================================
# # # # # # # # # def stream_local_llm(query_text):
# # # # # # # # #     """Streams tokens from a local LLM server."""
# # # # # # # # #     try:
# # # # # # # # #         payload = {
# # # # # # # # #             "model": "gpt-4o-mini",
# # # # # # # # #             "stream": True,
# # # # # # # # #             "messages": [{"role": "user", "content": query_text}]
# # # # # # # # #         }
# # # # # # # # #         r = requests.post(LOCAL_LLM_URL, json=payload, stream=True)

# # # # # # # # #         def generate():
# # # # # # # # #             for line in r.iter_lines(decode_unicode=True):
# # # # # # # # #                 if line:
# # # # # # # # #                     yield line + "\n"

# # # # # # # # #         return Response(generate(), mimetype="text/plain")

# # # # # # # # #     except Exception as e:
# # # # # # # # #         log.error("STREAM ERROR local LLM: %s", e)
# # # # # # # # #         return Response(f"Error: {e}", mimetype="text/plain")


# # # # # # # # # # ================================================================
# # # # # # # # # # /chat — Non-stream fallback
# # # # # # # # # # ================================================================
# # # # # # # # # @app.route("/chat", methods=["POST"])
# # # # # # # # # def chat_once():
# # # # # # # # #     data = request.json
# # # # # # # # #     user_msg = data.get("text", "")
# # # # # # # # #     analysis = data.get("analysis")

# # # # # # # # #     reply = None

# # # # # # # # #     # Use local LLM if enabled
# # # # # # # # #     if USE_LOCAL_LLM:
# # # # # # # # #         try:
# # # # # # # # #             payload = {
# # # # # # # # #                 "model": "gpt-4o-mini",
# # # # # # # # #                 "stream": False,
# # # # # # # # #                 "messages": [{"role": "user", "content": user_msg}]
# # # # # # # # #             }
# # # # # # # # #             r = requests.post(LOCAL_LLM_URL, json=payload)
# # # # # # # # #             j = r.json()
# # # # # # # # #             reply = j["choices"][0]["message"]["content"]
# # # # # # # # #         except:
# # # # # # # # #             reply = simple_bot(user_msg, analysis)

# # # # # # # # #     else:
# # # # # # # # #         reply = simple_bot(user_msg, analysis)

# # # # # # # # #     return jsonify({"reply": reply})

# # # # # # # # # # ================================================================
# # # # # # # # # # /chat/stream — Streaming endpoint
# # # # # # # # # # ================================================================
# # # # # # # # # @app.route("/chat/stream", methods=["POST"])
# # # # # # # # # def chat_stream():
# # # # # # # # #     data = request.json
# # # # # # # # #     user_msg = data.get("text", "")
# # # # # # # # #     analysis = data.get("analysis")

# # # # # # # # #     log.info("[STREAM] User: %s", user_msg)

# # # # # # # # #     # Local LLM mode
# # # # # # # # #     if USE_LOCAL_LLM:
# # # # # # # # #         return stream_local_llm(user_msg)

# # # # # # # # #     # Otherwise stream simple bot reply (token-by-token)
# # # # # # # # #     reply = simple_bot(user_msg, analysis)

# # # # # # # # #     def generate():
# # # # # # # # #         for token in reply.split():
# # # # # # # # #             yield token + " "
    
# # # # # # # # #     return Response(generate(), mimetype="text/plain")


# # # # # # # # # # ================================================================
# # # # # # # # # # MAIN
# # # # # # # # # # ================================================================
# # # # # # # # # if __name__ == "__main__":
# # # # # # # # #     app.run(host="0.0.0.0", port=5100, debug=False)



# # # # # # # # # ===========================================================
# # # # # # # # # api_chat.py (FINAL) — Intelligent Therapy Chat + Analysis-Based Replies
# # # # # # # # # ===========================================================

# # # # # # # # import json
# # # # # # # # import logging
# # # # # # # # from flask import Flask, request, jsonify
# # # # # # # # from flask_cors import CORS
# # # # # # # # import requests

# # # # # # # # logging.basicConfig(level=logging.INFO)
# # # # # # # # log = logging.getLogger("api_chat")

# # # # # # # # app = Flask(__name__)
# # # # # # # # CORS(app)

# # # # # # # # # ===========================================================
# # # # # # # # # CONFIG
# # # # # # # # # ===========================================================

# # # # # # # # USE_LOCAL_LLM = False       
# # # # # # # # LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"

# # # # # # # # # global latest analysis
# # # # # # # # last_analysis = {
# # # # # # # #     "mental": None,
# # # # # # # #     "emotion": None,
# # # # # # # #     "severity": None,
# # # # # # # #     "risk": None,
# # # # # # # #     "indicators": []
# # # # # # # # }

# # # # # # # # # ===========================================================
# # # # # # # # # Helper: Format user analysis context
# # # # # # # # # ===========================================================

# # # # # # # # def format_analysis_context():
# # # # # # # #     if not last_analysis["mental"]:
# # # # # # # #         return "No analysis available."

# # # # # # # #     return (
# # # # # # # #         f"Mental: {last_analysis['mental']}. "
# # # # # # # #         f"Emotion: {last_analysis['emotion']}. "
# # # # # # # #         f"Severity: {last_analysis['severity']}. "
# # # # # # # #         f"Suicide Risk: {last_analysis['risk']}. "
# # # # # # # #         f"Indicators: {', '.join(last_analysis['indicators'])}."
# # # # # # # #     )

# # # # # # # # # ===========================================================
# # # # # # # # # IMPROVED THERAPY LOGIC (NON-REPETITIVE)
# # # # # # # # # ===========================================================

# # # # # # # # def produce_therapy_reply(user_msg):
# # # # # # # #     a = format_analysis_context()

# # # # # # # #     pitch = (
# # # # # # # #         "\n\nBased on what I'm seeing, this could be a meaningful time to begin a paid therapy session "
# # # # # # # #         "with **MindMatters**. I can guide you, help prepare, or answer questions if you want."
# # # # # # # #     )

# # # # # # # #     if any(x in user_msg.lower() for x in ["why", "reason", "cause"]):
# # # # # # # #         return (
# # # # # # # #             f"I understand that you're wondering *why* you feel this way.\n\n"
# # # # # # # #             f"Based on your mental profile:\n{a}\n\n"
# # # # # # # #             f"These patterns often happen due to emotional overload or unresolved stress.\n"
# # # # # # # #             f"I'm here to help you understand it step by step.{pitch}"
# # # # # # # #         )

# # # # # # # #     if "what i have to do" in user_msg.lower() or "what should i do" in user_msg.lower():
# # # # # # # #         return (
# # # # # # # #             f"I hear you — you're asking what you should do next.\n\n"
# # # # # # # #             f"From the analysis:\n{a}\n\n"
# # # # # # # #             "A helpful next step could be:\n"
# # # # # # # #             "- Talking openly about what triggered these feelings\n"
# # # # # # # #             "- Trying grounding or breathing techniques\n"
# # # # # # # #             "- Identifying patterns that worsen the emotion\n"
# # # # # # # #             "- Reaching out for support when needed\n"
# # # # # # # #             f"{pitch}"
# # # # # # # #         )

# # # # # # # #     if "help" in user_msg.lower():
# # # # # # # #         return (
# # # # # # # #             f"I'm here to help.\n\n"
# # # # # # # #             f"Your emotional profile shows:\n{a}\n\n"
# # # # # # # #             "Tell me a bit more about what feels hardest right now."
# # # # # # # #             f"{pitch}"
# # # # # # # #         )

# # # # # # # #     # default — unique response every time
# # # # # # # #     return (
# # # # # # # #         f"I hear you. Your message means something important.\n\n"
# # # # # # # #         f"Your emotional state from the latest analysis:\n{a}\n\n"
# # # # # # # #         "Tell me more — what’s on your mind right now?"
# # # # # # # #         f"{pitch}"
# # # # # # # #     )

# # # # # # # # # ===========================================================
# # # # # # # # # CHAT ENDPOINT
# # # # # # # # # ===========================================================

# # # # # # # # @app.route("/chat", methods=["POST"])
# # # # # # # # def chat_once():
# # # # # # # #     data = request.json
# # # # # # # #     user_msg = data.get("text", "")

# # # # # # # #     if not user_msg:
# # # # # # # #         return jsonify({"reply": "Say something, I'm here."})

# # # # # # # #     reply = produce_therapy_reply(user_msg)
# # # # # # # #     return jsonify({"reply": reply})


# # # # # # # # # ===========================================================
# # # # # # # # # RECEIVE ANALYSIS FROM /analyze (frontend)
# # # # # # # # # ===========================================================

# # # # # # # # @app.route("/update_analysis", methods=["POST"])
# # # # # # # # def update_analysis():
# # # # # # # #     global last_analysis
# # # # # # # #     data = request.json

# # # # # # # #     last_analysis["mental"] = data.get("mental")
# # # # # # # #     last_analysis["emotion"] = data.get("emotion")
# # # # # # # #     last_analysis["severity"] = data.get("severity")
# # # # # # # #     last_analysis["risk"] = data.get("risk")
# # # # # # # #     last_analysis["indicators"] = data.get("indicators", [])

# # # # # # # #     log.info("Updated analysis: %s", last_analysis)

# # # # # # # #     return jsonify({"status": "ok", "updated": last_analysis})


# # # # # # # # # ===========================================================
# # # # # # # # # SERVER START
# # # # # # # # # ===========================================================

# # # # # # # # if __name__ == "__main__":
# # # # # # # #     log.info("Therapy Chat API running on http://127.0.0.1:5100/")
# # # # # # # #     app.run(host="0.0.0.0", port=5100)







# # # # # # # # ============================================================
# # # # # # # # api_chat.py — Final Therapy-aware Chat Server (No Symbols)
# # # # # # # # THE MIND MATTERS — Chat API
# # # # # # # # ============================================================

# # # # # # # import json
# # # # # # # import traceback
# # # # # # # from flask import Flask, request, Response, jsonify
# # # # # # # from flask_cors import CORS
# # # # # # # import requests
# # # # # # # import logging

# # # # # # # app = Flask(__name__)
# # # # # # # CORS(app)

# # # # # # # logging.basicConfig(level=logging.INFO)
# # # # # # # log = logging.getLogger("api_chat")

# # # # # # # # ============================================================
# # # # # # # # CONFIG
# # # # # # # # ============================================================

# # # # # # # USE_LOCAL_LLM = False        # Change to True if you have LM Studio or Ollama
# # # # # # # LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"

# # # # # # # SYSTEM_PROMPT = """
# # # # # # # You are a mental health conversational assistant for THE MIND MATTERS.
# # # # # # # Your job:

# # # # # # # 1. Respond with emotional sensitivity.
# # # # # # # 2. Use analysis data (mental_state, emotion, severity, suicide_risk, indicators)
# # # # # # #    to tailor replies.
# # # # # # # 3. If severity is moderate or high OR suicide_risk is moderate/high → gently suggest:
# # # # # # #    “This might be a meaningful time to begin a paid therapy session with THE MIND MATTERS.”
# # # # # # # 4. NEVER repeat the user's message back to them.
# # # # # # # 5. NEVER say generic fillers. Give real reasoning and supportive language.
# # # # # # # 6. Keep replies short, warm, supportive, human-like.
# # # # # # # 7. Never give medical claims — only emotional support.
# # # # # # # """

# # # # # # # # ============================================================
# # # # # # # # Helper: Call Local/OpenAI Model
# # # # # # # # ============================================================

# # # # # # # def call_llm(messages):
# # # # # # #     if not USE_LOCAL_LLM:
# # # # # # #         # Online: OpenAI compatible (if you connect)
# # # # # # #         url = "https://api.openai.com/v1/chat/completions"
# # # # # # #         headers = {
# # # # # # #             "Content-Type": "application/json",
# # # # # # #             "Authorization": "Bearer YOUR_API_KEY_HERE"
# # # # # # #         }
# # # # # # #         payload = {"model": "gpt-4o-mini", "messages": messages, "stream": False}
# # # # # # #         r = requests.post(url, json=payload, headers=headers)
# # # # # # #         j = r.json()
# # # # # # #         return j["choices"][0]["message"]["content"]

# # # # # # #     # Local LLM (LM Studio / Ollama)
# # # # # # #     payload = {
# # # # # # #         "model": "local-model",
# # # # # # #         "messages": messages,
# # # # # # #         "stream": False
# # # # # # #     }
# # # # # # #     r = requests.post(LOCAL_LLM_URL, json=payload)
# # # # # # #     j = r.json()
# # # # # # #     return j["choices"][0]["message"]["content"]


# # # # # # # # ============================================================
# # # # # # # # Format analysis into context prompt
# # # # # # # # ============================================================

# # # # # # # def build_analysis_context(analysis):
# # # # # # #     if not analysis:
# # # # # # #         return "No analysis available."
    
# # # # # # #     ms = analysis.get("mental_state","unknown")
# # # # # # #     em = analysis.get("emotion","unknown")
# # # # # # #     sv = analysis.get("severity","unknown")
# # # # # # #     rk = analysis.get("suicide_risk","unknown")
# # # # # # #     ind = ", ".join(analysis.get("indicators", [])) or "none"

# # # # # # #     return (
# # # # # # #         f"Mental State: {ms}. Emotion: {em}. Severity: {sv}. "
# # # # # # #         f"Suicide Risk: {rk}. Indicators: {ind}."
# # # # # # #     )


# # # # # # # # ============================================================
# # # # # # # # POST /chat — non-stream chat
# # # # # # # # ============================================================

# # # # # # # @app.post("/chat")
# # # # # # # def chat_once():
# # # # # # #     try:
# # # # # # #         data = request.json
# # # # # # #         user_text = data.get("text", "")
# # # # # # #         analysis = data.get("analysis")

# # # # # # #         analysis_context = build_analysis_context(analysis)

# # # # # # #         messages = [
# # # # # # #             {"role": "system", "content": SYSTEM_PROMPT},
# # # # # # #             {"role": "system", "content": f"Analysis summary: {analysis_context}"},
# # # # # # #             {"role": "user", "content": user_text}
# # # # # # #         ]

# # # # # # #         reply = call_llm(messages)
# # # # # # #         return jsonify({"reply": reply})

# # # # # # #     except Exception as e:
# # # # # # #         log.error("Chat error: %s", traceback.format_exc())
# # # # # # #         return jsonify({"error": str(e)}), 500


# # # # # # # # ============================================================
# # # # # # # # POST /chat/stream — streaming tokens
# # # # # # # # ============================================================

# # # # # # # @app.post("/chat/stream")
# # # # # # # def chat_stream():
# # # # # # #     data = request.json
# # # # # # #     user_text = data.get("text", "")
# # # # # # #     analysis = data.get("analysis")

# # # # # # #     analysis_context = build_analysis_context(analysis)

# # # # # # #     messages = [
# # # # # # #         {"role": "system", "content": SYSTEM_PROMPT},
# # # # # # #         {"role": "system", "content": f"Analysis summary: {analysis_context}"},
# # # # # # #         {"role": "user", "content": user_text},
# # # # # # #     ]

# # # # # # #     def stream_reply():
# # # # # # #         try:
# # # # # # #             if not USE_LOCAL_LLM:
# # # # # # #                 yield "Streaming disabled (online model not enabled)."
# # # # # # #                 return

# # # # # # #             payload = {
# # # # # # #                 "model": "local-model",
# # # # # # #                 "messages": messages,
# # # # # # #                 "stream": True
# # # # # # #             }
# # # # # # #             r = requests.post(LOCAL_LLM_URL, json=payload, stream=True)

# # # # # # #             for chunk in r.iter_lines(decode_unicode=True):
# # # # # # #                 if chunk:
# # # # # # #                     try:
# # # # # # #                         j = json.loads(chunk.replace("data: ", ""))
# # # # # # #                         token = j["choices"][0]["delta"].get("content")
# # # # # # #                         if token:
# # # # # # #                             yield token
# # # # # # #                     except:
# # # # # # #                         pass

# # # # # # #         except Exception as e:
# # # # # # #             log.error("Streaming failed: %s", traceback.format_exc())
# # # # # # #             yield "Error: streaming unavailable."

# # # # # # #     return Response(stream_reply(), mimetype="text/plain")


# # # # # # # # ============================================================
# # # # # # # # Run server
# # # # # # # # ============================================================

# # # # # # # if __name__ == "__main__":
# # # # # # #     log.info("Starting THE MIND MATTERS Chat API on 127.0.0.1:5100 ...")
# # # # # # #     app.run(host="0.0.0.0", port=5100, debug=False)


# # # # # # from flask_cors import CORS

# # # # # # app = Flask(__name__)
# # # # # # CORS(app, resources={r"/*": {"origins": "*"}})


# # # # # # import json
# # # # # # import logging
# # # # # # from flask import Flask, request, Response, jsonify
# # # # # # from flask_cors import CORS
# # # # # # import requests

# # # # # # app = Flask(__name__)
# # # # # # CORS(app)

# # # # # # logging.basicConfig(level=logging.INFO)
# # # # # # log = logging.getLogger("api_chat")

# # # # # # # -----------------------------
# # # # # # # SETTINGS
# # # # # # # -----------------------------
# # # # # # USE_LOCAL_LLM = True                 # <-- MAKE STREAMING TRUE
# # # # # # LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"

# # # # # # SYSTEM_PROMPT = """
# # # # # # You are THE MIND MATTERS therapy assistant.
# # # # # # You give emotional support, mental-health guidance, and suggest paid therapy sessions
# # # # # # with THE MIND MATTERS when needed.
# # # # # # Use the analysis data if provided.
# # # # # # Always be empathetic, supportive, clear, and human-like.
# # # # # # """

# # # # # # # -----------------------------
# # # # # # # INTERNAL FUNCTION
# # # # # # # -----------------------------
# # # # # # def call_local_llm_stream(user_msg, analysis=None):
# # # # # #     """STREAMING generator for LMStudio / Ollama / local models"""
# # # # # #     try:
# # # # # #         payload = {
# # # # # #             "model": "local-model",
# # # # # #             "stream": True,
# # # # # #             "messages": [
# # # # # #                 {"role": "system", "content": SYSTEM_PROMPT},
# # # # # #             ]
# # # # # #         }

# # # # # #         if analysis:
# # # # # #             payload["messages"].append({
# # # # # #                 "role": "system",
# # # # # #                 "content": f"Latest analysis: {json.dumps(analysis)}"
# # # # # #             })

# # # # # #         payload["messages"].append({"role": "user", "content": user_msg})

# # # # # #         with requests.post(LOCAL_LLM_URL, json=payload, stream=True) as r:
# # # # # #             for line in r.iter_lines():
# # # # # #                 if not line:
# # # # # #                     continue
# # # # # #                 try:
# # # # # #                     j = json.loads(line.decode("utf-8"))
# # # # # #                     if "choices" in j:
# # # # # #                         delta = j["choices"][0]["delta"]
# # # # # #                         if "content" in delta:
# # # # # #                             yield delta["content"]
# # # # # #                 except:
# # # # # #                     continue

# # # # # #     except Exception as e:
# # # # # #         log.error("STREAM ERROR: %s", e)
# # # # # #         yield "[Streaming failed.] "


# # # # # # # -----------------------------
# # # # # # # STREAM ENDPOINT
# # # # # # # -----------------------------
# # # # # # @app.post("/chat/stream")
# # # # # # def chat_stream():
# # # # # #     data = request.get_json(silent=True) or {}
# # # # # #     user_msg = data.get("text", "")
# # # # # #     analysis = data.get("analysis")

# # # # # #     if USE_LOCAL_LLM:
# # # # # #         return Response(call_local_llm_stream(user_msg, analysis), mimetype="text/plain")

# # # # # #     return Response("Streaming disabled (online model not enabled).", mimetype="text/plain")


# # # # # # # -----------------------------
# # # # # # # NON-STREAM FALLBACK
# # # # # # # -----------------------------
# # # # # # @app.post("/chat")
# # # # # # def chat_fallback():
# # # # # #     data = request.get_json(silent=True) or {}
# # # # # #     user_msg = data.get("text", "")
# # # # # #     analysis = data.get("analysis")

# # # # # #     reply = f"""
# # # # # # I hear you. You said: "{user_msg}"

# # # # # # Your emotional state from the latest analysis:
# # # # # # {analysis if analysis else 'No analysis available.'}

# # # # # # Based on what I'm seeing, this could be a meaningful time to begin a paid therapy session with THE MIND MATTERS.  
# # # # # # I can guide you, help prepare, or answer questions if you want.
# # # # # #     """.strip()

# # # # # #     return jsonify({"reply": reply})


# # # # # # if __name__ == "__main__":
# # # # # #     log.info("Starting THE MIND MATTERS Chat API on 127.0.0.1:5100 ...")
# # # # # #     app.run(host="0.0.0.0", port=5100)
# # # # # # # # # # # # ============================================================
# # # # # # # # # # # # api_chat.py — Therapy-Aware Chatbot API (OLD    VERSION)
# # # # # # # # # # # # ============================================================



# # # # # import json
# # # # # import logging
# # # # # import time
# # # # # from flask import Flask, request, Response, jsonify
# # # # # from flask_cors import CORS
# # # # # import requests

# # # # # # ------------------------------------------
# # # # # # FLASK APP + CORS FIX (REQUIRED)
# # # # # # ------------------------------------------
# # # # # app = Flask(__name__)
# # # # # CORS(app, resources={r"/*": {"origins": "*"}})

# # # # # logging.basicConfig(level=logging.INFO)
# # # # # log = logging.getLogger("api_chat")

# # # # # # ------------------------------------------
# # # # # # SETTINGS
# # # # # # ------------------------------------------
# # # # # USE_LOCAL_LLM = False   # streaming ko band rakho (local model nahi chal raha)
# # # # # LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"

# # # # # SYSTEM_PROMPT = """
# # # # # You are THE MIND MATTERS therapy assistant.
# # # # # You talk empathetically, supportively, and professionally.
# # # # # Use analysis info if provided.
# # # # # Suggest starting a paid therapy session with THE MIND MATTERS when appropriate.
# # # # # Be warm, human-like, helpful and clear.
# # # # # """


# # # # # # ------------------------------------------
# # # # # # LOCAL STREAMING FUNCTION (ONLY IF ENABLED)
# # # # # # ------------------------------------------
# # # # # def call_local_llm_stream(user_msg, analysis=None):
# # # # #     """Streaming generator for LM Studio OR Local Models"""
# # # # #     try:
# # # # #         payload = {
# # # # #             "model": "local-model",
# # # # #             "stream": True,
# # # # #             "messages": [
# # # # #                 {"role": "system", "content": SYSTEM_PROMPT},
# # # # #             ]
# # # # #         }

# # # # #         if analysis:
# # # # #             payload["messages"].append({
# # # # #                 "role": "system",
# # # # #                 "content": f"Latest analysis data: {json.dumps(analysis)}"
# # # # #             })

# # # # #         payload["messages"].append({"role": "user", "content": user_msg})

# # # # #         with requests.post(LOCAL_LLM_URL, json=payload, stream=True) as r:
# # # # #             for line in r.iter_lines():
# # # # #                 if not line:
# # # # #                     continue

# # # # #                 try:
# # # # #                     j = json.loads(line.decode("utf-8"))
# # # # #                     if "choices" in j:
# # # # #                         delta = j["choices"][0]["delta"]
# # # # #                         if "content" in delta:
# # # # #                             yield delta["content"]
# # # # #                 except:
# # # # #                     continue

# # # # #     except Exception as e:
# # # # #         log.error("STREAM ERROR: %s", e)
# # # # #         yield "[Streaming failed.] "


# # # # # # ------------------------------------------
# # # # # # STREAMING ENDPOINT
# # # # # # ------------------------------------------
# # # # # @app.post("/chat/stream")
# # # # # def chat_stream():
# # # # #     data = request.get_json(silent=True) or {}

# # # # #     user_msg = data.get("text", "")
# # # # #     analysis = data.get("analysis")

# # # # #     log.info("[STREAM] User: %s", user_msg)

# # # # #     # If local streaming is disabled → instantly fallback
# # # # #     if not USE_LOCAL_LLM:
# # # # #         return Response("[Streaming disabled (online model not enabled).]", mimetype="text/plain")

# # # # #     # Return streaming generator
# # # # #     return Response(call_local_llm_stream(user_msg, analysis), mimetype="text/plain")


# # # # # # ------------------------------------------
# # # # # # NON-STREAMING FALLBACK (ALWAYS WORKS)
# # # # # # ------------------------------------------
# # # # # @app.post("/chat")
# # # # # def chat_fallback():
# # # # #     data = request.get_json(silent=True) or {}

# # # # #     user_msg = data.get("text", "")
# # # # #     analysis = data.get("analysis")

# # # # #     log.info("[FALLBACK] User: %s", user_msg)

# # # # #     # Use analysis summary if available
# # # # #     if analysis:
# # # # #         emotional_summary = f"""
# # # # # Detected mental state: {analysis.get('mental_state')}
# # # # # Emotion: {analysis.get('emotion')}
# # # # # Severity: {analysis.get('severity')}
# # # # # Suicide Risk: {analysis.get('suicide_risk')}
# # # # # """.strip()
# # # # #     else:
# # # # #         emotional_summary = "No recent analysis available."

# # # # #     reply = f"""
# # # # # I hear you. You said: “{user_msg}”

# # # # # Your emotional state from the latest analysis:
# # # # # {emotional_summary}

# # # # # Based on what I'm seeing, this might be a meaningful time to begin a paid therapy session with THE MIND MATTERS.  
# # # # # I can guide you, help prepare, or answer any questions you may have.
# # # # #     """.strip()

# # # # #     return jsonify({"reply": reply})


# # # # # # ------------------------------------------
# # # # # # MAIN
# # # # # # ------------------------------------------
# # # # # if __name__ == "__main__":
# # # # #     log.info("Starting THE MIND MATTERS Chat API on 127.0.0.1:5100 ...")
# # # # #     app.run(host="0.0.0.0", port=5100)


# # # # import json
# # # # import logging
# # # # import requests
# # # # from flask import Flask, request, Response, jsonify
# # # # from flask_cors import CORS

# # # # # ------------------------------------------
# # # # # FLASK APP + CORS
# # # # # ------------------------------------------
# # # # app = Flask(__name__)
# # # # CORS(app, resources={r"/*": {"origins": "*"}})

# # # # logging.basicConfig(level=logging.INFO)
# # # # log = logging.getLogger("api_chat")

# # # # # ------------------------------------------
# # # # # SETTINGS
# # # # # ------------------------------------------
# # # # USE_LOCAL_LLM = False     # local streaming off (no model running)
# # # # LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"

# # # # SYSTEM_PROMPT = """
# # # # You are THE MIND MATTERS therapy assistant.
# # # # Provide emotional support, clarity, and recommend paid therapy with THE MIND MATTERS when needed.
# # # # Use analysis if available.
# # # # Be warm, human-like, and helpful.
# # # # """

# # # # # ------------------------------------------
# # # # # LOCAL STREAM (ONLY IF ENABLED)
# # # # # ------------------------------------------
# # # # def call_local_llm_stream(user_msg, analysis=None):
# # # #     try:
# # # #         payload = {
# # # #             "model": "local-model",
# # # #             "stream": True,
# # # #             "messages": [
# # # #                 {"role": "system", "content": SYSTEM_PROMPT}
# # # #             ]
# # # #         }

# # # #         if analysis:
# # # #             payload["messages"].append({
# # # #                 "role": "system",
# # # #                 "content": f"Latest analysis: {json.dumps(analysis)}"
# # # #             })

# # # #         payload["messages"].append({"role": "user", "content": user_msg})

# # # #         with requests.post(LOCAL_LLM_URL, json=payload, stream=True) as r:
# # # #             for line in r.iter_lines():
# # # #                 if not line:
# # # #                     continue
# # # #                 try:
# # # #                     j = json.loads(line.decode("utf-8"))
# # # #                     if "choices" in j:
# # # #                         delta = j["choices"][0]["delta"]
# # # #                         if "content" in delta:
# # # #                             yield delta["content"]
# # # #                 except:
# # # #                     continue

# # # #     except Exception as e:
# # # #         log.error("STREAM ERROR: %s", e)
# # # #         yield "[Streaming failed.] "

# # # # # ------------------------------------------
# # # # # STREAM ENDPOINT
# # # # # ------------------------------------------
# # # # @app.post("/chat/stream")
# # # # def chat_stream():
# # # #     data = request.get_json(silent=True) or {}

# # # #     user_msg = data.get("text", "")
# # # #     analysis = data.get("analysis")

# # # #     log.info("[STREAM] %s", user_msg)

# # # #     if not USE_LOCAL_LLM:
# # # #         return Response("[Streaming disabled (online model not enabled).]", mimetype="text/plain")

# # # #     return Response(call_local_llm_stream(user_msg, analysis), mimetype="text/plain")

# # # # # ------------------------------------------
# # # # # NON-STREAM FALLBACK
# # # # # ------------------------------------------
# # # # @app.post("/chat")
# # # # def chat_fallback():
# # # #     data = request.get_json(silent=True) or {}

# # # #     user_msg = data.get("text", "")
# # # #     analysis = data.get("analysis")

# # # #     log.info("[FALLBACK] %s", user_msg)

# # # #     if analysis:
# # # #         summary = f"""
# # # # Mental: {analysis.get('mental_state')}
# # # # Emotion: {analysis.get('emotion')}
# # # # Severity: {analysis.get('severity')}
# # # # Suicide Risk: {analysis.get('suicide_risk')}
# # # # """.strip()
# # # #     else:
# # # #         summary = "No analysis available."

# # # #     reply = f"""
# # # # I hear you. You said: "{user_msg}"

# # # # Your emotional state:
# # # # {summary}

# # # # Based on what I'm seeing, this could be a meaningful time to begin a paid therapy session with THE MIND MATTERS.
# # # # I can support you, answer questions, or help you prepare.
# # # # """.strip()

# # # #     return jsonify({"reply": reply})

# # # # # ------------------------------------------
# # # # # RUN SERVER
# # # # # ------------------------------------------
# # # # if __name__ == "__main__":
# # # #     log.info("THE MIND MATTERS Chat API running on 127.0.0.1:5100")
# # # #     app.run(host="0.0.0.0", port=5100)



# # # import json
# # # import logging
# # # from flask import Flask, request, Response, jsonify
# # # from flask_cors import CORS
# # # import requests

# # # app = Flask(__name__)
# # # CORS(app)

# # # logging.basicConfig(level=logging.INFO)
# # # log = logging.getLogger("api_chat")

# # # # -----------------------------------------------------
# # # # SETTINGS
# # # # -----------------------------------------------------
# # # USE_LOCAL_LLM = False       # STREAMING OFF (safe mode)
# # # LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"

# # # SYSTEM_PROMPT = """
# # # You are THE MIND MATTERS therapy assistant.
# # # You provide emotional support, mental-health guidance, and gently suggest
# # # paid therapy sessions with THE MIND MATTERS when appropriate.
# # # Use the analysis (if provided) to personalize responses.
# # # Always be empathetic, warm and conversational.
# # # """

# # # # -----------------------------------------------------
# # # # STREAMING GENERATOR (used only if USE_LOCAL_LLM=True)
# # # # -----------------------------------------------------
# # # def call_local_llm_stream(user_msg, analysis=None):
# # #     try:
# # #         payload = {
# # #             "model": "local-model",
# # #             "stream": True,
# # #             "messages": [
# # #                 {"role": "system", "content": SYSTEM_PROMPT},
# # #             ]
# # #         }

# # #         if analysis:
# # #             payload["messages"].append({
# # #                 "role": "system",
# # #                 "content": f"Latest analysis: {json.dumps(analysis)}"
# # #             })

# # #         payload["messages"].append({"role": "user", "content": user_msg})

# # #         with requests.post(LOCAL_LLM_URL, json=payload, stream=True) as r:
# # #             for line in r.iter_lines():
# # #                 if not line:
# # #                     continue
# # #                 try:
# # #                     j = json.loads(line.decode("utf-8"))
# # #                     if "choices" in j:
# # #                         delta = j["choices"][0]["delta"]
# # #                         if "content" in delta:
# # #                             yield delta["content"]
# # #                 except:
# # #                     continue

# # #     except Exception as e:
# # #         log.error("STREAM ERROR: %s", e)
# # #         # STREAMING ERROR MESSAGE REMOVED
# # #         return


# # # # -----------------------------------------------------
# # # # STREAM ENDPOINT
# # # # -----------------------------------------------------
# # # @app.post("/chat/stream")
# # # def chat_stream():
# # #     data = request.get_json(silent=True) or {}
# # #     user_msg = data.get("text", "")
# # #     analysis = data.get("analysis")

# # #     if USE_LOCAL_LLM:
# # #         return Response(call_local_llm_stream(user_msg, analysis), mimetype="text/plain")

# # #     # STREAMING DISABLED — return EMPTY RESPONSE
# # #     return Response("", mimetype="text/plain")


# # # # -----------------------------------------------------
# # # # NON-STREAM FALLBACK (ALWAYS WORKS)
# # # # -----------------------------------------------------
# # # @app.post("/chat")
# # # def chat_fallback():
# # #     data = request.get_json(silent=True) or {}
# # #     user_msg = data.get("text", "")
# # #     analysis = data.get("analysis")

# # #     # Build human-like response
# # #     reply = f"""
# # # I hear you. You said: "{user_msg}"

# # # From your recent emotional analysis:
# # # {analysis if analysis else "No analysis available."}

# # # If you're open to it, this could be a meaningful time to begin a paid therapy
# # # session with THE MIND MATTERS — I can guide you or answer anything you want.
# # #     """.strip()

# # #     return jsonify({"reply": reply})


# # # # -----------------------------------------------------
# # # # RUN
# # # # -----------------------------------------------------
# # # if __name__ == "__main__":
# # #     log.info("Starting THE MIND MATTERS Chat API on 127.0.0.1:5100 ...")
# # #     app.run(host="0.0.0.0", port=5100)







# # from flask import Flask, request, jsonify
# # from flask_cors import CORS
# # import random

# # app = Flask(__name__)
# # CORS(app)

# # # -------------------------------
# # # SUPPORTIVE TEMPLATES (Generative)
# # # -------------------------------

# # EMOTION_RESPONSES = {
# #     "anxiety": [
# #         "It sounds like your mind has been feeling overwhelmed. I want you to know you're not alone in this.",
# #         "Anxiety can be exhausting. I'm really glad you shared this.",
# #         "You seem burdened lately. Let's walk through this together."
# #     ],
# #     "guilt": [
# #         "Guilt can weigh heavily on the heart. Thank you for opening up about it.",
# #         "It sounds like you're being too harsh on yourself.",
# #         "Guilt often hides deeper emotions. I'm here with you."
# #     ],
# #     "sadness": [
# #         "I'm sorry you're feeling low. Thank you for trusting me with this.",
# #         "Sadness can be heavy, but you don't have to carry it alone.",
# #         "It seems you’re going through a lot emotionally."
# #     ],
# #     "anger": [
# #         "Your frustration is valid. Let’s talk through what’s causing it.",
# #         "Anger can come from hurt or stress. I’m here to listen.",
# #         "It seems like something has really affected you."
# #     ],
# #     "neutral": [
# #         "I hear you. Let’s explore what you've been feeling more deeply.",
# #         "Thanks for sharing. Tell me more about what's been going on.",
# #         "I’m here to support you with whatever you're thinking."
# #     ]
# # }


# # SEVERITY_RECOMMEND = {
# #     "mild": [
# #         "This might be a good time to reflect gently on what you're experiencing.",
# #         "Your feelings matter. Let's work through them step by step."
# #     ],
# #     "moderate": [
# #         "Based on this, I genuinely think a paid therapy session with THE MIND MATTERS could help.",
# #         "Your emotional load seems moderate. A professional session might guide you better."
# #     ],
# #     "severe": [
# #         "I strongly recommend beginning a paid therapy session with THE MIND MATTERS as soon as possible.",
# #         "Your feelings seem intense. Getting professional support would be very meaningful."
# #     ]
# # }

# # FINAL_THERAPY_LINE = [
# #     "If you'd like, I can help you get started with a therapy session.",
# #     "Would you like guidance on how to begin therapy with THE MIND MATTERS?",
# #     "You deserve support — therapy could be a strong next step for you."
# # ]


# # # -------------------------------
# # # GENERATIVE FUNCTION
# # # -------------------------------

# # def generate_reply(user_msg, analysis):
# #     mental = analysis.get("mental_state", "neutral")
# #     emotion = analysis.get("emotion", "neutral")
# #     severity = analysis.get("severity", "mild")

# #     # emotion-based tone
# #     emo_text = random.choice(EMOTION_RESPONSES.get(emotion, EMOTION_RESPONSES["neutral"]))

# #     # severity-based guidance
# #     sev_text = random.choice(SEVERITY_RECOMMEND.get(severity, SEVERITY_RECOMMEND["mild"]))

# #     # final suggestion
# #     therapy_line = random.choice(FINAL_THERAPY_LINE)

# #     # combine all
# #     reply = (
# #         f"{emo_text}\n\n"
# #         f"You said: \"{user_msg}\".\n\n"
# #         f"From the latest analysis: mental state **{mental}**, emotion **{emotion}**, severity **{severity}**.\n\n"
# #         f"{sev_text}\n\n"
# #         f"{therapy_line}"
# #     )

# #     return reply


# # # -------------------------------
# # # MAIN CHAT ENDPOINT
# # # -------------------------------

# # @app.post("/chat")
# # def chat():
# #     data = request.get_json(silent=True) or {}
# #     user_msg = data.get("text", "")
# #     analysis = data.get("analysis") or {}

# #     reply = generate_reply(user_msg, analysis)
# #     return jsonify({"reply": reply})


# # # -------------------------------
# # # START SERVER
# # # -------------------------------

# # if __name__ == "__main__":
# #     print("💬 THE MIND MATTERS Generative Chat API running on 127.0.0.1:5100")
# #     app.run(host="0.0.0.0", port=5100)
# # # # # # # #     a = (                                   



















# # ================================================================
# # api_chat.py — Smart Dynamic Therapy Chatbot (NO LLM NEEDED)
# # THE MIND MATTERS ©
# # ================================================================

# from flask import Flask, request, jsonify
# from flask_cors import CORS
# import random
# import json

# app = Flask(__name__)
# CORS(app)

# # ================================================================
# # Helper: Dynamic Therapy Replies (Random + Analysis Aware)
# # ================================================================

# def generate_dynamic_reply(user_msg, analysis):
#     mental = analysis.get("mental_state", "normal")
#     emotion = analysis.get("emotion", "neutral")
#     severity = analysis.get("severity", "mild")
#     risk = analysis.get("suicide_risk", "none")
#     indicators = analysis.get("indicators", [])

#     indicator_text = ", ".join(indicators) if indicators else "no strong symptoms"

#     # ------------------------------------------------------------
#     # Base responses (randomly selected)
#     # ------------------------------------------------------------
#     base_responses = [
#         f"I understand what you're feeling. Your message shows {emotion}, and it's completely okay to feel that way.",
#         f"It sounds like you're going through {emotion}. I'm here to help you process it.",
#         f"I hear you — your mind is carrying a lot right now, especially with {emotion}.",
#         f"Thank you for sharing that with me. It takes courage to open up about {emotion}.",
#         f"I'm here with you. Your feelings of {emotion} matter, and you're not alone.",
#     ]

#     # ------------------------------------------------------------
#     # Severity-based guidance
#     # ------------------------------------------------------------
#     severity_responses = {
#         "mild": [
#             "This seems manageable, and I believe with the right steps you can feel better.",
#             "Small emotional shifts can help a lot. I can guide you through them.",
#         ],
#         "moderate": [
#             "Your emotional weight seems moderate — not too light, not too heavy. We can navigate this together.",
#             "I see noticeable stress here. Let me support you through it.",
#         ],
#         "severe": [
#             "Your emotional difficulty seems intense. It's important you don't handle this alone.",
#             "This is quite heavy emotionally — you're strong, and I'll help you through it step by step.",
#         ],
#     }

#     # ------------------------------------------------------------
#     # Risk-based therapy suggestion
#     # ------------------------------------------------------------
#     therapy_recommend = []
    
#     if severity in ["moderate", "severe"] or risk in ["moderate", "high"]:
#         therapy_recommend = [
#             "Based on what I'm sensing, this may be a good time to consider a paid therapy session with **THE MIND MATTERS**.",
#             "Your patterns suggest deeper support could help — would you like me to guide you toward a therapy session?",
#             "This emotional state can improve faster with therapy. I'm here to help you schedule with THE MIND MATTERS if you’d like.",
#         ]
#     else:
#         therapy_recommend = [
#             "If at any time you feel overwhelmed, remember therapy is always an option — no pressure.",
#             "If you ever feel ready, THE MIND MATTERS offers supportive therapy sessions.",
#         ]

#     # ------------------------------------------------------------
#     # Combine all layers into one final response
#     # ------------------------------------------------------------
#     final_response = (
#         random.choice(base_responses)
#         + "\n\n"
#         + f"Your analysis shows: **{mental}**, emotion **{emotion}**, severity **{severity}**, and {indicator_text}."
#         + "\n\n"
#         + random.choice(severity_responses.get(severity, ["You’re doing your best, and that matters."]))
#         + "\n\n"
#         + random.choice(therapy_recommend)
#     )

#     return final_response.strip()


# # ================================================================
# # Chat endpoint (NO STREAMING)
# # ================================================================

# @app.post("/chat")
# def chat():
#     data = request.get_json(force=True)
#     user_msg = data.get("text", "")
#     analysis = data.get("analysis", {})

#     if not user_msg:
#         return jsonify({"reply": "I’m here whenever you want to talk."})

#     reply = generate_dynamic_reply(user_msg, analysis)
#     return jsonify({"reply": reply})


# # ================================================================
# # Start server
# # ================================================================
# if __name__ == "__main__":
#     print("🔥 THE MIND MATTERS Chat API running on 127.0.0.1:5100")
#     app.run(host="0.0.0.0", port=5100, debug=False)
# # ================================================================  






# ============================
# THE MIND MATTERS - CHAT API
# ============================

from flask import Flask, request, jsonify
from flask_cors import CORS
import random

app = Flask(__name__)
CORS(app)

SYSTEM_STYLE = [
    "I understand, that must be difficult.",
    "Thanks for sharing with me.",
    "You're not alone in this.",
    "I’m here with you.",
    "It’s okay to feel this way.",
]

THERAPY_PUSH = [
    "It may be a good time to consider a paid therapy session with THE MIND MATTERS.",
    "If you want, I can help you book a therapy session.",
    "Professional support can help a lot — consider scheduling therapy.",
    "Talking to a therapist might really help you right now.",
]

def generate_reply(user_msg, analysis):

    style = random.choice(SYSTEM_STYLE)
    therapy = random.choice(THERAPY_PUSH)

    mental = analysis.get("mental_state", "normal")
    emotion = analysis.get("emotion", "neutral")
    severity = analysis.get("severity", "low")
    risk = analysis.get("suicide_risk", "none")

    msg = f"{style}\n\n"

    msg += f"I see you're experiencing **{mental}**, with emotions of **{emotion}**.\n"

    if severity in ["moderate", "severe"]:
        msg += f"Your severity looks **{severity}**, so please take care.\n"

    if risk in ["moderate", "high"]:
        msg += f"There is some risk detected (**{risk}**). You deserve proper support.\n"

    msg += "\nWhat you said: “" + user_msg + "”\n\n"

    # 40% random therapy push (so same msg repeat nahi hoga)
    if random.random() < 0.40:
        msg += therapy + "\n"

    # dynamic helpful reply
    msg += random.choice([
        "Can you tell me what part of this is affecting you the most?",
        "What happened before you started feeling this way?",
        "I'm listening — what would you like to talk about next?",
        "What support do you feel you need right now?",
    ])

    return msg


@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    user_msg = data.get("text", "")
    analysis = data.get("analysis", {}) or {}

    reply = generate_reply(user_msg, analysis)
    return jsonify({"reply": reply})


if __name__ == "__main__":
    print("THE MIND MATTERS Chat API running on 5100...")
    app.run(host="0.0.0.0", port=5100)
