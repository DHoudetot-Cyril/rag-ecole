"""Enregistre les échanges de la démo en interrogeant la vraie API (stack lancée + exemples ingérés).

    set -a && . ./.env && set +a
    python docs/demo/record.py            # -> docs/demo/turns.json (sans les clés d'API)

RAG_API_URL change l'adresse de l'API (défaut : http://localhost:8080). LLM_LABEL donne le nom
lisible du modèle affiché dans le GIF (sinon : le nom renvoyé par /health).
"""

import json
import os
import time
import urllib.request
from pathlib import Path

API = os.environ.get("RAG_API_URL", "http://localhost:8080")
KEYS = {"élève": os.environ["STUDENT_API_KEY"], "direction": os.environ["DIRECTION_API_KEY"]}
TURNS = [
    ("élève", "Le téléphone est-il autorisé en classe ?"),
    ("élève", "Quel est le budget de rénovation des salles de sciences ?"),  # document de niveau 2
    ("direction", "Quel est le budget de rénovation des salles de sciences ?"),
    ("élève", "Qui a gagné la Coupe du monde de football 2018 ?"),  # hors sujet
]


def ask(role: str, question: str) -> dict:
    req = urllib.request.Request(
        f"{API}/chat",
        data=json.dumps({"question": question}).encode(),
        headers={"X-API-Key": KEYS[role], "Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.load(resp)
    return {
        "role": role,
        "question": question,
        "answer": data["answer"],
        "levels_searched": data["levels_searched"],
        "latency_ms": data["latency_ms"],
        "wall_s": round(time.perf_counter() - t0, 2),
        "sources": [
            {"document": s["document"], "level": s["level"], "score": s["score"]} for s in data.get("sources", [])
        ],
    }


def main() -> None:
    health = json.load(urllib.request.urlopen(f"{API}/health", timeout=10))
    turns = [ask(role, q) for role, q in TURNS]
    out = Path(__file__).with_name("turns.json")
    record = {
        "llm_model": health.get("llm_model"),
        "llm_label": os.environ.get("LLM_LABEL"),
        "embedding_model": health.get("embedding_model"),
        "turns": turns,
    }
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(turns)} échanges écrits dans {out}")


if __name__ == "__main__":
    main()
