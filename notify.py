# -*- coding: utf-8 -*-
"""
Zveřejní vyrenderované video jako GitHub Release asset a zavolá zpět
Apps Script webapp, aby poslal makléři e-mail (nebo e-mail o chybě).

Použití:
    python notify.py --status success --job job.json --result render_result.json
    python notify.py --status failed  --job job.json
"""

import os
import sys
import json
import argparse
import re
import time
import requests


def sanitize_tag(raw_input):
    """Převede název na platný a čistý formát pro GitHub Release Tag."""
    clean = re.sub(r"[^a-zA-Z0-9_\-.]", "_", str(raw_input))
    return clean.strip("_")


def create_release_with_asset(job_id, title, video_path):
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }

    # Vyčištění tagu od mezer a diakritiky + přidání časového razítka proti duplicitám (422)
    clean_job_id = sanitize_tag(job_id)
    unique_tag = f"rel_{clean_job_id}_{int(time.time())}"

    create_url = f"https://api.github.com/repos/{repo}/releases"
    payload = {
        "tag_name": unique_tag,
        "target_commitish": "main",
        "name": title,
        "body": "Automaticky vygenerované video (HVB Video pipeline).",
        "draft": False,
        "prerelease": False,
    }

    resp = requests.post(create_url, headers=headers, json=payload)
    
    # Zpětná záloha pro případ, že by tag přesto kolidoval
    if resp.status_code == 422:
        payload["tag_name"] = f"rel_{int(time.time())}"
        resp = requests.post(create_url, headers=headers, json=payload)

    resp.raise_for_status()
    release = resp.json()
    upload_url_template = release["upload_url"].split("{")[0]

    filename = os.path.basename(video_path)
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    upload_resp = requests.post(
        f"{upload_url_template}?name={filename}",
        headers={**headers, "Content-Type": "video/mp4"},
        data=video_bytes,
    )
    upload_resp.raise_for_status()
    asset = upload_resp.json()
    return asset["browser_download_url"]


def call_callback(callback_url, payload):
    if not callback_url:
        print("VAROVÁNÍ: chybí callback_url, e-mail se neodešle.", file=sys.stderr)
        return
    try:
        resp = requests.post(callback_url, json=payload, timeout=30)
        print(f"Callback odpověď: {resp.status_code} {resp.text}")
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

    email = config.get("MAKLER_EMAIL")
    name = config.get("MAKLER_JMENO")

    if args.status == "success":
        result = {}
        if args.result and os.path.exists(args.result):
            with open(args.result, "r", encoding="utf-8") as f:
                result = json.load(f)

        # Načtení cesty k videu (s fallbackem na standardní výstup)
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

        video_url = create_release_with_asset(
            job_id=job_id,
            title=f"Video – {name or job_id}",
            video_path=video_path,
        )
        print(f"Video zveřejněno: {video_url}")

        call_callback(callback_url, {
            "action": "notify_complete",
            "email": email,
            "name": name,
            "job_id": job_id,
            "video_url": video_url,
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
