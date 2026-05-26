#!/usr/bin/env node
import fs from "node:fs";

import { buildReports } from "./scripts/build-xway-limit-reports.mjs";

const PACHCA_API_BASE = "https://api.pachca.com/api/shared/v1";

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

async function pachcaRequest(token, endpoint, options = {}) {
  const response = await fetch(`${PACHCA_API_BASE}${endpoint}`, {
    ...options,
    headers: {
      authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { body: text };
    }
  }
  if (!response.ok) {
    throw new Error(`Pachca API ${endpoint} failed: ${response.status} ${text}`);
  }
  return payload;
}

async function uploadFile(token, filePath) {
  const upload = await pachcaRequest(token, "/uploads", { method: "POST" });
  const data = upload.data || upload;
  const uploadUrl = data.direct_url || data.url;
  const fileName = filePath.split("/").at(-1);
  const fileKey = String(data.key || data.file_key || data.id || "").replace("${filename}", fileName);
  if (!uploadUrl || !fileKey) {
    throw new Error(`Unexpected Pachca upload payload for ${filePath}`);
  }

  const form = new FormData();
  for (const [field, value] of Object.entries(data)) {
    if (field !== "direct_url" && field !== "url") form.append(field, String(value));
  }
  form.set("key", fileKey);
  const file = new Blob([fs.readFileSync(filePath)], { type: "text/markdown" });
  form.append("file", file, fileName);

  const uploadResponse = await fetch(uploadUrl, { method: "POST", body: form });
  if (!uploadResponse.ok) {
    throw new Error(`Pachca direct upload failed for ${filePath}: ${uploadResponse.status} ${await uploadResponse.text()}`);
  }

  return {
    key: fileKey,
    name: fileName,
    file_type: "file",
    size: fs.statSync(filePath).size,
  };
}

async function sendMessage(token, entityType, entityId, content, files = []) {
  const payload = {
    message: {
      entity_type: entityType,
      entity_id: Number(entityId),
      content,
    },
    link_preview: false,
  };
  if (files.length) payload.message.files = files;
  const data = await pachcaRequest(token, "/messages", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  return data.data?.id || data.id;
}

async function main() {
  const token = requiredEnv("PACHCA_TOKEN");
  const chatId = requiredEnv("PACHCA_CHAT_ID");
  const report = await buildReports();
  const files = await Promise.all([
    uploadFile(token, report.files.limits),
    uploadFile(token, report.files.activity),
    uploadFile(token, report.files.autoExclusions),
    uploadFile(token, report.files.instruction),
  ]);
  const messageId = await sendMessage(token, "discussion", chatId, report.pachcaMessage, files);
  console.log(JSON.stringify({ ok: true, messageId, chatId, manifest: report.manifestPath, stats: report.stats }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
