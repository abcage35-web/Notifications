#!/usr/bin/env python3
import json
import mimetypes
import os
import subprocess
import sys
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent
PACHCA_API_BASE = "https://api.pachca.com/api/shared/v1"


def required_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def build_report():
    try:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "build_sheet_supplies_md.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            print(exc.stdout, file=sys.stdout)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        raise
    return json.loads(completed.stdout)


def upload_file(token, file_path):
    headers = {"Authorization": f"Bearer {token}"}
    upload_response = requests.post(f"{PACHCA_API_BASE}/uploads", headers=headers, timeout=30)
    upload_response.raise_for_status()
    upload = upload_response.json()

    file_name = file_path.name
    file_key = upload["key"].replace("${filename}", file_name)
    fields = {key: value for key, value in upload.items() if key != "direct_url"}
    fields["key"] = file_key
    content_type = mimetypes.guess_type(file_name)[0] or "text/markdown"

    multipart = [(key, (None, str(value))) for key, value in fields.items()]
    with file_path.open("rb") as file_handle:
        multipart.append(("file", (file_name, file_handle, content_type)))
        s3_response = requests.post(upload["direct_url"], files=multipart, timeout=60)
    s3_response.raise_for_status()

    return {
        "key": file_key,
        "name": file_name,
        "file_type": "file",
        "size": file_path.stat().st_size,
    }


def send_message(token, entity_type, entity_id, content, files=None):
    payload = {
        "message": {
            "entity_type": entity_type,
            "entity_id": int(entity_id),
            "content": content,
        }
    }
    if files:
        payload["message"]["files"] = files
    response = requests.post(
        f"{PACHCA_API_BASE}/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("data", {}).get("id") or data.get("id")


def create_thread(token, message_id):
    response = requests.post(
        f"{PACHCA_API_BASE}/messages/{message_id}/thread",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("data", {}).get("id") or data.get("id")


def main():
    token = required_env("PACHCA_TOKEN")
    chat_id = required_env("PACHCA_CHAT_ID")
    report = build_report()

    md_path = Path(report["md"])
    message_path = Path(report["message"])
    thread_message_path = Path(report["thread_message"])

    file_payload = upload_file(token, md_path)
    content = message_path.read_text(encoding="utf-8").strip()
    message_id = send_message(token, "discussion", chat_id, content, [file_payload])

    thread_content = thread_message_path.read_text(encoding="utf-8").strip()
    thread_id = None
    if thread_content:
        thread_id = create_thread(token, message_id)
        send_message(token, "thread", thread_id, thread_content)

    print(
        json.dumps(
            {
                "message_id": message_id,
                "thread_id": thread_id,
                "md": str(md_path),
                "items": report.get("items"),
                "unresolved": report.get("unresolved"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
