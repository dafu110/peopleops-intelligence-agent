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
  assert.match(page, /mobile-more-trigger/);
  assert.match(page, /mobileMoreOpen/);
  assert.match(page, /primaryNavigation/);
  assert.match(page, /managementNavigation/);
  assert.match(page, /inspectorHasDetail/);
  assert.match(page, /runtime-details/);
  assert.match(page, /选择一项任务/);
  assert.match(page, /候选人匹配/);
  assert.match(page, /submitMessage/);
  assert.match(page, /咨询制度与流程/);
  assert.match(page, /data-tooltip/);
  assert.match(page, /contextDrawerRef/);
  assert.match(page, /aria-modal="true"/);
  assert.match(page, /event.key === "Escape"/);
  assert.match(page, /isDevelopment/);
  assert.match(page, /生成候选人跟进草稿（需审批）/);
  assert.match(page, /未连接外部 HR 系统/);

  assert.match(contextPanel, /id="candidate-context"/);
  assert.match(contextPanel, /onChange=\{handleFiles\}/);
  assert.match(contextPanel, /setResumeText/);
  assert.match(contextPanel, /setJdText/);
  assert.match(contextPanel, /refreshOperationalData/);
  assert.match(contextPanel, /完成两项材料后即可开始匹配/);
  assert.match(contextPanel, /data-context-close/);
  assert.doesNotMatch(contextPanel, /API:/);

  assert.match(helpers, /export function statusLabel/);
  assert.match(helpers, /export function statusClass/);
  assert.match(helpers, /export function getInitialProductView/);
});

test("narrow screens keep the operator workspace full width", () => {
  const styles = read("app/globals.css");
  const finalMobileStyles = styles.slice(styles.lastIndexOf("@media (max-width: 600px)"));

  assert.match(finalMobileStyles, /\.codex-shell\s*\{\s*grid-template-columns:\s*1fr;/);
  assert.match(finalMobileStyles, /\.chat-workspace, \.compact-view\s*\{\s*width:\s*100%;/);
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
