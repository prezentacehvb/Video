# -*- coding: utf-8 -*-
"""
Zveřejní vyrenderované video jako GitHub Release asset a zavolá zpět
Apps Script webapp, aby poslal makléři e-mail (nebo e-mail o chybě).

Použití:
    python notify.py --status success --job job.json --result render_result.json
    python notify.py --status failed  --job job.json

Vyžaduje proměnnou prostředí GITHUB_TOKEN (v Actions automaticky
secrets.GITHUB_TOKEN) a GITHUB_REPOSITORY (Actions ji nastavuje automaticky
jako "owner/repo").
"""

import os
import sys
import json
import argparse
import requests


def create_release_with_asset(job_id, title, video_path):
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }

    create_url = f"https://api.github.com/repos/{repo}/releases"
    resp = requests.post(create_url, headers=headers, json={
        "tag_name": job_id,
        "name": title,
        "body": "Automaticky vygenerované video (HVB Video pipeline).",
        "draft": False,
        "prerelease": False,
    })
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
    resp = requests.post(callback_url, json=payload, timeout=30)
    print(f"Callback odpověď: {resp.status_code} {resp.text}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", choices=["success", "failed"], required=True)
    parser.add_argument("--job", required=True, help="cesta k job.json")
    parser.add_argument("--result", help="cesta k render_result.json (jen pro status=success)")
    args = parser.parse_args()

    with open(args.job, "r", encoding="utf-8") as f:
        job = json.load(f)

    if args.status == "success":
        with open(args.result, "r", encoding="utf-8") as f:
            result = json.load(f)

        video_url = create_release_with_asset(
            job_id=result["job_id"],
            title=f"Video – {result['name']}",
            video_path=result["video_file"],
        )
        print(f"Video zveřejněno: {video_url}")

        call_callback(result.get("callback_url") or job.get("callback_url"), {
            "action": "notify_complete",
            "email": result.get("email"),
            "name": result.get("name"),
            "video_url": video_url,
        })
    else:
        config = job.get("config", {})
        call_callback(job.get("callback_url"), {
            "action": "notify_failed",
            "email": config.get("MAKLER_EMAIL"),
            "name": config.get("MAKLER_JMENO"),
        })


if __name__ == "__main__":
    main()
