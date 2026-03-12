import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FieldTemplate } from "@/lib/api";
import { ProjectTemplateImportBar } from "./project-template-import-bar";

const templates: FieldTemplate[] = [
  {
    id: "template-1",
    name: "要約テンプレート",
    description: "",
    category: "content",
    schema_version: 1,
    fields: [],
    root_nodes: [],
    created_at: null,
  },
];

describe("ProjectTemplateImportBar", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders japanese copy when project locale is ja-JP", () => {
    const onImport = vi.fn();

    render(
      <ProjectTemplateImportBar
        title="冒頭内容テンプレート"
        projectLocale="ja-JP"
        templates={templates}
        onImport={onImport}
      />,
    );

    expect(screen.getByText("内容ブロックテンプレートを選択")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "テンプレート構造をインポート" })).toBeDisabled();

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "template-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "テンプレート構造をインポート" }));

    expect(onImport).toHaveBeenCalledWith(templates[0]);
  });
});
