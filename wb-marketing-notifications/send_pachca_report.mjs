#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const PACHCA_API_BASE = "https://api.pachca.com/api/shared/v1";

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function buildReport() {
  const stdout = execFileSync(process.execPath, [path.join(ROOT, "scripts", "build-products-content-problems-plan-or-fbo-report.mjs")], {
    cwd: ROOT,
    encoding: "utf8",
    maxBuffer: 50 * 1024 * 1024,
    stdio: ["ignore", "pipe", "inherit"],
  });
  return JSON.parse(stdout);
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
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(`Pachca ${endpoint} failed: ${response.status} ${text}`);
  }
  return data?.data || data;
}

async function uploadFile(token, filePath) {
  const upload = await pachcaRequest(token, "/uploads", { method: "POST" });
  const fileName = path.basename(filePath);
  const key = upload.key.replace("${filename}", fileName);
  const form = new FormData();
  for (const [field, value] of Object.entries(upload)) {
    if (field !== "direct_url") form.append(field, String(value));
  }
  form.set("key", key);
  const file = new Blob([fs.readFileSync(filePath)], { type: "text/markdown" });
  form.append("file", file, fileName);

  const s3Response = await fetch(upload.direct_url, { method: "POST", body: form });
  if (!s3Response.ok) {
    throw new Error(`Pachca file upload failed: ${s3Response.status} ${await s3Response.text()}`);
  }

  return {
    key,
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
  return data.id;
}

async function createThread(token, messageId) {
  const data = await pachcaRequest(token, `/messages/${messageId}/thread`, { method: "POST" });
  return data.id;
}

async function main() {
  const token = requiredEnv("PACHCA_TOKEN");
  const chatId = requiredEnv("PACHCA_CHAT_ID");
  const report = buildReport();

  const files = await Promise.all([
    uploadFile(token, report.recommendationsOut),
    uploadFile(token, report.incompleteOut),
    uploadFile(token, report.allContentOut),
  ]);

  const messageId = await sendMessage(token, "discussion", chatId, report.pachcaMessage, files);
  const threadId = await createThread(token, messageId);
  const descriptionMessageId = await sendMessage(token, "thread", threadId, report.pachcaThreadMessage);
  const summaryMessageId = await sendMessage(token, "thread", threadId, report.pachcaMarketerSummaryMessage);

  console.log(JSON.stringify({
    message_id: messageId,
    thread_id: threadId,
    description_message_id: descriptionMessageId,
    summary_message_id: summaryMessageId,
    files: files.map((file) => file.name),
    base_articles: report.baseArticles,
    problem_rows: report.problemRows,
    recommendation_problem_rows: report.recommendationProblemRows,
  }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
