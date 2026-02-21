import csv
import os

# -----------------------------------------------------------
# SAVE LOCATION (YOUR WINDOWS PATH)
# -----------------------------------------------------------
SAVE_DIR = r"C:\Users\isneh\Downloads\mental matters"
os.makedirs(SAVE_DIR, exist_ok=True)

OUTPUT_FILE = rf"{SAVE_DIR}\mental_health_dataset_100k.csv"

N = 100000  # 1 lakh dataset

# -----------------------------------------------------------
# LABEL SPACES
# -----------------------------------------------------------
MENTAL_STATES = ["depression", "anxiety", "stress", "trauma", "burnout", "normal"]

EMOTIONS = [
    "sadness", "fear", "anger", "guilt", "shame",
    "loneliness", "hopelessness", "neutral", "other"
]

SEVERITIES = ["mild", "moderate", "severe"]

INDICATORS = {
    "sleep_issues": "I experience noticeable sleep difficulties.",
    "appetite_change": "My appetite has been fluctuating lately.",
    "fatigue": "I often feel drained and low on energy.",
    "overthinking": "I keep overthinking even small details.",
    "concentration_problems": "I find it hard to maintain focus."
}

SUICIDE_TEXT = {
    "none": "",
    "low": "I sometimes experience mild thoughts about giving up, but I stay in control.",
    "moderate": "I occasionally have troubling self-harm thoughts, yet I manage to stay safe.",
    "high": "I have been having serious distressing thoughts and feel I need immediate help."
}

# Text uniqueness modifiers
CONTEXT = [
    "Recently", "Lately", "These days", "In the past few weeks",
    "For some time now", "Currently", "Nowadays", "At present"
]

DETAIL = [
    "and it has been affecting my routine",
    "which concerns me a bit",
    "and I'm trying to cope with it",
    "and it feels overwhelming sometimes",
    "and it's noticeable to me",
    "and it disrupts my productivity",
    "and it has been getting stronger",
    "and it impacts my daily functioning"
]

EMOTION_PHRASE = {
    "sadness": "sad and low",
    "fear": "afraid and uneasy",
    "anger": "angry and irritated",
    "guilt": "guilty and regretful",
    "shame": "ashamed and uncomfortable",
    "loneliness": "isolated and lonely",
    "hopelessness": "hopeless and stuck",
    "neutral": "calm and neutral",
    "other": "a mix of different emotions"
}

SEVERITY_PHRASE = {
    "mild": "to a mild extent",
    "moderate": "to a moderate extent",
    "severe": "to a severe extent"
}

# -----------------------------------------------------------
# EXPANDED FIELDS
# -----------------------------------------------------------
SENTIMENT = ["positive", "neutral", "negative", "highly_negative"]

BEHAVIOR_PATTERNS = [
    "withdrawal", "avoidance", "agitation", "hypervigilance",
    "irritability", "social_isolation", "normal_behavior"
]

COPING = ["none", "unhealthy", "healthy", "mixed"]

TRIGGERS = [
    "work_pressure", "family_conflict", "past_trauma",
    "relationship_issue", "financial_stress", "academic_stress",
    "health_issues", "unknown"
]

DURATION = ["days", "weeks", "months", "years"]

FUNCTIONAL_IMPAIRMENT = ["none", "mild", "moderate", "severe"]

SLEEP_QUALITY = ["good", "fair", "poor", "very_poor"]

APPETITE_STATE = ["normal", "increased", "decreased", "unpredictable"]

ENERGY_LEVEL = ["high", "normal", "low", "very_low"]

CONCENTRATION_LEVEL = ["normal", "mild_issues", "moderate_issues", "severe_issues"]

HALLUCINATION = ["yes", "no"]

THERAPY_RECOMMENDATION = [
    "none", "self_help", "therapy", "urgent_care", "emergency_intervention"
]


# -----------------------------------------------------------
# LOGIC
# -----------------------------------------------------------
def pick_indicators(state, severity):
    mapping = {
        "depression": ["fatigue", "sleep_issues", "appetite_change"],
        "anxiety": ["overthinking", "sleep_issues", "concentration_problems"],
        "stress": ["concentration_problems", "fatigue", "sleep_issues"],
        "trauma": ["sleep_issues", "overthinking", "concentration_problems"],
        "burnout": ["fatigue", "concentration_problems"],
        "normal": []
    }

    base = mapping[state]
    if severity == "mild": return base[:1]
    if severity == "moderate": return base[:2]
    return base  # severe


def compute_suicide_risk(state, severity, emotion):
    if state in ["depression", "trauma"] and severity == "severe":
        return "high" if emotion == "hopelessness" else "moderate"
    if severity == "moderate":
        return "moderate" if emotion in ["sadness", "hopelessness"] else "low"
    return "none"


def risk_score_numeric(level):
    return {"none": 10, "low": 30, "moderate": 60, "high": 85}[level]


# -----------------------------------------------------------
# TEXT GENERATION
# -----------------------------------------------------------
def build_text(i, state, emotion, severity, indicators, suicide):
    context = CONTEXT[i % len(CONTEXT)]
    detail = DETAIL[i % len(DETAIL)]

    emo = EMOTION_PHRASE[emotion]
    sev = SEVERITY_PHRASE[severity]
    suicide_text = SUICIDE_TEXT[suicide]

    ind_text = " ".join([INDICATORS[x] for x in indicators])

    if state == "normal":
        return (
            f"{context}, I am feeling stable and {emo}. "
            f"My daily functioning is consistent and balanced."
        )

    return (
        f"{context}, I have been feeling {emo} {detail}. "
        f"My condition affects me {sev}. "
        f"{ind_text} {suicide_text}".strip()
    )


# -----------------------------------------------------------
# ROW GENERATOR
# -----------------------------------------------------------
def generate_row(i):
    state = MENTAL_STATES[i % len(MENTAL_STATES)]
    emotion = EMOTIONS[(i // len(MENTAL_STATES)) % len(EMOTIONS)]
    severity = SEVERITIES[(i // (len(MENTAL_STATES) * len(EMOTIONS))) % len(SEVERITIES)]

    indicators = pick_indicators(state, severity)
    suicide = compute_suicide_risk(state, severity, emotion)
    text = build_text(i, state, emotion, severity, indicators, suicide)

    return [
        i + 1,
        text,
        state,
        emotion,
        severity,
        suicide,
        "|".join(indicators),
        SENTIMENT[i % len(SENTIMENT)],
        BEHAVIOR_PATTERNS[i % len(BEHAVIOR_PATTERNS)],
        COPING[i % len(COPING)],
        TRIGGERS[i % len(TRIGGERS)],
        DURATION[i % len(DURATION)],
        FUNCTIONAL_IMPAIRMENT[i % len(FUNCTIONAL_IMPAIRMENT)],
        SLEEP_QUALITY[i % len(SLEEP_QUALITY)],
        APPETITE_STATE[i % len(APPETITE_STATE)],
        ENERGY_LEVEL[i % len(ENERGY_LEVEL)],
        CONCENTRATION_LEVEL[i % len(CONCENTRATION_LEVEL)],
        HALLUCINATION[i % len(HALLUCINATION)],
        THERAPY_RECOMMENDATION[i % len(THERAPY_RECOMMENDATION)],
        risk_score_numeric(suicide)
    ]


# -----------------------------------------------------------
# CREATE CSV
# -----------------------------------------------------------
with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)

    writer.writerow([
        "id", "text", "mental_state", "emotion", "severity", "suicide_risk",
        "indicators", "sentiment", "behavior_pattern", "coping_mechanisms",
        "trigger_type", "duration", "functional_impairment", "sleep_quality",
        "appetite", "energy_level", "concentration_level",
        "hallucination_or_delusion", "therapy_recommendation",
        "risk_score_numeric"
    ])

    for i in range(N):
        writer.writerow(generate_row(i))

print(f"✅ Dataset created successfully at:\n{OUTPUT_FILE}")
