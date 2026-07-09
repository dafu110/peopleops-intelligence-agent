import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

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
