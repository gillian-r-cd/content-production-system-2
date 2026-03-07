// frontend/e2e/project-auto-split.spec.ts
// 功能: 浏览器级验证项目自动拆分主链，覆盖模板导入、拆分、校验、应用与全部开始
// 主要测试: auto split modal end-to-end smoke
// 数据结构: Playwright Page / APIResponse / ProjectStructureDraft

import { expect, test } from "@playwright/test";

const BACKEND_BASE = process.env.PLAYWRIGHT_BACKEND_URL || "http://127.0.0.1:8002";

test("auto split modal supports split validate apply and start-all-ready", async ({ page, request }) => {
  const suffix = Date.now().toString();
  const projectName = `auto-split-playwright-${suffix}`;
  const templateName = `auto-split-template-${suffix}`;

  const projectResp = await request.post(`${BACKEND_BASE}/api/projects/`, {
    data: { name: projectName },
  });
  expect(projectResp.ok()).toBeTruthy();
  const project = await projectResp.json();

  const templateResp = await request.post(`${BACKEND_BASE}/api/settings/field-templates`, {
    data: {
      name: templateName,
      description: "playwright smoke template",
      category: "general",
      schema_version: 2,
      fields: [],
      root_nodes: [
        {
          template_node_id: "field-summary",
          name: "Summary",
          block_type: "field",
          ai_prompt: "Write a concise summary for the current chunk based on its dependencies.",
          auto_generate: false,
          children: [],
        },
      ],
    },
  });
  expect(templateResp.ok()).toBeTruthy();

  await page.goto("/workspace");

  await page.locator("header").getByRole("button").filter({
    hasText: /选择项目|\(v\d+\)/,
  }).first().click();
  await page.getByText(projectName, { exact: true }).click();

  await expect(page.getByRole("button", { name: "自动拆分内容" })).toBeVisible();
  await expect(page.getByRole("button", { name: "全部开始" })).toBeVisible();

  await page.getByRole("button", { name: "自动拆分内容" }).click();
  await expect(page.getByText("项目级自动拆分内容")).toBeVisible();

  await page.getByPlaceholder("粘贴要拆分的完整内容").fill(
    "Paragraph one about the customer problem.\n\nParagraph two about the proposed solution.",
  );
  await page.locator("input[type='number']").first().fill("2");

  await page.getByRole("button", { name: "执行拆分" }).click();
  await expect(page.locator("input[value='内容片段 01']")).toBeVisible();
  await expect(page.locator("input[value='内容片段 02']")).toBeVisible();

  await page.getByRole("button", { name: "+ 新编排方案" }).click();
  await page.getByLabel("内容片段 01").check();
  await page.getByLabel("内容片段 02").check();
  await page.locator("select").nth(1).selectOption({ label: templateName });
  await page.getByRole("button", { name: "导入模板结构" }).nth(0).click();
  await expect(page.locator("input[value='Summary']")).toBeVisible();

  await page.getByRole("button", { name: "校验" }).click();
  await expect(page.getByText("应用前结构预览")).toBeVisible();
  await expect(page.getByText(/chunk 数:/)).toBeVisible();
  await expect(page.getByRole("button", { name: "应用到项目" })).toBeEnabled();

  await page.getByRole("button", { name: "应用到项目" }).click();
  await expect(page.getByText("项目级自动拆分内容")).toHaveCount(0);
  await expect(page.getByText("自动拆分内容批次", { exact: true })).toBeVisible();

  const runResponsePromise = page.waitForResponse((response) =>
    response.url().includes(`/api/blocks/project/${project.id}/run`) &&
    response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "全部开始" }).click();
  const runResponse = await runResponsePromise;
  expect(runResponse.ok()).toBeTruthy();
  const runJson = await runResponse.json();
  expect(runJson.started_count).toBeGreaterThan(0);
  expect(runJson.failed_count).toBe(0);
});
