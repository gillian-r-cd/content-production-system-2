import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EvalPhasePanel } from "./eval-phase-panel";

const apiMocks = vi.hoisted(() => ({
  getProjectBlocks: vi.fn(),
  createBlock: vi.fn(),
  listTasks: vi.fn(),
  executionReport: vi.fn(),
  listGraders: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    blockAPI: {
      ...actual.blockAPI,
      getProjectBlocks: apiMocks.getProjectBlocks,
      create: apiMocks.createBlock,
    },
    evalV2API: {
      ...actual.evalV2API,
      listTasks: apiMocks.listTasks,
      executionReport: apiMocks.executionReport,
    },
    graderAPI: {
      ...actual.graderAPI,
      listForProject: apiMocks.listGraders,
    },
  };
});

function makeEvalBlock(id: string, name: string, specialHandler: "eval_persona_setup" | "eval_task_config" | "eval_report") {
  return {
    id,
    project_id: "project-1",
    parent_id: null,
    name,
    block_type: "field" as const,
    depth: 0,
    order_index: 0,
    content: specialHandler === "eval_persona_setup" ? JSON.stringify({ personas: [] }) : "",
    status: "pending",
    ai_prompt: "",
    constraints: {},
    pre_questions: [],
    pre_answers: {},
    depends_on: [],
    special_handler: specialHandler,
    need_review: false,
    auto_generate: false,
    is_collapsed: false,
    model_override: null,
    children: [],
    created_at: "",
    updated_at: "",
  };
}

describe("EvalPhasePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getProjectBlocks.mockResolvedValue({
      blocks: [
        makeEvalBlock("persona-1", "ペルソナ設定", "eval_persona_setup"),
        makeEvalBlock("config-1", "評価タスク設定", "eval_task_config"),
        makeEvalBlock("report-1", "評価レポート", "eval_report"),
      ],
    });
    apiMocks.createBlock.mockResolvedValue(null);
    apiMocks.listTasks.mockResolvedValue({ tasks: [] });
    apiMocks.executionReport.mockResolvedValue({ executions: [] });
    apiMocks.listGraders.mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
  });

  it("renders japanese tabs and localized empty states for ja-JP projects", async () => {
    render(<EvalPhasePanel projectId="project-1" projectLocale="ja-JP" />);

    expect(await screen.findByText("評価")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ペルソナ" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "評価設定" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "評価レポート" })).toBeInTheDocument();
    expect(screen.getByText("ペルソナ設定")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "評価設定" }));
    expect(await screen.findByText("タスク設定")).toBeInTheDocument();
    expect(screen.getByText("評価タスクはまだありません。「タスクを追加」をクリックして最初のタスクを作成してください。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "評価レポート" }));
    await waitFor(() => {
      expect(screen.getByText("実行記録はまだありません。先にタスク設定でタスクを実行してください。")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument();
  });
});
