import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { createChatSubmission } from "../lib/chat-workflow.mjs";

const root = process.cwd();

function read(path) {
  return readFileSync(join(root, path), "utf8");
}

test("operator console keeps primary workflow surfaces wired", () => {
  const page = read("app/page.tsx");
  const contextPanel = read("components/context-panel.tsx");
  const helpers = read("lib/ui-helpers.ts");

  assert.match(page, /<ContextPanel/);
  assert.match(page, /activeProductView === "workspace"/);
  assert.match(page, /activeProductView === "candidates"/);
  assert.match(page, /activeProductView === "approvals"/);
  assert.match(page, /activeProductView === "connectors"/);
  assert.match(page, /activeProductView === "audit"/);
  assert.match(page, /activeProductView === "settings"/);

  assert.match(page, /handleSubmit/);
  assert.match(page, /sendChat/);
  assert.match(page, /handleApprovalAction/);
  assert.match(page, /transitionApproval/);
  assert.match(page, /getTaskDetail/);

  assert.match(contextPanel, /id="candidate-context"/);
  assert.match(contextPanel, /onChange=\{handleFiles\}/);
  assert.match(contextPanel, /setResumeText/);
  assert.match(contextPanel, /setJdText/);
  assert.match(contextPanel, /refreshOperationalData/);

  assert.match(helpers, /export function statusLabel/);
  assert.match(helpers, /export function evidenceReliability/);
  assert.match(helpers, /export function getInitialProductView/);
});

test("chat submission ignores blank or in-flight input", () => {
  const messages = [{ role: "assistant", content: "你好" }];

  assert.equal(createChatSubmission({ prompt: "   ", messages, isSending: false }), null);
  assert.equal(createChatSubmission({ prompt: "政策问题", messages, isSending: true }), null);
});

test("chat submission trims input and appends the user message", () => {
  const messages = [{ role: "assistant", content: "你好" }];

  const submission = createChatSubmission({ prompt: "  差旅报销标准是什么？  ", messages, isSending: false });

  assert.deepEqual(submission, {
    message: "差旅报销标准是什么？",
    messages: [
      { role: "assistant", content: "你好" },
      { role: "user", content: "差旅报销标准是什么？" },
    ],
  });
});
