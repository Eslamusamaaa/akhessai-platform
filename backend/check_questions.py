import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from questions.resolver import QUESTION_BANK

print(f"Total questions in bank: {len(QUESTION_BANK)}")

# Check all age bands
all_bands = set()
for q in QUESTION_BANK:
    all_bands.update(q.get("age_bands", []))
print(f"Age bands in bank: {all_bands}")

# Check for 6-18 / parent / adhd+sensory_processing
age_band = "6-18"
informant = "parent"
active_specialties = {"adhd", "sensory_processing"}

matching = []
for q in QUESTION_BANK:
    if age_band not in q.get("age_bands", []):
        continue
    q_inf = q.get("informant", "any")
    if q_inf != "any" and q_inf != informant:
        continue
    is_core = q["id"].startswith("q_core") or q["id"] == "q_verbal_status"
    q_specs = set(q.get("specialty_tags", []))
    if not is_core and not q_specs.intersection(active_specialties):
        continue
    matching.append(q)

print(f"\nMatching for 6-18 / parent / adhd+sensory_processing: {len(matching)}")
for q in matching[:10]:
    print(f"  {q['id']} | {q.get('informant','any')} | {q.get('specialty_tags',[])} | {q['label_ar'][:60]}")

# Also check core questions
core_q = [q for q in QUESTION_BANK if q["id"].startswith("q_core") or q["id"] == "q_verbal_status"]
print(f"\nCore questions total: {len(core_q)}")
for q in core_q[:5]:
    print(f"  {q['id']} | age_bands={q.get('age_bands')} | {q.get('informant','any')}")
