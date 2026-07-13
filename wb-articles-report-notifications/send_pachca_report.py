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
PACHCA_MESSAGE_LIMIT = 18_000


def required_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def build_report():
    try:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "build_wb_articles_marketer_report.py")],
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
            "link_preview": False,
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
    if not response.ok:
        raise RuntimeError(
            f"Pachca message failed: HTTP {response.status_code}; {response.text[:1000]}"
        )
    data = response.json()
    message_id = data.get("data", {}).get("id") or data.get("id")
    if not message_id:
        raise RuntimeError("Pachca did not return a message id")
    return message_id


def create_thread(token, message_id):
    response = requests.post(
        f"{PACHCA_API_BASE}/messages/{int(message_id)}/thread",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", payload)
    thread_id = data.get("id")
    thread_chat_id = data.get("chat_id")
    if not thread_id or not thread_chat_id:
        raise RuntimeError("Pachca did not return thread identifiers")
    return {"id": thread_id, "chat_id": thread_chat_id}


def split_markdown_messages(content, limit=PACHCA_MESSAGE_LIMIT):
    content = str(content or "").strip()
    if not content:
        return []
    if len(content) <= limit:
        return [content]

    chunks = []
    current = ""
    for block in content.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(block) <= limit:
            current = block
            continue
        for line in block.splitlines():
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = line
    if current:
        chunks.append(current)
    return chunks


def main():
    token = required_env("PACHCA_TOKEN")
    chat_id = required_env("PACHCA_CHAT_ID")
    report = build_report()

    md_path = Path(report["md"])
    message_path = Path(report["message"])
    niche_message_path = Path(report["niche_message"])
    niche_thread_message_path = Path(report["niche_thread_message"])

    file_payload = upload_file(token, md_path)
    niche_file_payload = upload_file(token, niche_thread_message_path)
    content = message_path.read_text(encoding="utf-8").strip()
    message_id = send_message(token, "discussion", chat_id, content, [file_payload])
    niche_content = niche_message_path.read_text(encoding="utf-8").strip()
    niche_message_id = send_message(token, "discussion", chat_id, niche_content, [niche_file_payload])
    thread = create_thread(token, niche_message_id)
    thread_content = niche_thread_message_path.read_text(encoding="utf-8").strip()
    thread_message_ids = [
        send_message(token, "thread", thread["id"], chunk)
        for chunk in split_markdown_messages(thread_content)
    ]
    thread_message_id = thread_message_ids[0] if thread_message_ids else None

    print(
        json.dumps(
            {
                "message_id": message_id,
                "niche_message_id": niche_message_id,
                "thread_id": thread["id"],
                "thread_chat_id": thread["chat_id"],
                "thread_message_id": thread_message_id,
                "thread_message_ids": thread_message_ids,
                "md": str(md_path),
                "message": str(message_path),
                "niche_message": str(niche_message_path),
                "niche_thread_message": str(niche_thread_message_path),
                "rows": report.get("rows"),
                "skus": report.get("skus"),
                "cabinets": report.get("cabinets"),
                "niches": report.get("niches"),
                "current_month_drr": report.get("current_month_drr"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
