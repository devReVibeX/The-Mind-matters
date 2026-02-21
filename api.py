# # # ==============================================================
# # # api.py — FLASK VERSION (JUST RUN: python api.py)
# # # ==============================================================

# # import warnings
# # warnings.filterwarnings("ignore")

# # import os
# # import sys
# # import random
# # import torch
# # import torch.nn as nn
# # from flask import Flask, request, jsonify
# # from transformers import AutoTokenizer, XLMRobertaModel

# # # ==============================================================
# # # MODEL PATH
# # # ==============================================================

# # MODEL_DIR = r"C:\Users\isneh\Downloads\mental matters\mental_model_custom"

# # # ==============================================================
# # # LABEL SPACES
# # # ==============================================================

# # MENTAL = ["depression","anxiety","stress","trauma","burnout","normal"]
# # EMO = ["sadness","fear","anger","guilt","shame","loneliness","hopelessness","neutral","other"]
# # SEV = ["mild","moderate","severe"]
# # RISK = ["none","low","moderate","high"]
# # IND  = ["sleep_issues","appetite_change","fatigue","overthinking","concentration_problems"]

# # # ==============================================================
# # # LOAD TOKENIZER
# # # ==============================================================

# # tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)

# # # ==============================================================
# # # LOAD BACKBONE SAFELY
# # # ==============================================================

# # print("Loading XLM-R backbone...")
# # backbone = XLMRobertaModel.from_pretrained("xlm-roberta-base")

# # print("Loading fine-tuned weights...")
# # finetuned_state = torch.load(
# #     os.path.join(MODEL_DIR, "pytorch_model.bin"),
# #     map_location="cpu"
# # )

# # backbone.load_state_dict(finetuned_state, strict=False)
# # H = backbone.config.hidden_size

# # # ==============================================================
# # # LOAD CUSTOM HEADS
# # # ==============================================================

# # print("Loading classifier heads...")
# # heads = torch.load(os.path.join(MODEL_DIR, "custom_heads.pt"), map_location="cpu")

# # # ==============================================================
# # # BUILD MODEL
# # # ==============================================================

# # class MentalModel(nn.Module):
# #     def __init__(self):
# #         super().__init__()
# #         self.backbone = backbone

# #         self.m = nn.Linear(H, len(MENTAL))
# #         self.e = nn.Linear(H, len(EMO))
# #         self.s = nn.Linear(H, len(SEV))
# #         self.r = nn.Linear(H, len(RISK))
# #         self.i = nn.Linear(H, len(IND))

# #         self.m.load_state_dict(heads["m"])
# #         self.e.load_state_dict(heads["e"])
# #         self.s.load_state_dict(heads["s"])
# #         self.r.load_state_dict(heads["r"])
# #         self.i.load_state_dict(heads["i"])

# #     def forward(self, ids, mask):
# #         x = self.backbone(ids, attention_mask=mask).last_hidden_state[:,0]
# #         return {
# #             "mental": self.m(x),
# #             "emotion": self.e(x),
# #             "severity": self.s(x),
# #             "risk": self.r(x),
# #             "indicators": self.i(x)
# #         }

# # model = MentalModel().eval()
# # print("Model ready.")

# # # ==============================================================
# # # GENERATIVE REASONER
# # # ==============================================================

# # def generate_reasoning(text, mental, emotion, severity, risk, indicators, conf):

# #     intro = random.choice([
# #         "deep emotional mapping",
# #         "multi-layer cognitive analysis",
# #         "psychological interpretation",
# #         "context-aware emotional decoding",
# #         "behavioral signal analysis"
# #     ])

# #     mental_map = {
# #         "depression": "shows emotional heaviness and inner sadness.",
# #         "anxiety": "reflects fear loops and overthinking.",
# #         "stress": "indicates overload and mental pressure.",
# #         "trauma": "contains signs of past emotional wounds.",
# #         "burnout": "signals exhaustion and emotional depletion.",
# #         "normal": "represents a stable emotional state."
# #     }

# #     emotion_map = {
# #         "sadness": "sorrow and low mood detected.",
# #         "fear": "fear-driven patterns detected.",
# #         "anger": "frustration or irritation detected.",
# #         "guilt": "self-blame signals detected.",
# #         "shame": "self-image conflict detected.",
# #         "loneliness": "isolation feelings detected.",
# #         "hopelessness": "loss of direction detected.",
# #         "neutral": "calm emotional tone.",
# #         "other": "mixed emotional patterns."
# #     }

# #     sev_map = {
# #         "mild": "mild emotional intensity.",
# #         "moderate": "moderate emotional distress.",
# #         "severe": "strong emotional intensity."
# #     }

# #     risk_map = {
# #         "none": "no harmful intent detected.",
# #         "low": "slight concerning thoughts detected.",
# #         "moderate": "moderate risk signals detected.",
# #         "high": "high risk cues detected."
# #     }

# #     ind_text = ", ".join(indicators) if indicators else "No strong symptoms detected."

# #     return f"""
# # AI Interpretation ({intro})

# # Mental State: {mental} → {mental_map[mental]}
# # Emotion: {emotion} → {emotion_map[emotion]}
# # Severity: {severity} → {sev_map[severity]}
# # Suicide Risk: {risk} → {risk_map[risk]}
# # Indicators: {ind_text}

# # Confidence:
# # Mental={conf['mental']:.2f}, Emotion={conf['emotion']:.2f}, 
# # Severity={conf['severity']:.2f}, Risk={conf['risk']:.2f}

# # (This is a generative AI reasoning summary.)
# # """

# # # ==============================================================
# # # FLASK SETUP
# # # ==============================================================

# # app = Flask(__name__)

# # @app.route("/", methods=["GET"])
# # def home():
# #     return {"status": "OK", "message": "Mental Gen-AI (Flask) Running"}

# # @app.route("/analyze", methods=["POST"])
# # def analyze():
# #     data = request.json
# #     text = data.get("text", "")

# #     enc = tokenizer(text, return_tensors="pt", truncation=True, padding=True)

# #     with torch.no_grad():
# #         out = model(enc["input_ids"], enc["attention_mask"])

# #     mental = MENTAL[out["mental"].argmax().item()]
# #     emotion = EMO[out["emotion"].argmax().item()]
# #     severity = SEV[out["severity"].argmax().item()]
# #     risk = RISK[out["risk"].argmax().item()]

# #     ind_sig = out["indicators"].sigmoid().squeeze().tolist()
# #     indicators = [IND[i] for i,v in enumerate(ind_sig) if v > 0.5]

# #     conf = {
# #         "mental": float(torch.softmax(out["mental"], dim=-1).max()),
# #         "emotion": float(torch.softmax(out["emotion"], dim=-1).max()),
# #         "severity": float(torch.softmax(out["severity"], dim=-1).max()),
# #         "risk": float(torch.softmax(out["risk"], dim=-1).max())
# #     }

# #     reasoning = generate_reasoning(
# #         text, mental, emotion, severity, risk, indicators, conf
# #     )

# #     return jsonify({
# #         "input": text,
# #         "mental_state": mental,
# #         "emotion": emotion,
# #         "severity": severity,
# #         "suicide_risk": risk,
# #         "indicators": indicators,
# #         "confidence": conf,
# #         "analysis": reasoning
# #     })


# # # ==============================================================
# # # RUN SERVER (DIRECT)
# # # ==============================================================

# # if __name__ == "__main__":
# #     print("Starting Flask API on http://127.0.0.1:5000 ...")
# #     app.run(host="0.0.0.0", port=5000, debug=False)


# # ==============================================================
# # api.py — THE MIND MATTERS (Premium Analyzer API)
# # Run using: python api.py
# # ==============================================================

# import warnings
# warnings.filterwarnings("ignore")

# import os
# import random
# import torch
# import torch.nn as nn
# from flask import Flask, request, jsonify
# from flask_cors import CORS
# from transformers import AutoTokenizer, XLMRobertaModel

# # ============================================================== 
# # CONFIGURATION
# # ==============================================================

# MODEL_DIR = r"C:\Users\isneh\Downloads\mental matters\mental_model_custom"
# DEVICE = "cpu"  # (use "cuda" if available)

# MENTAL = ["depression","anxiety","stress","trauma","burnout","normal"]
# EMO = ["sadness","fear","anger","guilt","shame","loneliness","hopelessness","neutral","other"]
# SEV = ["mild","moderate","severe"]
# RISK = ["none","low","moderate","high"]
# IND  = ["sleep_issues","appetite_change","fatigue","overthinking","concentration_problems"]

# # ============================================================== 
# # TOKENIZER
# # ==============================================================

# print("🔄 Loading tokenizer...")
# tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)

# # ============================================================== 
# # LOAD BACKBONE (SAFE MODE)
# # ==============================================================

# print("🔄 Loading XLM-R backbone...")
# backbone = XLMRobertaModel.from_pretrained("xlm-roberta-base")

# print("🔄 Loading fine-tuned model weights...")
# finetuned_state = torch.load(
#     os.path.join(MODEL_DIR, "pytorch_model.bin"),
#     map_location=DEVICE
# )

# backbone.load_state_dict(finetuned_state, strict=False)
# H = backbone.config.hidden_size

# # ============================================================== 
# # LOAD CUSTOM HEADS
# # ==============================================================

# print("🔄 Loading classifier heads...")
# heads = torch.load(os.path.join(MODEL_DIR, "custom_heads.pt"), map_location=DEVICE)

# # ============================================================== 
# # BUILD FINAL MODEL CLASS
# # ==============================================================

# class MentalModel(nn.Module):
#     def __init__(self):
#         super().__init__()
#         self.backbone = backbone

#         self.m = nn.Linear(H, len(MENTAL))
#         self.e = nn.Linear(H, len(EMO))
#         self.s = nn.Linear(H, len(SEV))
#         self.r = nn.Linear(H, len(RISK))
#         self.i = nn.Linear(H, len(IND))

#         # load custom heads
#         self.m.load_state_dict(heads["m"])
#         self.e.load_state_dict(heads["e"])
#         self.s.load_state_dict(heads["s"])
#         self.r.load_state_dict(heads["r"])
#         self.i.load_state_dict(heads["i"])

#     def forward(self, ids, mask):
#         x = self.backbone(ids, attention_mask=mask).last_hidden_state[:,0]
#         return {
#             "mental": self.m(x),
#             "emotion": self.e(x),
#             "severity": self.s(x),
#             "risk": self.r(x),
#             "indicators": self.i(x)
#         }

# print("🔄 Building model...")
# model = MentalModel().to(DEVICE).eval()

# print("✔ Model Loaded Successfully\n")

# # ============================================================== 
# # REASONING ENGINE — CLEANER, PREMIUM VERSION
# # ==============================================================

# def generate_reasoning(text, m, emo, sev, risk, indicators, conf):

#     style = random.choice([
#         "contextual mapping",
#         "deep emotional reasoning",
#         "psychological interpretation",
#         "pattern recognition",
#         "behavioral signal decoding"
#     ])

#     mental_map = {
#         "depression": "shows emotional heaviness and withdrawal.",
#         "anxiety": "indicates worry loops and mental tension.",
#         "stress": "reveals overload and pressure patterns.",
#         "trauma": "reflects past unresolved emotional wounds.",
#         "burnout": "signals exhaustion and emotional depletion.",
#         "normal": "reflects a relatively stable emotional state."
#     }

#     emo_map = {
#         "sadness": "sorrow and emotional heaviness detected.",
#         "fear": "fear-driven thinking noticed.",
#         "anger": "frustration or irritation present.",
#         "guilt": "self-blame or internal conflict detected.",
#         "shame": "self-image conflict signals observed.",
#         "loneliness": "feelings of isolation detected.",
#         "hopelessness": "loss of direction or despair signals present.",
#         "neutral": "emotion appears balanced.",
#         "other": "mixed emotional patterns detected."
#     }

#     sev_map = {
#         "mild": "mild emotional intensity.",
#         "moderate": "moderate-level distress.",
#         "severe": "strong emotional impact detected."
#     }

#     risk_map = {
#         "none": "no harmful intent found.",
#         "low": "slightly concerning emotional undertones.",
#         "moderate": "moderate-risk cues detected.",
#         "high": "strong risk signals detected."
#     }

#     ind_text = ", ".join(indicators) if indicators else "No strong symptoms detected."

#     return f"""
# AI Interpretation ({style})

# Mental State: {m} → {mental_map[m]}
# Emotion: {emo} → {emo_map[emo]}
# Severity: {sev} → {sev_map[sev]}
# Suicide Risk: {risk} → {risk_map[risk]}
# Indicators: {ind_text}

# Confidence Scores:
# • Mental: {conf['mental']:.2f}
# • Emotion: {conf['emotion']:.2f}
# • Severity: {conf['severity']:.2f}
# • Risk: {conf['risk']:.2f}

# (This summary is AI-generated based on emotional & contextual cues.)
# """

# # ============================================================== 
# # FLASK API
# # ==============================================================

# app = Flask(__name__)
# CORS(app)

# @app.route("/", methods=["GET"])
# def home():
#     return {"status": "OK", "message": "THE MIND MATTERS — Analyzer API Running"}

# # ============================================================== 
# # ANALYZE ENDPOINT
# # ==============================================================

# @app.route("/analyze", methods=["POST"])
# def analyze():
#     data = request.json
#     text = data.get("text", "").strip()

#     if not text:
#         return jsonify({"error": "Text cannot be empty"}), 400

#     enc = tokenizer(text, return_tensors="pt", truncation=True, padding=True)
#     ids, mask = enc["input_ids"].to(DEVICE), enc["attention_mask"].to(DEVICE)

#     with torch.no_grad():
#         out = model(ids, mask)

#     mental = MENTAL[out["mental"].argmax().item()]
#     emotion = EMO[out["emotion"].argmax().item()]
#     severity = SEV[out["severity"].argmax().item()]
#     risk = RISK[out["risk"].argmax().item()]

#     ind_sig = out["indicators"].sigmoid().squeeze().tolist()
#     indicators = [IND[i] for i,v in enumerate(ind_sig) if v > 0.5]

#     conf = {
#         "mental": float(torch.softmax(out["mental"], dim=-1).max()),
#         "emotion": float(torch.softmax(out["emotion"], dim=-1).max()),
#         "severity": float(torch.softmax(out["severity"], dim=-1).max()),
#         "risk": float(torch.softmax(out["risk"], dim=-1).max())
#     }

#     reasoning = generate_reasoning(text, mental, emotion, severity, risk, indicators, conf)

#     return jsonify({
#         "input": text,
#         "mental_state": mental,
#         "emotion": emotion,
#         "severity": severity,
#         "suicide_risk": risk,
#         "indicators": indicators,
#         "confidence": conf,
#         "analysis": reasoning
#     })

# # ============================================================== 
# # RUN SERVER
# # ==============================================================

# if __name__ == "__main__":
#     print("🚀 THE MIND MATTERS — Analyzer running at http://127.0.0.1:5000")
#     app.run(host="0.0.0.0", port=5000, debug=False)




# ==============================================================
# api.py — FINAL FIXED VERSION (CORS + JSON + CLEAN OUTPUT)
# ==============================================================

import warnings
warnings.filterwarnings("ignore")

import os
import torch
import torch.nn as nn
from flask import Flask, request, jsonify
from flask_cors import CORS
from transformers import AutoTokenizer, XLMRobertaModel

# ==============================================================

MODEL_DIR = r"C:\Users\isneh\Downloads\mental matters\mental_model_custom"

MENTAL = ["depression","anxiety","stress","trauma","burnout","normal"]
EMO    = ["sadness","fear","anger","guilt","shame","loneliness","hopelessness","neutral","other"]
SEV    = ["mild","moderate","severe"]
RISK   = ["none","low","moderate","high"]
IND    = ["sleep_issues","appetite_change","fatigue","overthinking","concentration_problems"]

# ==============================================================

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)

print("Loading backbone...")
backbone = XLMRobertaModel.from_pretrained("xlm-roberta-base")

print("Loading fine-tuned weights...")
finetuned_state = torch.load(os.path.join(MODEL_DIR, "pytorch_model.bin"), map_location="cpu")
backbone.load_state_dict(finetuned_state, strict=False)

H = backbone.config.hidden_size

print("Loading classifier heads...")
heads = torch.load(os.path.join(MODEL_DIR, "custom_heads.pt"), map_location="cpu")

# ==============================================================

class MentalModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = backbone

        self.m = nn.Linear(H, len(MENTAL))
        self.e = nn.Linear(H, len(EMO))
        self.s = nn.Linear(H, len(SEV))
        self.r = nn.Linear(H, len(RISK))
        self.i = nn.Linear(H, len(IND))

        self.m.load_state_dict(heads["m"])
        self.e.load_state_dict(heads["e"])
        self.s.load_state_dict(heads["s"])
        self.r.load_state_dict(heads["r"])
        self.i.load_state_dict(heads["i"])

    def forward(self, ids, mask):
        x = self.backbone(ids, attention_mask=mask).last_hidden_state[:, 0]
        return {
            "mental": self.m(x),
            "emotion": self.e(x),
            "severity": self.s(x),
            "risk": self.r(x),
            "indicators": self.i(x)
        }

model = MentalModel().eval()
print("Model Loaded Successfully ✔")

# ==============================================================

def make_reasoning(text, mental, emotion, severity, risk, indicators, conf):
    return (
        f"Mental State: {mental}\n"
        f"Emotion: {emotion}\n"
        f"Severity: {severity}\n"
        f"Suicide Risk: {risk}\n"
        f"Indicators: {', '.join(indicators) if indicators else 'None'}\n\n"
        f"Confidence → M:{conf['mental']:.2f}  "
        f"E:{conf['emotion']:.2f}  "
        f"S:{conf['severity']:.2f}  "
        f"R:{conf['risk']:.2f}\n"
    )

# ==============================================================

app = Flask(__name__)
CORS(app)       # VERY IMPORTANT — Fixes browser block

@app.route("/")
def home():
    return {"status": "OK"}

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.json
        text = data.get("text", "")

        enc = tokenizer(text, return_tensors="pt", truncation=True, padding=True)

        with torch.no_grad():
            out = model(enc["input_ids"], enc["attention_mask"])

        mental = MENTAL[out["mental"].argmax().item()]
        emotion = EMO[out["emotion"].argmax().item()]
        severity = SEV[out["severity"].argmax().item()]
        risk = RISK[out["risk"].argmax().item()]

        ind_prob = out["indicators"].sigmoid().squeeze().tolist()
        indicators = [IND[i] for i, v in enumerate(ind_prob) if v > 0.5]

        conf = {
            "mental": float(torch.softmax(out["mental"], dim=-1).max()),
            "emotion": float(torch.softmax(out["emotion"], dim=-1).max()),
            "severity": float(torch.softmax(out["severity"], dim=-1).max()),
            "risk": float(torch.softmax(out["risk"], dim=-1).max())
        }

        summary = make_reasoning(text, mental, emotion, severity, risk, indicators, conf)

        return jsonify({
            "input": text,
            "mental_state": mental,
            "emotion": emotion,
            "severity": severity,
            "suicide_risk": risk,
            "indicators": indicators,
            "confidence": conf,
            "analysis": summary
        })

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("Starting Flask API on 127.0.0.1:5000 ...")
    app.run(host="0.0.0.0", port=5000, debug=False)
