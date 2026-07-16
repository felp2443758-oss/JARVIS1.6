"""One-shot CLI: capture a face from the webcam, compute a 128-d embedding
and register the owner in the J.A.R.V.I.S. Cloud Brain."""
from __future__ import annotations
import argparse
import os
import sys

import requests
from dotenv import load_dotenv

from vision import capture_embedding

load_dotenv()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="Owner name (e.g. 'Felipe Stark')")
    parser.add_argument("--user-id", default="owner")
    parser.add_argument("--brain", default=os.getenv("BRAIN_URL", ""))
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args()
    if not args.brain:
        print("ERRO: defina BRAIN_URL em .env ou --brain"); sys.exit(2)
    print("[register] capturando rosto…")
    emb = capture_embedding(args.camera)
    if not emb:
        print("ERRO: nenhum rosto detectado. Iluminação e enquadramento adequados?"); sys.exit(1)
    r = requests.post(f"{args.brain}/api/face/register", json={
        "user_id": args.user_id, "name": args.name, "embedding": emb,
    }, timeout=30)
    r.raise_for_status()
    print(f"[register] OK — {r.json()}")


if __name__ == "__main__":
    main()
