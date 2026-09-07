# -*- coding: utf-8 -*-
"""
Po dokončení (nebo selhání) renderu zavolá zpět Apps Script webapp, aby
poslal makléři e-mail.

ZMĚNA OPROTI PŮVODNÍ VERZI:
  Video se už NEPUBLIKUJE jako GitHub Release (to by časem vyčerpalo
  kapacitu GitHubu). Místo toho se pošle jako base64 přímo v callbacku
  na Apps Script, který ho uloží do stejné pojmenované složky na Disku,
  kde už jsou fotky a config.json. GitHub tak nikdy nedrží žádné video
  trvale.

Použití:
    python notify.py --status success --job job.json --result render_result.json
    python notify.py --status failed  --job job.json
"""

import os
import sys
import json
import argparse
import base64
import requests


def call_callback(callback_url, payload):
    if not callback_url:
        print("VAROVÁNÍ: chybí callback_url, e-mail se neodešle.", file=sys.stderr)
        return
    try:
        # Video v base64 může být poměrně velké, dáváme delší timeout
        resp = requests.post(callback_url, json=payload, timeout=300)
        print(f"Callback odpověď: {resp.status_code} {resp.text[:500]}")
    except Exception as e:
        print(f"CHYBA při volání callbacku: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", choices=["success", "failed"], required=True)
    parser.add_argument("--job", required=True, help="cesta k job.json")
    parser.add_argument("--result", help="cesta k render_result.json (jen pro status=success)")
    args = parser.parse_args()

    if not os.path.exists(args.job):
        print(f"CHYBA: Soubor {args.job} neexistuje.", file=sys.stderr)
        sys.exit(1)

    with open(args.job, "r", encoding="utf-8") as f:
        job = json.load(f)

    config = job.get("config", {})
    callback_url = job.get("callback_url")
    job_id = job.get("job_id", "job_unknown")
    folder_id = job.get("folder_id")

    email = config.get("MAKLER_EMAIL")
    name = config.get("MAKLER_JMENO")

    if args.status == "success":
        result = {}
        if args.result and os.path.exists(args.result):
            with open(args.result, "r", encoding="utf-8") as f:
                result = json.load(f)

        video_path = result.get("video_file") or result.get("video_path") or "output.mp4"

        if not os.path.exists(video_path):
            print(f"CHYBA: Soubor s videem '{video_path}' neexistuje!", file=sys.stderr)
            call_callback(callback_url, {
                "action": "notify_failed",
                "email": email,
                "name": name,
                "job_id": job_id
            })
            sys.exit(1)

        if not folder_id:
            print("VAROVÁNÍ: job.json neobsahuje folder_id - video se nepodaří "
                  "uložit do správné složky na Disku.", file=sys.stderr)

        with open(video_path, "rb") as f:
            video_b64 = base64.b64encode(f.read()).decode("utf-8")

        size_mb = len(video_b64) / (1024 * 1024)
        print(f"Video zakódováno jako base64 ({size_mb:.1f} MB), posílám na Apps Script...")

        call_callback(callback_url, {
            "action": "notify_complete",
            "email": email,
            "name": name,
            "job_id": job_id,
            "folder_id": folder_id,
            "video_base64": video_b64,
            "video_filename": os.path.basename(video_path),
        })
    else:
        call_callback(callback_url, {
            "action": "notify_failed",
            "email": email,
            "name": name,
            "job_id": job_id
        })


if __name__ == "__main__":
    main()
