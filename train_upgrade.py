# ======================================================================
# FAST TRAINING WITH CUSTOM DATASET SIZE (UPGRADED FOR HUGGINGFACE EXPORT)
# ======================================================================

import csv
import os
import json
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, XLMRobertaModel, PretrainedConfig
from tqdm import tqdm

# -----------------------------
# CONFIG (CHANGE THIS ONE VALUE)
# -----------------------------

DATASET_LIMIT = 1000     # <==========================
CSV_PATH = r"C:\Users\isneh\Downloads\mental matters\mental_health_dataset_100k.csv"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
BATCH = 16
EPOCHS = 1
LR = 2e-5
MAX_LEN = 96
ACCUM_STEPS = 2
FP16 = True if DEVICE == "cuda" else False

print("DEVICE =", DEVICE)
print(f"USING DATASET SIZE: {DATASET_LIMIT}")

# -----------------------------
# LABEL SPACE
# -----------------------------
MENTAL = ["depression","anxiety","stress","trauma","burnout","normal"]

EMO = [
    "sadness","fear","anger","guilt","shame",
    "loneliness","hopelessness","neutral","other"
]

SEV = ["mild","moderate","severe"]
RISK = ["none","low","moderate","high"]
IND  = ["sleep_issues","appetite_change","fatigue","overthinking","concentration_problems"]

m2id = {k:i for i,k in enumerate(MENTAL)}
e2id = {k:i for i,k in enumerate(EMO)}
s2id = {k:i for i,k in enumerate(SEV)}
r2id = {k:i for i,k in enumerate(RISK)}
i2id = {k:i for i,k in enumerate(IND)}

# -----------------------------
# CSV LOADER WITH LIMIT
# -----------------------------
def parse_indicators(v):
    vec = [0]*len(IND)
    if not v: return vec
    for x in v.split("|"):
        x = x.strip().lower()
        if x in i2id:
            vec[i2id[x]] = 1
    return vec

def load_csv(path, limit):
    out=[]
    with open(path,"r",encoding="utf-8") as f:
        r=csv.DictReader(f)
        for i,row in enumerate(r):
            if i >= limit:
                break
            
            out.append({
                "text": row["text"],
                "labels": [
                    m2id.get(row["mental_state"].lower(), 0),
                    e2id.get(row["emotion"].lower(), e2id["other"]),
                    s2id.get(row["severity"].lower(), 0),
                    r2id.get(row["suicide_risk"].lower(), 0),
                    *parse_indicators(row["indicators"])
                ]
            })
    return out

print("Loading CSV...")
rows = load_csv(CSV_PATH, DATASET_LIMIT)
print("Rows loaded:", len(rows))

# -----------------------------
# SPLIT
# -----------------------------
cut = int(0.8 * len(rows))
train = rows[:cut]
test  = rows[cut:]

# -----------------------------
# TOKENIZER
# -----------------------------
tok = AutoTokenizer.from_pretrained("xlm-roberta-base")

def encode(text):
    return tok(
        text,
        truncation=True,
        padding="max_length",
        max_length=MAX_LEN,
        return_tensors="pt"
    )

# -----------------------------
# DATASET CLASS
# -----------------------------
class MentalDS(Dataset):
    def __init__(self,data):
        self.d = data

    def __len__(self):
        return len(self.d)

    def __getitem__(self,idx):
        ex = self.d[idx]
        enc = encode(ex["text"])
        ids  = enc["input_ids"].squeeze(0)
        mask = enc["attention_mask"].squeeze(0)
        lab = torch.tensor(ex["labels"], dtype=torch.float)
        return ids, mask, lab

train_ds = MentalDS(train)
test_ds  = MentalDS(test)

train_loader = DataLoader(train_ds, batch_size=BATCH, shuffle=True)
test_loader  = DataLoader(test_ds, batch_size=BATCH)

print("Dataloaders ready.")

# -----------------------------
# CUSTOM CONFIG FOR EXPORT
# -----------------------------
class MentalHealthConfig(PretrainedConfig):
    model_type = "mental_health_model"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.num_mental = len(MENTAL)
        self.num_emotion = len(EMO)
        self.num_severity = len(SEV)
        self.num_suicide = len(RISK)
        self.num_indicators = len(IND)
        self.hidden_size = 768
        self.backbone = "xlm-roberta-base"


# -----------------------------
# MODEL
# -----------------------------
class Model(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = XLMRobertaModel.from_pretrained("xlm-roberta-base")
        H = self.backbone.config.hidden_size

        self.m = nn.Linear(H, len(MENTAL))
        self.e = nn.Linear(H, len(EMO))
        self.s = nn.Linear(H, len(SEV))
        self.r = nn.Linear(H, len(RISK))
        self.i = nn.Linear(H, len(IND))

        self.ce  = nn.CrossEntropyLoss()
        self.bce = nn.BCEWithLogitsLoss()

    def forward(self, ids, mask, labels=None):
        x = self.backbone(input_ids=ids, attention_mask=mask).last_hidden_state[:,0]

        lm = self.m(x)
        le = self.e(x)
        ls = self.s(x)
        lr = self.r(x)
        li = self.i(x)

        if labels is None:
            return lm, le, ls, lr, li

        loss = (
            self.ce(lm, labels[:,0].long()) +
            self.ce(le, labels[:,1].long()) +
            self.ce(ls, labels[:,2].long()) +
            self.ce(lr, labels[:,3].long()) +
            self.bce(li, labels[:,4:])
        )

        return loss

model = Model().to(DEVICE)
opt = torch.optim.AdamW(model.parameters(), lr=LR)
scaler = torch.cuda.amp.GradScaler(enabled=FP16)

# -----------------------------
# TRAINING
# -----------------------------
print("Training...")

for epoch in range(EPOCHS):
    model.train()
    total = 0
    opt.zero_grad()

    pbar = tqdm(train_loader, desc=f"Epoch {epoch+1}")

    for step, (ids,mask,lab) in enumerate(pbar):

        ids, mask, lab = ids.to(DEVICE), mask.to(DEVICE), lab.to(DEVICE)

        with torch.cuda.amp.autocast(enabled=FP16):
            loss = model(ids, mask, lab) / ACCUM_STEPS

        scaler.scale(loss).backward()

        if (step+1) % ACCUM_STEPS == 0:
            scaler.step(opt)
            scaler.update()
            opt.zero_grad()

        total += loss.item() * ACCUM_STEPS
        pbar.set_postfix({"loss": f"{loss.item()*ACCUM_STEPS:.4f}"})

    print(f"Epoch {epoch+1} Avg Loss = {total/len(train_loader):.4f}")

# -----------------------------
# SAVE (UPGRADED)
# -----------------------------
SAVE_DIR = "mental_model_custom"
os.makedirs(SAVE_DIR, exist_ok=True)

# 1) Save classifier heads separately
heads = {
    "m": model.m.state_dict(),
    "e": model.e.state_dict(),
    "s": model.s.state_dict(),
    "r": model.r.state_dict(),
    "i": model.i.state_dict()
}
torch.save(heads, f"{SAVE_DIR}/custom_heads.pt")

# 2) Save backbone + heads in HF format
full_state = model.state_dict()
torch.save(full_state, f"{SAVE_DIR}/pytorch_model.bin")

# 3) Save config.json
config = MentalHealthConfig()
config.save_pretrained(SAVE_DIR)

# 4) Save tokenizer
tok.save_pretrained(SAVE_DIR)

print("\nDONE! Full HuggingFace model saved in:", SAVE_DIR)
# ======================================================================
# END OF SCRIPT