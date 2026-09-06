import json
import os

INPUT = os.path.join("outputs", "parsed_fir.json")
OUTPUT = os.path.join("outputs", "semantic_data.json")

with open(INPUT, "r", encoding="utf-8") as f:
    fir = json.load(f)

# -----------------------------
# AI Semantic Layer
# -----------------------------

semantic = {
    "document_type": "FIR",
    "fir_number": fir["fir_number"],
    "district": fir["district"],
    "police_station": fir["police_station"],
    "registration_date": fir["registration_date"],
    "registration_time": fir["registration_time"],
    "year": fir["year"],
    "ipc_sections": fir["ipc_sections"],
    "type_of_information": fir["type_of_information"],
    "confidence": 100.0
}

# Save
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(semantic, f, indent=4)

print("\n===== FIR SEMANTIC OUTPUT =====\n")

for k, v in semantic.items():
    print(f"{k:22}: {v}")

print("\nSaved :", OUTPUT)