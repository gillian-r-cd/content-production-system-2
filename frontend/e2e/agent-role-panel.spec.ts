// frontend/e2e/agent-role-panel.spec.ts
// 功能: 浏览器级验证 Agent 角色链路，覆盖默认角色引导、覆盖式管理面板与日语文案
// 主要测试: role manager overlay smoke
// 数据结构: Playwright Page / APIResponse / Project

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { resolveBackendBaseUrl } from "../lib/backend-url";

const BACKEND_BASE = resolveBackendBaseUrl({
  NEXT_PUBLIC_BACKEND_URL:
    process.env.PLAYWRIGHT_BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL,
  BACKEND_URL: process.env.BACKEND_URL,
});

async function createProjectAndOpenWorkspace(
  request: APIRequestContext,
  page: Page,
  namePrefix: string,
  locale = "zh-CN",
) {
  const suffix = Date.now().toString();
  const projectName = `${namePrefix}-${suffix}`;

  const projectResp = await request.post(`${BACKEND_BASE}/api/projects/`, {
    data: { name: projectName, locale },
  });
  expect(projectResp.ok()).toBeTruthy();

  await page.goto("/workspace");
  await page.locator("header").getByRole("button").filter({
    hasText: /选择项目|プロジェクトを選択|\(v\d+\)/,
  }).first().click();
  await page.locator("header").locator(".max-h-80").getByText(projectName, { exact: true }).click();

  return { projectName };
}

test("agent role manager opens as overlay and creates a project role", async ({ page, request }) => {
  await createProjectAndOpenWorkspace(request, page, "agent-role-playwright");

  await expect(page.getByRole("button", { name: /助手/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /审稿人/ })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "输入消息... 使用 @ 引用内容块" })).toBeEnabled();

  await page.getByRole("button", { name: "管理角色" }).click();

  await expect(page.getByRole("heading", { name: "Agent 角色", exact: true })).toBeVisible();
  await expect(page.getByText("角色名称和提示词由当前项目维护，简介为可选项")).toBeVisible();
  await expect(page.getByRole("button", { name: "新建角色" })).toBeVisible();

  await page.getByRole("button", { name: "新建角色" }).click();

  await page.getByLabel("角色名称").fill("增长教练");
  await page.getByLabel("角色提示词").fill("你是增长教练，聚焦增长策略、实验设计与行动建议。");
  await page.getByRole("button", { name: "创建角色" }).click();

  await expect(page.getByText("增长教练")).toBeVisible();
});

test("agent role manager shows bootstrapped default roles for a fresh project", async ({ page, request }) => {
  await createProjectAndOpenWorkspace(request, page, "agent-role-import");

  await expect(page.getByRole("button", { name: /助手/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /策略顾问/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /审稿人/ })).toBeVisible();

  await page.getByRole("button", { name: "管理角色" }).click();
  await expect(page.getByRole("heading", { name: "Agent 角色", exact: true })).toBeVisible();
  await expect(page.getByText("当前项目还没有角色")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "导入默认模板" })).toBeVisible();
});

test("agent role manager renders japanese copy for ja-JP projects", async ({ page, request }) => {
  await createProjectAndOpenWorkspace(request, page, "agent-role-ja", "ja-JP");

  await expect(page.getByRole("button", { name: /アシスタント/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /戦略アドバイザー/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /助手/ })).toHaveCount(0);
  await page.getByRole("button", { name: "役割を管理" }).click();

  await expect(page.getByRole("heading", { name: "Agent 役割", exact: true })).toBeVisible();
  await expect(page.getByText("役割名とプロンプトはこのプロジェクトで管理します。説明は任意です。")).toBeVisible();
  await expect(page.getByText("このプロジェクトにはまだ役割がありません")).toHaveCount(0);
});
