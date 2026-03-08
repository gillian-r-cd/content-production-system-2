// frontend/e2e/agent-role-panel.spec.ts
// 功能: 浏览器级验证 Agent 角色面板的空状态、覆盖式管理面板与最小创建链路
// 主要测试: role manager overlay smoke
// 数据结构: Playwright Page / APIResponse / Project

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const BACKEND_BASE = process.env.PLAYWRIGHT_BACKEND_URL || "http://127.0.0.1:8002";

async function createProjectAndOpenWorkspace(
  request: APIRequestContext,
  page: Page,
  namePrefix: string,
) {
  const suffix = Date.now().toString();
  const projectName = `${namePrefix}-${suffix}`;

  const projectResp = await request.post(`${BACKEND_BASE}/api/projects/`, {
    data: { name: projectName },
  });
  expect(projectResp.ok()).toBeTruthy();

  await page.goto("/workspace");
  await page.locator("header").getByRole("button").filter({
    hasText: /选择项目|\(v\d+\)/,
  }).first().click();
  await page.getByText(projectName, { exact: true }).click();

  return { projectName };
}

test("agent role manager opens as overlay and creates a project role", async ({ page, request }) => {
  await createProjectAndOpenWorkspace(request, page, "agent-role-playwright");

  await expect(page.getByText("当前项目还没有 Agent 角色")).toBeVisible();
  await expect(page.getByText("暂无角色")).toBeVisible();

  await page.getByRole("button", { name: "配置角色" }).click();

  await expect(page.getByRole("heading", { name: "Agent 角色", exact: true })).toBeVisible();
  await expect(page.getByText("角色名称和提示词由当前项目维护，简介为可选项")).toBeVisible();
  await expect(page.getByText("当前项目还没有角色")).toBeVisible();

  await page.getByLabel("角色名称").fill("增长教练");
  await page.getByLabel("角色提示词").fill("你是增长教练，聚焦增长策略、实验设计与行动建议。");
  await page.getByRole("button", { name: "创建角色" }).click();

  await expect(page.getByRole("heading", { name: "Agent 角色" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /增长教练/ })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "输入消息... 使用 @ 引用内容块" })).toBeEnabled();
});

test("agent role manager imports default templates for an empty project", async ({ page, request }) => {
  await createProjectAndOpenWorkspace(request, page, "agent-role-import");

  await expect(page.getByText("当前项目还没有 Agent 角色")).toBeVisible();
  await page.getByRole("button", { name: "配置角色" }).click();

  const importButton = page.getByRole("button", { name: "导入默认模板" });
  await expect(importButton).toBeEnabled();
  await importButton.click();

  await expect(page.getByText("助手")).toBeVisible();
  await expect(page.getByText("审稿人")).toBeVisible();
});
