// frontend/e2e/japanese-locale-parity.spec.ts
// 功能: 浏览器级验证 ja-JP 入口的设置页与新建项目弹窗链路，确保与 zh-CN 一致可用
// 主要测试: settings/logs 日语可访问、新建项目弹窗默认继承日语 UI locale 并显示日语创作者特质
// 数据结构: Playwright Page / APIRequestContext / Project / CreatorProfile

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { resolveBackendBaseUrl } from "../lib/backend-url";

const BACKEND_BASE = resolveBackendBaseUrl({
  NEXT_PUBLIC_BACKEND_URL:
    process.env.PLAYWRIGHT_BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL,
  BACKEND_URL: process.env.BACKEND_URL,
});

async function createProject(
  request: APIRequestContext,
  namePrefix: string,
  locale: "zh-CN" | "ja-JP",
) {
  const projectName = `${namePrefix}-${Date.now()}`;
  const response = await request.post(`${BACKEND_BASE}/api/projects/`, {
    data: { name: projectName, locale },
  });
  expect(response.ok()).toBeTruthy();
  const project = await response.json();
  return { project, projectName };
}

async function createCreatorProfile(
  request: APIRequestContext,
  namePrefix: string,
  locale: "zh-CN" | "ja-JP",
) {
  const response = await request.post(`${BACKEND_BASE}/api/settings/creator-profiles`, {
    data: {
      name: `${namePrefix}-${Date.now()}-${locale}`,
      locale,
      description: `playwright-${locale}`,
      traits: {},
    },
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function openProjectInWorkspace(page: Page, projectName: string) {
  await page.goto("/workspace");
  await page.locator("header").getByRole("button").filter({
    hasText: /选择项目|プロジェクトを選択|\(v\d+\)/,
  }).first().click();
  await page.locator("header").locator(".max-h-80").getByText(projectName, { exact: true }).click();
}

test("ja-JP project can open settings logs without runtime failure", async ({ page, request }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => {
    pageErrors.push(error.message);
  });

  const { projectName } = await createProject(request, "settings-ja", "ja-JP");
  await openProjectInWorkspace(page, projectName);

  await expect(page.getByRole("button", { name: /\+ 新規プロジェクト/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "設定" })).toBeVisible();

  await page.getByRole("link", { name: "設定" }).click();

  await expect(page.getByRole("heading", { name: "設定", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "デバッグログ" }).click();
  await expect(page.getByRole("heading", { name: "デバッグログ", exact: true })).toBeVisible();
  await expect(page.getByText("各 AI 呼び出しの詳細情報を確認できます")).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("create project modal inherits japanese ui locale and exposes japanese creator profiles", async ({ page, request }) => {
  const zhProfile = await createCreatorProfile(request, "playwright-profile-zh", "zh-CN");
  const jaProfile = await createCreatorProfile(request, "playwright-profile-ja", "ja-JP");
  const { projectName } = await createProject(request, "modal-ja", "ja-JP");

  await openProjectInWorkspace(page, projectName);
  await expect(page.getByRole("button", { name: /\+ 新規プロジェクト/ })).toBeVisible();

  await page.getByRole("button", { name: /\+ 新規プロジェクト/ }).click();

  await expect(page.getByText("新規コンテンツプロジェクト")).toBeVisible();
  const localeSelect = page.getByRole("combobox").nth(0);
  const creatorProfileSelect = page.getByRole("combobox").nth(1);

  await expect(localeSelect).toHaveValue("ja-JP");
  await expect(creatorProfileSelect.locator(`option[value="${jaProfile.id}"]`)).toHaveCount(1);
  await expect(creatorProfileSelect.locator(`option[value="${zhProfile.id}"]`)).toHaveCount(0);

  await page.getByPlaceholder("例: 新製品ローンチのコンテンツ企画").fill(`ja-modal-${Date.now()}`);
  await creatorProfileSelect.selectOption(jaProfile.id);
  await page.getByRole("button", { name: "次へ" }).click();

  await expect(page.getByRole("button", { name: "プロジェクトを作成" })).toBeVisible();
});
