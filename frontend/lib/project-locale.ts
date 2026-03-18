// frontend/lib/project-locale.ts
// 功能: 前端项目级 locale 工具，统一处理 locale 归一化、客户端 UI locale 持久化与常用界面文案
// 主要函数: normalizeProjectLocale, isJaProjectLocale, resolveClientLocale, persistClientLocale, projectUiText
// 数据结构: PROJECT_UI_TEXTS, CLIENT_UI_LOCALE_STORAGE_KEY

export function normalizeProjectLocale(locale?: string | null): "zh-CN" | "ja-JP" {
  const value = (locale || "").trim().toLowerCase();
  if (value === "ja" || value === "ja-jp" || value === "jp") return "ja-JP";
  return "zh-CN";
}

export function isJaProjectLocale(locale?: string | null): boolean {
  return normalizeProjectLocale(locale) === "ja-JP";
}

export const CLIENT_UI_LOCALE_STORAGE_KEY = "content-production-ui-locale";

export function resolveClientLocale(): "zh-CN" | "ja-JP" {
  if (typeof window !== "undefined") {
    try {
      const storedLocale = window.localStorage.getItem(CLIENT_UI_LOCALE_STORAGE_KEY);
      if (storedLocale) {
        return normalizeProjectLocale(storedLocale);
      }
    } catch {
      // 忽略存储异常，继续回退到其他来源
    }
  }

  if (typeof navigator !== "undefined") {
    return normalizeProjectLocale(navigator.language);
  }

  if (typeof document !== "undefined") {
    const documentLocale = document.documentElement?.lang;
    if (documentLocale) {
      return normalizeProjectLocale(documentLocale);
    }
  }

  return "zh-CN";
}

export function persistClientLocale(locale?: string | null): "zh-CN" | "ja-JP" {
  const normalizedLocale = normalizeProjectLocale(locale);

  if (typeof document !== "undefined") {
    document.documentElement.lang = normalizedLocale;
  }

  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(CLIENT_UI_LOCALE_STORAGE_KEY, normalizedLocale);
    } catch {
      // 忽略存储异常，至少保证当前文档语言同步
    }
  }

  return normalizedLocale;
}

const PROJECT_UI_TEXTS = {
  "zh-CN": {
    systemName: "内容生产系统",
    selectProject: "选择项目",
    loading: "加载中...",
    loadingProjectsFailed: "加载项目失败",
    duplicateProjectFailed: "复制项目失败",
    deleteProjectFailed: "删除项目失败",
    deleteProjectConfirm: "确定删除此项目？此操作将删除项目的所有数据，包括内容块和对话记录。",
    batchDeleteConfirm: "确定删除选中的 {count} 个项目？此操作将删除所有选中项目的数据，包括内容块和对话记录。",
    batchDeleteFailed: "批量删除失败",
    createVersionFailed: "创建版本失败",
    snapshotNote: "版本快照 {time}",
    exportProjectFailed: "导出项目失败",
    importProjectFailed: "导入项目失败",
    invalidImportFile: "无效的项目导出文件：缺少 project 数据",
    unknownError: "未知错误",
    importSummaryTitle: "导入统计",
    importContentBlocks: "内容块",
    importProjectFields: "字段",
    importChatMessages: "对话记录",
    importContentVersions: "版本历史",
    importSimulationRecords: "模拟记录",
    importEvalRuns: "评估运行",
    importGenerationLogs: "生成日志",
    selectAll: "全选",
    selectedCount: "已选 {selected} / {total}",
    deleting: "删除中...",
    batchDelete: "批量删除",
    exitBatchMode: "退出批量模式",
    cancel: "取消",
    projectCount: "{count} 个项目",
    batchManage: "批量管理",
    noProjects: "暂无项目",
    versionsCount: "({count} 个版本)",
    current: "当前",
    versionNotePlaceholder: "版本备注（可选）",
    confirm: "确定",
    createVersion: "创建新版本",
    newProject: "+ 新建项目",
    importProject: "导入项目",
    importProjectTitle: "从JSON文件导入项目",
    importMarkdown: "导入 Markdown",
    importMarkdownTitle: "从 Markdown 导入",
    importMarkdownDescription: "导入内容会追加到当前项目目录末尾，不会覆盖现有结构。",
    markdownImportSelectFiles: "选择 Markdown 文件",
    markdownImportReselectFiles: "重新选择文件：{name}",
    markdownImportModeLabel: "导入模式",
    markdownImportModeHeadingTree: "按标题树导入",
    markdownImportModeHeadingTreeDesc: "每个文件先创建一个分组根节点，再按 heading 映射树结构；无 heading 的文件自动回退为 raw_file。",
    markdownImportModeRawFile: "按原文件导入",
    markdownImportModeRawFileDesc: "每个文件作为一个独立内容块导入，完整保留 Markdown 原文。",
    markdownImportSelectedFiles: "已选择 {count} 个文件",
    markdownImportFileCount: "文件数",
    markdownImportFallbackHint: "无标题文件会自动回退为 raw_file。代码块、表格、列表、引用块与空行会尽量按原文保留。",
    markdownImportFooter: "系统只会本地化导入控制文案，不会翻译或改写 Markdown 正文。",
    markdownImportChooseFirst: "请先选择至少一个 Markdown 文件",
    markdownImportFailed: "Markdown 导入失败",
    markdownImportDoneTitle: "Markdown 导入完成",
    markdownImportDoneMessage: "已追加导入 {blocksCreated} 个内容块，处理了 {fileCount} 个文件",
    markdownImportSubmitting: "导入中...",
    renameProjectTitle: "重命名项目",
    renameProjectPlaceholder: "输入新项目名称",
    renameProjectSave: "保存",
    renameProjectCancel: "取消",
    renameProjectFailed: "重命名失败",
    exportProjectTitle: "导出项目",
    duplicateProjectTitle: "复制项目",
    deleteProjectTitle: "删除项目",
    exportVersionTitle: "导出此版本",
    deleteVersionTitle: "删除此版本",
    search: "搜索",
    searchTitle: "全局搜索替换 (⌘⇧F)",
    settings: "后台设置",
    projectActions: "项目操作菜单",
    noProjectSelected: "未选择项目",
    version: "版本 {version}",
    autoSplit: "自动拆分内容",
    startAllReady: "开始所有已就绪内容块",
    readyHint: "已就绪 = 依赖完成，且所有必答生成前提问已回答。",
    contentStructure: "内容结构",
    noBlocks: "尚未创建内容块",
    noBlocksHint: "与 Agent 对话或手动添加内容块开始项目",
    chooseOrCreateProject: "请选择或创建一个项目",
    chooseProjectHint: "在左侧选择项目开始工作",
    intentAnalysis: "意图分析",
    intentEmptyHint: "意图分析由 AI Agent 通过对话完成。请在右侧对话框中输入“开始”来启动意图分析流程。",
    intentEmptySubHint: "Agent 会问你 3 个问题来了解你的项目意图。",
    research: "消费者调研",
    researchEmptyHint: "消费者调研由 AI Agent 通过 DeepResearch 工具完成。请在右侧对话框中输入“开始调研”来启动。",
    researchEmptySubHint: "Agent 会基于你的意图分析结果，搜索相关信息并生成调研报告。",
    childGroups: "{count} 个子组",
    childBlocks: "{count} 个内容块",
    childOthers: "{count} 个其他",
    noContent: "暂无内容",
    groupTag: "组",
    includes: "包含 {description}",
    emptyGroupHint: "该组暂无内容块，请在左侧添加",
  },
  "ja-JP": {
    systemName: "コンテンツ制作システム",
    selectProject: "プロジェクトを選択",
    loading: "読み込み中...",
    loadingProjectsFailed: "プロジェクトの読み込みに失敗しました",
    duplicateProjectFailed: "プロジェクトの複製に失敗しました",
    deleteProjectFailed: "プロジェクトの削除に失敗しました",
    deleteProjectConfirm: "このプロジェクトを削除しますか？内容ブロックや対話履歴を含むすべてのデータが削除されます。",
    batchDeleteConfirm: "選択中の {count} 件のプロジェクトを削除しますか？内容ブロックや対話履歴を含むすべてのデータが削除されます。",
    batchDeleteFailed: "一括削除に失敗しました",
    createVersionFailed: "新バージョンの作成に失敗しました",
    snapshotNote: "バージョンスナップショット {time}",
    exportProjectFailed: "プロジェクトのエクスポートに失敗しました",
    importProjectFailed: "プロジェクトのインポートに失敗しました",
    invalidImportFile: "無効なプロジェクトエクスポートです: project データがありません",
    unknownError: "不明なエラー",
    importSummaryTitle: "インポート結果",
    importContentBlocks: "内容ブロック",
    importProjectFields: "フィールド",
    importChatMessages: "対話履歴",
    importContentVersions: "バージョン履歴",
    importSimulationRecords: "シミュレーション記録",
    importEvalRuns: "評価実行",
    importGenerationLogs: "生成ログ",
    selectAll: "すべて選択",
    selectedCount: "{selected} / {total} 件選択中",
    deleting: "削除中...",
    batchDelete: "一括削除",
    exitBatchMode: "一括管理を終了",
    cancel: "キャンセル",
    projectCount: "{count} 件のプロジェクト",
    batchManage: "一括管理",
    noProjects: "プロジェクトがありません",
    versionsCount: "({count} バージョン)",
    current: "現在",
    versionNotePlaceholder: "バージョンメモ（任意）",
    confirm: "確定",
    createVersion: "新しいバージョンを作成",
    newProject: "+ 新規プロジェクト",
    importProject: "プロジェクトをインポート",
    importProjectTitle: "JSON ファイルからプロジェクトをインポート",
    importMarkdown: "Markdown をインポート",
    importMarkdownTitle: "Markdown からインポート",
    importMarkdownDescription: "インポート内容は現在のプロジェクトツリー末尾に追加され、既存構造は上書きされません。",
    markdownImportSelectFiles: "Markdown ファイルを選択",
    markdownImportReselectFiles: "ファイルを再選択: {name}",
    markdownImportModeLabel: "インポートモード",
    markdownImportModeHeadingTree: "見出しツリーとして取り込む",
    markdownImportModeHeadingTreeDesc: "各ファイルにグループ root を作成し、heading をツリーへ変換します。heading がないファイルは raw_file に自動フォールバックします。",
    markdownImportModeRawFile: "原稿ファイルとして取り込む",
    markdownImportModeRawFileDesc: "各ファイルを独立した内容ブロックとして取り込み、Markdown 原文をそのまま保持します。",
    markdownImportSelectedFiles: "{count} 個のファイルを選択済み",
    markdownImportFileCount: "ファイル数",
    markdownImportFallbackHint: "見出しがないファイルは raw_file に自動フォールバックします。コードブロック、表、リスト、引用、空行は可能な限り原文を保持します。",
    markdownImportFooter: "システム文言のみ locale-aware に処理され、Markdown 本文は翻訳も改変もされません。",
    markdownImportChooseFirst: "Markdown ファイルを少なくとも 1 つ選択してください",
    markdownImportFailed: "Markdown インポートに失敗しました",
    markdownImportDoneTitle: "Markdown インポート完了",
    markdownImportDoneMessage: "{blocksCreated} 個の内容ブロックを追加し、{fileCount} 個のファイルを処理しました",
    markdownImportSubmitting: "インポート中...",
    renameProjectTitle: "プロジェクトを名前変更",
    renameProjectPlaceholder: "新しいプロジェクト名を入力",
    renameProjectSave: "保存",
    renameProjectCancel: "キャンセル",
    renameProjectFailed: "名前変更に失敗しました",
    exportProjectTitle: "プロジェクトをエクスポート",
    duplicateProjectTitle: "プロジェクトを複製",
    deleteProjectTitle: "プロジェクトを削除",
    exportVersionTitle: "このバージョンをエクスポート",
    deleteVersionTitle: "このバージョンを削除",
    search: "検索",
    searchTitle: "全体検索と置換 (⌘⇧F)",
    settings: "設定",
    projectActions: "プロジェクト操作メニュー",
    noProjectSelected: "プロジェクト未選択",
    version: "バージョン {version}",
    autoSplit: "内容を自動分割",
    startAllReady: "準備完了ブロックをすべて開始",
    readyHint: "準備完了 = 依存関係が完了し、必須の事前質問への回答が揃っている状態です。",
    contentStructure: "コンテンツ構造",
    noBlocks: "コンテンツブロックがまだありません",
    noBlocksHint: "Agent と対話するか、手動でブロックを追加して開始してください",
    chooseOrCreateProject: "プロジェクトを選択するか作成してください",
    chooseProjectHint: "左側でプロジェクトを選んで作業を開始します",
    intentAnalysis: "意図分析",
    intentEmptyHint: "意図分析は AI Agent との対話で進みます。右側の入力欄で「開始」と入力してください。",
    intentEmptySubHint: "Agent が 3 つの質問を通じてプロジェクト意図を整理します。",
    research: "顧客調査",
    researchEmptyHint: "顧客調査は AI Agent が DeepResearch ツールで実行します。右側で「調査開始」と入力してください。",
    researchEmptySubHint: "Agent が意図分析を基に情報収集し、調査レポートを生成します。",
    childGroups: "{count} 個の子グループ",
    childBlocks: "{count} 個の内容ブロック",
    childOthers: "{count} 個のその他",
    noContent: "内容はまだありません",
    groupTag: "グループ",
    includes: "{description} を含む",
    emptyGroupHint: "このグループにはまだ内容ブロックがありません。左側から追加してください。",
  },
} as const;

export function projectUiText(locale?: string | null) {
  return PROJECT_UI_TEXTS[normalizeProjectLocale(locale)];
}

export function formatProjectText(template: string, params: Record<string, string | number>) {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(params[key] ?? ""));
}
