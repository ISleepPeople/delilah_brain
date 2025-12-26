import json
import os
import requests

BRAIN_URL = os.getenv("BRAIN_URL", "http://localhost:8000")
INGEST = f"{BRAIN_URL}/ingest"

def seed_file(path, source="unknown"):
    print(f"[seed-file] Seeding {path} ...")
    total_inserted = 0

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            text = item["text"]
            src = item.get("source", source)

            payload = {
                "texts": [text],
                "user_id": "system_seed",
                "source": src,
            }

            resp = requests.post(INGEST, json=payload, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                total_inserted += data.get("inserted", 0)
                print(f"  OK: {text[:40]}...")
            else:
                print(f"  ERROR: {resp.status_code} {resp.text}")

    print(f"[seed-file] Done. Inserted: {total_inserted}")
    return total_inserted


def main():
    # seed all .jsonl files in /app/knowledge/
    folder = "/app/knowledge"
    for fname in os.listdir(folder):
        if fname.endswith(".jsonl"):
            seed_file(os.path.join(folder, fname), source=fname)


if __name__ == "__main__":
    main()
