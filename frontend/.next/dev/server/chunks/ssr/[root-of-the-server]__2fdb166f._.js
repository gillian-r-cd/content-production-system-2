module.exports = [
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[project]/components/layout/workspace-layout.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "WorkspaceLayout",
    ()=>WorkspaceLayout
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
// frontend/components/layout/workspace-layout.tsx
// 功能: 工作台三栏布局
// 主要组件: WorkspaceLayout
"use client";
;
function WorkspaceLayout({ leftPanel, centerPanel, rightPanel }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "flex h-screen bg-surface-0",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("aside", {
                className: "w-64 flex-shrink-0 border-r border-surface-3 bg-surface-1 overflow-y-auto",
                children: leftPanel
            }, void 0, false, {
                fileName: "[project]/components/layout/workspace-layout.tsx",
                lineNumber: 23,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("main", {
                className: "flex-1 overflow-y-auto bg-surface-0",
                children: centerPanel
            }, void 0, false, {
                fileName: "[project]/components/layout/workspace-layout.tsx",
                lineNumber: 28,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("aside", {
                className: "w-96 flex-shrink-0 border-l border-surface-3 bg-surface-1 flex flex-col",
                children: rightPanel
            }, void 0, false, {
                fileName: "[project]/components/layout/workspace-layout.tsx",
                lineNumber: 33,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/components/layout/workspace-layout.tsx",
        lineNumber: 21,
        columnNumber: 5
    }, this);
}
}),
"[project]/lib/utils.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "PHASE_NAMES",
    ()=>PHASE_NAMES,
    "PHASE_STATUS",
    ()=>PHASE_STATUS,
    "cn",
    ()=>cn,
    "formatDate",
    ()=>formatDate
]);
// frontend/lib/utils.ts
// 功能: 通用工具函数
// 主要函数: cn, formatDate
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$clsx$2f$dist$2f$clsx$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/clsx/dist/clsx.mjs [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$tailwind$2d$merge$2f$dist$2f$bundle$2d$mjs$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/tailwind-merge/dist/bundle-mjs.mjs [app-ssr] (ecmascript)");
;
;
function cn(...inputs) {
    return (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$tailwind$2d$merge$2f$dist$2f$bundle$2d$mjs$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["twMerge"])((0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$clsx$2f$dist$2f$clsx$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["clsx"])(inputs));
}
function formatDate(dateString) {
    if (!dateString) return "";
    const date = new Date(dateString);
    return date.toLocaleString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit"
    });
}
const PHASE_NAMES = {
    intent: "意图分析",
    research: "消费者调研",
    design_inner: "内涵设计",
    produce_inner: "内涵生产",
    design_outer: "外延设计",
    produce_outer: "外延生产",
    simulate: "消费者模拟",
    evaluate: "评估"
};
const PHASE_STATUS = {
    pending: {
        label: "未开始",
        color: "text-zinc-500"
    },
    in_progress: {
        label: "进行中",
        color: "text-yellow-500"
    },
    completed: {
        label: "已完成",
        color: "text-green-500"
    }
};
}),
"[project]/components/progress-panel.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "ProgressPanel",
    ()=>ProgressPanel
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/utils.ts [app-ssr] (ecmascript)");
// frontend/components/progress-panel.tsx
// 功能: 左栏项目进度面板，支持中间4阶段拖拽排序
// 主要组件: ProgressPanel
// 固定阶段: 意图分析、消费者调研在顶部；消费者模拟、评估在底部
// 可拖拽阶段: 内涵设计、内涵生产、外延设计、外延生产
"use client";
;
;
;
// 固定阶段定义
const FIXED_TOP_PHASES = [
    "intent",
    "research"
];
const DRAGGABLE_PHASES = [
    "design_inner",
    "produce_inner",
    "design_outer",
    "produce_outer"
];
const FIXED_BOTTOM_PHASES = [
    "simulate",
    "evaluate"
];
function ProgressPanel({ project, onPhaseClick, onPhaseReorder, onAutonomyChange }) {
    const [showAutonomySettings, setShowAutonomySettings] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const allPhases = project?.phase_order || [];
    const phaseStatus = project?.phase_status || {};
    const currentPhase = project?.current_phase || "intent";
    // 分离固定和可拖拽阶段
    const topPhases = allPhases.filter((p)=>FIXED_TOP_PHASES.includes(p));
    const middlePhases = allPhases.filter((p)=>DRAGGABLE_PHASES.includes(p));
    const bottomPhases = allPhases.filter((p)=>FIXED_BOTTOM_PHASES.includes(p));
    // 拖拽状态
    const [draggedPhase, setDraggedPhase] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [dragOverPhase, setDragOverPhase] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const dragCounter = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(0);
    const handleDragStart = (e, phase)=>{
        setDraggedPhase(phase);
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", phase);
    };
    const handleDragEnd = ()=>{
        setDraggedPhase(null);
        setDragOverPhase(null);
        dragCounter.current = 0;
    };
    const handleDragEnter = (e, phase)=>{
        e.preventDefault();
        dragCounter.current++;
        if (DRAGGABLE_PHASES.includes(phase)) {
            setDragOverPhase(phase);
        }
    };
    const handleDragLeave = ()=>{
        dragCounter.current--;
        if (dragCounter.current === 0) {
            setDragOverPhase(null);
        }
    };
    const handleDragOver = (e)=>{
        e.preventDefault();
    };
    const handleDrop = (e, targetPhase)=>{
        e.preventDefault();
        if (!draggedPhase || draggedPhase === targetPhase) {
            handleDragEnd();
            return;
        }
        // 重新排序中间阶段
        const newMiddle = [
            ...middlePhases
        ];
        const dragIdx = newMiddle.indexOf(draggedPhase);
        const dropIdx = newMiddle.indexOf(targetPhase);
        if (dragIdx !== -1 && dropIdx !== -1) {
            newMiddle.splice(dragIdx, 1);
            newMiddle.splice(dropIdx, 0, draggedPhase);
            // 重建完整顺序
            const newOrder = [
                ...topPhases,
                ...newMiddle,
                ...bottomPhases
            ];
            onPhaseReorder?.(newOrder);
        }
        handleDragEnd();
    };
    const renderPhaseItem = (phase, isDraggable)=>{
        const status = phaseStatus[phase] || "pending";
        const statusInfo = __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["PHASE_STATUS"][status] || __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["PHASE_STATUS"].pending;
        const isCurrent = phase === currentPhase;
        const isDragging = draggedPhase === phase;
        const isDragOver = dragOverPhase === phase;
        return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
            draggable: isDraggable,
            onDragStart: isDraggable ? (e)=>handleDragStart(e, phase) : undefined,
            onDragEnd: isDraggable ? handleDragEnd : undefined,
            onDragEnter: isDraggable ? (e)=>handleDragEnter(e, phase) : undefined,
            onDragLeave: isDraggable ? handleDragLeave : undefined,
            onDragOver: isDraggable ? handleDragOver : undefined,
            onDrop: isDraggable ? (e)=>handleDrop(e, phase) : undefined,
            className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("relative transition-all duration-150", isDragging && "opacity-50", isDragOver && "before:absolute before:inset-x-0 before:-top-1 before:h-0.5 before:bg-brand-500"),
            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                onClick: ()=>onPhaseClick?.(phase),
                className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors", isCurrent ? "bg-brand-600/20 text-brand-400" : "hover:bg-surface-3 text-zinc-300", isDraggable && "cursor-grab active:cursor-grabbing"),
                children: [
                    isDraggable && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: "text-zinc-600 text-xs select-none",
                        children: "⋮⋮"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 137,
                        columnNumber: 13
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("w-2 h-2 rounded-full flex-shrink-0", status === "completed" && "bg-green-500", status === "in_progress" && "bg-yellow-500", status === "pending" && "bg-zinc-600")
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 141,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: "flex-1 text-sm",
                        children: __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["PHASE_NAMES"][phase] || phase
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 151,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("text-xs", statusInfo.color),
                        children: statusInfo.label
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 156,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/progress-panel.tsx",
                lineNumber: 125,
                columnNumber: 9
            }, this)
        }, phase, false, {
            fileName: "[project]/components/progress-panel.tsx",
            lineNumber: 110,
            columnNumber: 7
        }, this);
    };
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "p-4",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "mb-6",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                        className: "text-lg font-semibold text-zinc-100",
                        children: project?.name || "未选择项目"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 168,
                        columnNumber: 9
                    }, this),
                    project && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-sm text-zinc-500 mt-1",
                        children: [
                            "版本 ",
                            project.version
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 172,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/progress-panel.tsx",
                lineNumber: 167,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "space-y-1",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                        className: "text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3",
                        children: "流程进度"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 180,
                        columnNumber: 9
                    }, this),
                    topPhases.map((phase)=>renderPhaseItem(phase, false)),
                    middlePhases.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "py-1",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "text-xs text-zinc-600 px-3 mb-1 flex items-center gap-1",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "↕"
                                    }, void 0, false, {
                                        fileName: "[project]/components/progress-panel.tsx",
                                        lineNumber: 191,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "可拖拽调整顺序"
                                    }, void 0, false, {
                                        fileName: "[project]/components/progress-panel.tsx",
                                        lineNumber: 192,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/components/progress-panel.tsx",
                                lineNumber: 190,
                                columnNumber: 13
                            }, this),
                            middlePhases.map((phase)=>renderPhaseItem(phase, true))
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 189,
                        columnNumber: 11
                    }, this),
                    bottomPhases.map((phase)=>renderPhaseItem(phase, false))
                ]
            }, void 0, true, {
                fileName: "[project]/components/progress-panel.tsx",
                lineNumber: 179,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "my-6 border-t border-surface-3"
            }, void 0, false, {
                fileName: "[project]/components/progress-panel.tsx",
                lineNumber: 203,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "space-y-2",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                        className: "text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3",
                        children: "快捷操作"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 207,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        onClick: ()=>setShowAutonomySettings(true),
                        className: "w-full px-3 py-2 text-sm text-left text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded-lg transition-colors",
                        children: "⚙ Agent自主权设置"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 211,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        className: "w-full px-3 py-2 text-sm text-left text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded-lg transition-colors",
                        children: "+ 新建版本"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 218,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        className: "w-full px-3 py-2 text-sm text-left text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded-lg transition-colors",
                        children: "查看历史版本"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 222,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        className: "w-full px-3 py-2 text-sm text-left text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded-lg transition-colors",
                        children: "导出内容"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 226,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/progress-panel.tsx",
                lineNumber: 206,
                columnNumber: 7
            }, this),
            showAutonomySettings && project && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(AutonomySettingsModal, {
                project: project,
                onClose: ()=>setShowAutonomySettings(false),
                onSave: onAutonomyChange
            }, void 0, false, {
                fileName: "[project]/components/progress-panel.tsx",
                lineNumber: 233,
                columnNumber: 9
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/components/progress-panel.tsx",
        lineNumber: 165,
        columnNumber: 5
    }, this);
}
function AutonomySettingsModal({ project, onClose, onSave }) {
    const [autonomy, setAutonomy] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(project.agent_autonomy || {});
    const allPhases = [
        {
            id: "intent",
            name: "意图分析",
            desc: "Agent自动提问并分析意图"
        },
        {
            id: "research",
            name: "消费者调研",
            desc: "Agent自动调研用户画像"
        },
        {
            id: "design_inner",
            name: "内涵设计",
            desc: "Agent自动设计内容方案"
        },
        {
            id: "produce_inner",
            name: "内涵生产",
            desc: "Agent自动生产各字段内容"
        },
        {
            id: "design_outer",
            name: "外延设计",
            desc: "Agent自动设计传播方案"
        },
        {
            id: "produce_outer",
            name: "外延生产",
            desc: "Agent自动生产渠道内容"
        },
        {
            id: "simulate",
            name: "消费者模拟",
            desc: "Agent自动模拟用户体验"
        },
        {
            id: "evaluate",
            name: "评估",
            desc: "Agent自动评估内容质量"
        }
    ];
    const handleToggle = (phase)=>{
        setAutonomy((prev)=>({
                ...prev,
                [phase]: !prev[phase]
            }));
    };
    const handleSave = ()=>{
        onSave?.(autonomy);
        onClose();
    };
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "fixed inset-0 bg-black/50 flex items-center justify-center z-50",
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
            className: "bg-surface-2 rounded-xl border border-surface-3 w-full max-w-lg max-h-[80vh] overflow-hidden",
            children: [
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "px-4 py-3 border-b border-surface-3",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                            className: "font-medium text-zinc-200",
                            children: "Agent自主权设置"
                        }, void 0, false, {
                            fileName: "[project]/components/progress-panel.tsx",
                            lineNumber: 281,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                            className: "text-xs text-zinc-500 mt-1",
                            children: "设置各阶段Agent是否自动执行，不勾选 = 需要人工确认后才继续"
                        }, void 0, false, {
                            fileName: "[project]/components/progress-panel.tsx",
                            lineNumber: 282,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/components/progress-panel.tsx",
                    lineNumber: 280,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "p-4 max-h-[50vh] overflow-y-auto space-y-3",
                    children: allPhases.map((phase)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                            className: "flex items-start gap-3 p-3 rounded-lg hover:bg-surface-3 cursor-pointer",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                    type: "checkbox",
                                    checked: autonomy[phase.id] !== false,
                                    onChange: ()=>handleToggle(phase.id),
                                    className: "mt-0.5 rounded"
                                }, void 0, false, {
                                    fileName: "[project]/components/progress-panel.tsx",
                                    lineNumber: 293,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex-1",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "text-sm text-zinc-200",
                                            children: phase.name
                                        }, void 0, false, {
                                            fileName: "[project]/components/progress-panel.tsx",
                                            lineNumber: 300,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "text-xs text-zinc-500 mt-0.5",
                                            children: phase.desc
                                        }, void 0, false, {
                                            fileName: "[project]/components/progress-panel.tsx",
                                            lineNumber: 301,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/components/progress-panel.tsx",
                                    lineNumber: 299,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    className: `text-xs px-2 py-0.5 rounded ${autonomy[phase.id] !== false ? "bg-green-600/20 text-green-400" : "bg-yellow-600/20 text-yellow-400"}`,
                                    children: autonomy[phase.id] !== false ? "自动" : "需确认"
                                }, void 0, false, {
                                    fileName: "[project]/components/progress-panel.tsx",
                                    lineNumber: 303,
                                    columnNumber: 15
                                }, this)
                            ]
                        }, phase.id, true, {
                            fileName: "[project]/components/progress-panel.tsx",
                            lineNumber: 289,
                            columnNumber: 13
                        }, this))
                }, void 0, false, {
                    fileName: "[project]/components/progress-panel.tsx",
                    lineNumber: 287,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "px-4 py-3 border-t border-surface-3 flex justify-between",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "flex gap-2",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                    onClick: ()=>setAutonomy(allPhases.reduce((acc, p)=>({
                                                ...acc,
                                                [p.id]: true
                                            }), {})),
                                    className: "px-3 py-1.5 text-xs bg-surface-3 hover:bg-surface-4 rounded-lg",
                                    children: "全部自动"
                                }, void 0, false, {
                                    fileName: "[project]/components/progress-panel.tsx",
                                    lineNumber: 316,
                                    columnNumber: 13
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                    onClick: ()=>setAutonomy(allPhases.reduce((acc, p)=>({
                                                ...acc,
                                                [p.id]: false
                                            }), {})),
                                    className: "px-3 py-1.5 text-xs bg-surface-3 hover:bg-surface-4 rounded-lg",
                                    children: "全部确认"
                                }, void 0, false, {
                                    fileName: "[project]/components/progress-panel.tsx",
                                    lineNumber: 322,
                                    columnNumber: 13
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/components/progress-panel.tsx",
                            lineNumber: 315,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "flex gap-2",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                    onClick: onClose,
                                    className: "px-4 py-2 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg",
                                    children: "取消"
                                }, void 0, false, {
                                    fileName: "[project]/components/progress-panel.tsx",
                                    lineNumber: 330,
                                    columnNumber: 13
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                    onClick: handleSave,
                                    className: "px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg",
                                    children: "保存"
                                }, void 0, false, {
                                    fileName: "[project]/components/progress-panel.tsx",
                                    lineNumber: 336,
                                    columnNumber: 13
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/components/progress-panel.tsx",
                            lineNumber: 329,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/components/progress-panel.tsx",
                    lineNumber: 314,
                    columnNumber: 9
                }, this)
            ]
        }, void 0, true, {
            fileName: "[project]/components/progress-panel.tsx",
            lineNumber: 279,
            columnNumber: 7
        }, this)
    }, void 0, false, {
        fileName: "[project]/components/progress-panel.tsx",
        lineNumber: 278,
        columnNumber: 5
    }, this);
}
}),
"[project]/lib/api.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "agentAPI",
    ()=>agentAPI,
    "fieldAPI",
    ()=>fieldAPI,
    "projectAPI",
    ()=>projectAPI,
    "settingsAPI",
    ()=>settingsAPI,
    "simulationAPI",
    ()=>simulationAPI
]);
// frontend/lib/api.ts
// 功能: API客户端，封装后端API调用
// 主要函数: fetchAPI, streamAPI
// 数据结构: Project, Field, ChatMessage
const API_BASE = ("TURBOPACK compile-time value", "http://localhost:8000") || "http://localhost:8000";
// ============== API Functions ==============
async function fetchAPI(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const response = await fetch(url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...options.headers
        }
    });
    if (!response.ok) {
        const error = await response.json().catch(()=>({
                detail: "Unknown error"
            }));
        // 处理Pydantic验证错误格式 (detail可能是数组)
        let errorMessage;
        if (typeof error.detail === "string") {
            errorMessage = error.detail;
        } else if (Array.isArray(error.detail)) {
            errorMessage = error.detail.map((e)=>e.msg || e.message || JSON.stringify(e)).join("; ");
        } else {
            errorMessage = `API error: ${response.status}`;
        }
        throw new Error(errorMessage);
    }
    return response.json();
}
const projectAPI = {
    list: ()=>fetchAPI("/api/projects/"),
    get: (id)=>fetchAPI(`/api/projects/${id}`),
    create: (data)=>fetchAPI("/api/projects/", {
            method: "POST",
            body: JSON.stringify(data)
        }),
    update: (id, data)=>fetchAPI(`/api/projects/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    delete: (id)=>fetchAPI(`/api/projects/${id}`, {
            method: "DELETE"
        }),
    createVersion: (id, version_note)=>fetchAPI(`/api/projects/${id}/versions`, {
            method: "POST",
            body: JSON.stringify({
                version_note
            })
        })
};
const fieldAPI = {
    listByProject: (projectId, phase)=>{
        const query = phase ? `?phase=${phase}` : "";
        return fetchAPI(`/api/fields/project/${projectId}${query}`);
    },
    get: (id)=>fetchAPI(`/api/fields/${id}`),
    create: (data)=>fetchAPI("/api/fields/", {
            method: "POST",
            body: JSON.stringify(data)
        }),
    update: (id, data)=>fetchAPI(`/api/fields/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    delete: (id)=>fetchAPI(`/api/fields/${id}`, {
            method: "DELETE"
        }),
    generate: (id, pre_answers = {})=>fetchAPI(`/api/fields/${id}/generate`, {
            method: "POST",
            body: JSON.stringify({
                pre_answers
            })
        })
};
const agentAPI = {
    chat: (projectId, message, currentPhase)=>fetchAPI("/api/agent/chat", {
            method: "POST",
            body: JSON.stringify({
                project_id: projectId,
                message,
                current_phase: currentPhase
            })
        }),
    advance: (projectId)=>fetchAPI("/api/agent/advance", {
            method: "POST",
            body: JSON.stringify({
                project_id: projectId,
                message: "继续"
            })
        }),
    stream: async function*(projectId, message, currentPhase) {
        const response = await fetch(`${API_BASE}/api/agent/stream`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                project_id: projectId,
                message,
                current_phase: currentPhase
            })
        });
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        if (!reader) return;
        while(true){
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value);
            const lines = text.split("\n");
            for (const line of lines){
                if (line.startsWith("data: ")) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        yield data;
                    } catch  {
                    // Ignore parse errors
                    }
                }
            }
        }
    }
};
const settingsAPI = {
    // System Prompts
    listSystemPrompts: ()=>fetchAPI("/api/settings/system-prompts"),
    updateSystemPrompt: (id, data)=>fetchAPI(`/api/settings/system-prompts/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    // Creator Profiles
    listCreatorProfiles: ()=>fetchAPI("/api/settings/creator-profiles"),
    createCreatorProfile: (data)=>fetchAPI("/api/settings/creator-profiles", {
            method: "POST",
            body: JSON.stringify(data)
        }),
    updateCreatorProfile: (id, data)=>fetchAPI(`/api/settings/creator-profiles/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    deleteCreatorProfile: (id)=>fetchAPI(`/api/settings/creator-profiles/${id}`, {
            method: "DELETE"
        }),
    // Field Templates
    listFieldTemplates: ()=>fetchAPI("/api/settings/field-templates"),
    createFieldTemplate: (data)=>fetchAPI("/api/settings/field-templates", {
            method: "POST",
            body: JSON.stringify(data)
        }),
    updateFieldTemplate: (id, data)=>fetchAPI(`/api/settings/field-templates/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    deleteFieldTemplate: (id)=>fetchAPI(`/api/settings/field-templates/${id}`, {
            method: "DELETE"
        }),
    // Channels
    listChannels: ()=>fetchAPI("/api/settings/channels"),
    createChannel: (data)=>fetchAPI("/api/settings/channels", {
            method: "POST",
            body: JSON.stringify(data)
        }),
    updateChannel: (id, data)=>fetchAPI(`/api/settings/channels/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    deleteChannel: (id)=>fetchAPI(`/api/settings/channels/${id}`, {
            method: "DELETE"
        }),
    // Simulators
    listSimulators: ()=>fetchAPI("/api/settings/simulators"),
    createSimulator: (data)=>fetchAPI("/api/settings/simulators", {
            method: "POST",
            body: JSON.stringify(data)
        }),
    updateSimulator: (id, data)=>fetchAPI(`/api/settings/simulators/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    deleteSimulator: (id)=>fetchAPI(`/api/settings/simulators/${id}`, {
            method: "DELETE"
        }),
    // Agent Settings
    getAgentSettings: ()=>fetchAPI("/api/settings/agent"),
    updateAgentSettings: (data)=>fetchAPI("/api/settings/agent", {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    // Logs
    listLogs: (projectId)=>{
        const query = projectId ? `?project_id=${projectId}` : "";
        return fetchAPI(`/api/settings/logs${query}`);
    },
    exportLogs: (projectId)=>{
        const query = projectId ? `?project_id=${projectId}` : "";
        return fetchAPI(`/api/settings/logs/export${query}`);
    }
};
const simulationAPI = {
    // 获取项目的模拟记录列表
    list: (projectId)=>fetchAPI(`/api/simulations/project/${projectId}`),
    // 获取模拟记录详情
    get: (id)=>fetchAPI(`/api/simulations/${id}`),
    // 创建模拟记录
    create: (data)=>fetchAPI("/api/simulations/", {
            method: "POST",
            body: JSON.stringify(data)
        }),
    // 删除模拟记录
    delete: (id)=>fetchAPI(`/api/simulations/${id}`, {
            method: "DELETE"
        }),
    // 获取消费者调研中的人物小传
    getPersonasFromResearch: (projectId)=>fetchAPI(`/api/simulations/project/${projectId}/personas`)
};
}),
"[project]/components/content-panel.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "ContentPanel",
    ()=>ContentPanel
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/utils.ts [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/api.ts [app-ssr] (ecmascript)");
// frontend/components/content-panel.tsx
// 功能: 中栏内容展示面板，支持字段依赖选择和生成
// 主要组件: ContentPanel, FieldCard
// 新增: 依赖选择弹窗、生成按钮、依赖状态显示、模拟阶段特殊面板
"use client";
;
;
;
;
function ContentPanel({ projectId, currentPhase, fields, onFieldUpdate, onFieldsChange }) {
    const phaseFields = fields.filter((f)=>f.phase === currentPhase);
    const allCompletedFields = fields.filter((f)=>f.status === "completed");
    if (!projectId) {
        return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
            className: "flex items-center justify-center h-full text-zinc-500",
            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "text-center",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-lg mb-2",
                        children: "请选择或创建一个项目"
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 36,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-sm",
                        children: "在左侧选择项目开始工作"
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 37,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/content-panel.tsx",
                lineNumber: 35,
                columnNumber: 9
            }, this)
        }, void 0, false, {
            fileName: "[project]/components/content-panel.tsx",
            lineNumber: 34,
            columnNumber: 7
        }, this);
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "p-6 max-w-4xl mx-auto",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "mb-8",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h1", {
                        className: "text-2xl font-bold text-zinc-100",
                        children: __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["PHASE_NAMES"][currentPhase] || currentPhase
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 47,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-zinc-500 mt-1",
                        children: getPhaseDescription(currentPhase)
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 50,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/content-panel.tsx",
                lineNumber: 46,
                columnNumber: 7
            }, this),
            phaseFields.length > 0 ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "space-y-6",
                children: phaseFields.map((field)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(FieldCard, {
                        field: field,
                        allFields: fields,
                        onUpdate: (content)=>onFieldUpdate?.(field.id, content),
                        onFieldsChange: onFieldsChange
                    }, field.id, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 59,
                        columnNumber: 13
                    }, this))
            }, void 0, false, {
                fileName: "[project]/components/content-panel.tsx",
                lineNumber: 57,
                columnNumber: 9
            }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "text-center py-12 text-zinc-500",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: "当前阶段暂无内容"
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 70,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-sm mt-2",
                        children: "在右侧与 AI Agent 对话开始生产内容"
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 71,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/content-panel.tsx",
                lineNumber: 69,
                columnNumber: 9
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/components/content-panel.tsx",
        lineNumber: 44,
        columnNumber: 5
    }, this);
}
function FieldCard({ field, allFields, onUpdate, onFieldsChange }) {
    const [isEditing, setIsEditing] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [content, setContent] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(field.content);
    const [showDependencyModal, setShowDependencyModal] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [isGenerating, setIsGenerating] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [generatingContent, setGeneratingContent] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        setContent(field.content);
    }, [
        field.content
    ]);
    // 获取依赖字段信息
    const dependsOnIds = field.dependencies?.depends_on || [];
    const dependencyFields = allFields.filter((f)=>dependsOnIds.includes(f.id));
    const unmetDependencies = dependencyFields.filter((f)=>f.status !== "completed");
    const canGenerate = unmetDependencies.length === 0;
    const handleSave = ()=>{
        onUpdate?.(content);
        setIsEditing(false);
    };
    const handleGenerate = async ()=>{
        if (!canGenerate) {
            alert(`请先完成依赖字段: ${unmetDependencies.map((f)=>f.name).join(", ")}`);
            return;
        }
        setIsGenerating(true);
        setGeneratingContent("");
        try {
            // 使用流式生成
            const response = await fetch(`http://localhost:8000/api/fields/${field.id}/generate/stream`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    pre_answers: field.pre_answers || {}
                })
            });
            const reader = response.body?.getReader();
            const decoder = new TextDecoder();
            if (reader) {
                while(true){
                    const { done, value } = await reader.read();
                    if (done) break;
                    const text = decoder.decode(value);
                    const lines = text.split("\n");
                    for (const line of lines){
                        if (line.startsWith("data: ")) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                if (data.chunk) {
                                    setGeneratingContent((prev)=>prev + data.chunk);
                                }
                                if (data.done) {
                                    onFieldsChange?.();
                                }
                            } catch  {}
                        }
                    }
                }
            }
        } catch (err) {
            console.error("生成失败:", err);
            alert("生成失败: " + (err instanceof Error ? err.message : "未知错误"));
        } finally{
            setIsGenerating(false);
        }
    };
    const handleUpdateDependencies = async (newDependsOn)=>{
        try {
            await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["fieldAPI"].update(field.id, {
                dependencies: {
                    depends_on: newDependsOn,
                    dependency_type: field.dependencies?.dependency_type || "all"
                }
            });
            onFieldsChange?.();
            setShowDependencyModal(false);
        } catch (err) {
            alert("更新依赖失败: " + (err instanceof Error ? err.message : "未知错误"));
        }
    };
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "bg-surface-2 rounded-xl border border-surface-3 overflow-hidden",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "px-4 py-3 border-b border-surface-3",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "flex items-center justify-between",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                        className: "font-medium text-zinc-200",
                                        children: field.name
                                    }, void 0, false, {
                                        fileName: "[project]/components/content-panel.tsx",
                                        lineNumber: 181,
                                        columnNumber: 13
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        className: "flex items-center gap-2 mt-1",
                                        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: `text-xs px-2 py-0.5 rounded ${field.status === "completed" ? "bg-green-600/20 text-green-400" : field.status === "generating" ? "bg-yellow-600/20 text-yellow-400" : "bg-zinc-600/20 text-zinc-400"}`,
                                            children: field.status === "completed" ? "已生成" : field.status === "generating" ? "生成中..." : "待生成"
                                        }, void 0, false, {
                                            fileName: "[project]/components/content-panel.tsx",
                                            lineNumber: 183,
                                            columnNumber: 15
                                        }, this)
                                    }, void 0, false, {
                                        fileName: "[project]/components/content-panel.tsx",
                                        lineNumber: 182,
                                        columnNumber: 13
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/components/content-panel.tsx",
                                lineNumber: 180,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "flex gap-2",
                                children: [
                                    field.status !== "completed" && !isGenerating && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                        onClick: handleGenerate,
                                        disabled: !canGenerate,
                                        className: `px-3 py-1 text-sm rounded-lg transition-colors ${canGenerate ? "bg-brand-600 hover:bg-brand-700 text-white" : "bg-zinc-700 text-zinc-500 cursor-not-allowed"}`,
                                        title: canGenerate ? "生成内容" : `依赖未满足: ${unmetDependencies.map((f)=>f.name).join(", ")}`,
                                        children: "生成"
                                    }, void 0, false, {
                                        fileName: "[project]/components/content-panel.tsx",
                                        lineNumber: 199,
                                        columnNumber: 15
                                    }, this),
                                    isEditing ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Fragment"], {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                onClick: handleSave,
                                                className: "px-3 py-1 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors",
                                                children: "保存"
                                            }, void 0, false, {
                                                fileName: "[project]/components/content-panel.tsx",
                                                lineNumber: 215,
                                                columnNumber: 17
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                onClick: ()=>{
                                                    setContent(field.content);
                                                    setIsEditing(false);
                                                },
                                                className: "px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors",
                                                children: "取消"
                                            }, void 0, false, {
                                                fileName: "[project]/components/content-panel.tsx",
                                                lineNumber: 221,
                                                columnNumber: 17
                                            }, this)
                                        ]
                                    }, void 0, true) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                        onClick: ()=>setIsEditing(true),
                                        className: "px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors",
                                        children: "编辑"
                                    }, void 0, false, {
                                        fileName: "[project]/components/content-panel.tsx",
                                        lineNumber: 232,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/components/content-panel.tsx",
                                lineNumber: 197,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 179,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "mt-2 flex items-center gap-2 flex-wrap",
                        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                            onClick: ()=>setShowDependencyModal(true),
                            className: "text-xs text-zinc-500 hover:text-zinc-300 flex items-center gap-1",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    children: "📎 依赖:"
                                }, void 0, false, {
                                    fileName: "[project]/components/content-panel.tsx",
                                    lineNumber: 248,
                                    columnNumber: 13
                                }, this),
                                dependencyFields.length > 0 ? dependencyFields.map((df)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        className: `px-1.5 py-0.5 rounded text-xs ${df.status === "completed" ? "bg-green-600/20 text-green-400" : "bg-red-600/20 text-red-400"}`,
                                        children: df.name
                                    }, df.id, false, {
                                        fileName: "[project]/components/content-panel.tsx",
                                        lineNumber: 251,
                                        columnNumber: 17
                                    }, this)) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    className: "text-zinc-600",
                                    children: "无"
                                }, void 0, false, {
                                    fileName: "[project]/components/content-panel.tsx",
                                    lineNumber: 263,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    className: "text-zinc-600 ml-1",
                                    children: "（点击编辑）"
                                }, void 0, false, {
                                    fileName: "[project]/components/content-panel.tsx",
                                    lineNumber: 265,
                                    columnNumber: 13
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/components/content-panel.tsx",
                            lineNumber: 244,
                            columnNumber: 11
                        }, this)
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 243,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/content-panel.tsx",
                lineNumber: 178,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "p-4",
                children: isGenerating ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "bg-surface-1 border border-surface-3 rounded-lg p-3",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "text-xs text-brand-400 mb-2",
                            children: "正在生成..."
                        }, void 0, false, {
                            fileName: "[project]/components/content-panel.tsx",
                            lineNumber: 274,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "whitespace-pre-wrap text-zinc-300 animate-pulse",
                            children: generatingContent || "⏳ 准备中..."
                        }, void 0, false, {
                            fileName: "[project]/components/content-panel.tsx",
                            lineNumber: 275,
                            columnNumber: 13
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/components/content-panel.tsx",
                    lineNumber: 273,
                    columnNumber: 11
                }, this) : isEditing ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("textarea", {
                    value: content,
                    onChange: (e)=>setContent(e.target.value),
                    className: "w-full min-h-[200px] bg-surface-1 border border-surface-3 rounded-lg p-3 text-zinc-200 resize-y focus:outline-none focus:ring-2 focus:ring-brand-500"
                }, void 0, false, {
                    fileName: "[project]/components/content-panel.tsx",
                    lineNumber: 280,
                    columnNumber: 11
                }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "prose prose-invert max-w-none",
                    children: field.content ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "whitespace-pre-wrap text-zinc-300",
                        children: field.content
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 288,
                        columnNumber: 15
                    }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-zinc-500 italic",
                        children: '暂无内容，点击"生成"按钮开始'
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 292,
                        columnNumber: 15
                    }, this)
                }, void 0, false, {
                    fileName: "[project]/components/content-panel.tsx",
                    lineNumber: 286,
                    columnNumber: 11
                }, this)
            }, void 0, false, {
                fileName: "[project]/components/content-panel.tsx",
                lineNumber: 271,
                columnNumber: 7
            }, this),
            showDependencyModal && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(DependencyModal, {
                field: field,
                allFields: allFields,
                onClose: ()=>setShowDependencyModal(false),
                onSave: handleUpdateDependencies
            }, void 0, false, {
                fileName: "[project]/components/content-panel.tsx",
                lineNumber: 300,
                columnNumber: 9
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/components/content-panel.tsx",
        lineNumber: 176,
        columnNumber: 5
    }, this);
}
function DependencyModal({ field, allFields, onClose, onSave }) {
    const [selectedIds, setSelectedIds] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(field.dependencies?.depends_on || []);
    // 可选的依赖字段（排除自己）
    const availableFields = allFields.filter((f)=>f.id !== field.id);
    const toggleField = (id)=>{
        setSelectedIds((prev)=>prev.includes(id) ? prev.filter((x)=>x !== id) : [
                ...prev,
                id
            ]);
    };
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "fixed inset-0 bg-black/50 flex items-center justify-center z-50",
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
            className: "bg-surface-2 rounded-xl border border-surface-3 w-full max-w-lg max-h-[80vh] overflow-hidden",
            children: [
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "px-4 py-3 border-b border-surface-3",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                            className: "font-medium text-zinc-200",
                            children: "设置依赖关系"
                        }, void 0, false, {
                            fileName: "[project]/components/content-panel.tsx",
                            lineNumber: 336,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                            className: "text-xs text-zinc-500 mt-1",
                            children: [
                                '选择生成"',
                                field.name,
                                '"前需要先完成的字段'
                            ]
                        }, void 0, true, {
                            fileName: "[project]/components/content-panel.tsx",
                            lineNumber: 337,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/components/content-panel.tsx",
                    lineNumber: 335,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "p-4 max-h-[50vh] overflow-y-auto space-y-2",
                    children: availableFields.length > 0 ? availableFields.map((f)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                            className: "flex items-center gap-3 p-2 rounded-lg hover:bg-surface-3 cursor-pointer",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                    type: "checkbox",
                                    checked: selectedIds.includes(f.id),
                                    onChange: ()=>toggleField(f.id),
                                    className: "rounded"
                                }, void 0, false, {
                                    fileName: "[project]/components/content-panel.tsx",
                                    lineNumber: 349,
                                    columnNumber: 17
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex-1",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "text-sm text-zinc-200",
                                            children: f.name
                                        }, void 0, false, {
                                            fileName: "[project]/components/content-panel.tsx",
                                            lineNumber: 356,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "text-xs text-zinc-500",
                                            children: [
                                                f.phase,
                                                " · ",
                                                f.status === "completed" ? "已完成" : "未完成"
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/components/content-panel.tsx",
                                            lineNumber: 357,
                                            columnNumber: 19
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/components/content-panel.tsx",
                                    lineNumber: 355,
                                    columnNumber: 17
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    className: `w-2 h-2 rounded-full ${f.status === "completed" ? "bg-green-500" : "bg-zinc-600"}`
                                }, void 0, false, {
                                    fileName: "[project]/components/content-panel.tsx",
                                    lineNumber: 361,
                                    columnNumber: 17
                                }, this)
                            ]
                        }, f.id, true, {
                            fileName: "[project]/components/content-panel.tsx",
                            lineNumber: 345,
                            columnNumber: 15
                        }, this)) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-zinc-500 text-center py-4",
                        children: "暂无可选的依赖字段"
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 369,
                        columnNumber: 13
                    }, this)
                }, void 0, false, {
                    fileName: "[project]/components/content-panel.tsx",
                    lineNumber: 342,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "px-4 py-3 border-t border-surface-3 flex justify-end gap-2",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                            onClick: onClose,
                            className: "px-4 py-2 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors",
                            children: "取消"
                        }, void 0, false, {
                            fileName: "[project]/components/content-panel.tsx",
                            lineNumber: 374,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                            onClick: ()=>onSave(selectedIds),
                            className: "px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors",
                            children: "保存"
                        }, void 0, false, {
                            fileName: "[project]/components/content-panel.tsx",
                            lineNumber: 380,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/components/content-panel.tsx",
                    lineNumber: 373,
                    columnNumber: 9
                }, this)
            ]
        }, void 0, true, {
            fileName: "[project]/components/content-panel.tsx",
            lineNumber: 334,
            columnNumber: 7
        }, this)
    }, void 0, false, {
        fileName: "[project]/components/content-panel.tsx",
        lineNumber: 333,
        columnNumber: 5
    }, this);
}
function getPhaseDescription(phase) {
    const descriptions = {
        intent: "澄清内容生产的核心意图和目标",
        research: "调研目标用户，了解痛点和需求",
        design_inner: "设计内容生产方案和大纲",
        produce_inner: "生产核心内容",
        design_outer: "设计外延传播方案",
        produce_outer: "为各渠道生产营销内容",
        simulate: "模拟用户体验，收集反馈",
        evaluate: "全面评估内容质量"
    };
    return descriptions[phase] || "";
}
}),
"[project]/components/agent-panel.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "AgentPanel",
    ()=>AgentPanel
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/utils.ts [app-ssr] (ecmascript)");
// frontend/components/agent-panel.tsx
// 功能: 右栏AI Agent对话面板，支持@引用机制
// 主要组件: AgentPanel, MessageBubble, MentionDropdown
// @引用: 输入@弹出已生成字段选择菜单
"use client";
;
;
;
function AgentPanel({ projectId, fields = [], onSendMessage, isLoading = false }) {
    const [messages, setMessages] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])([]);
    const [input, setInput] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [sending, setSending] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [showMentions, setShowMentions] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [mentionFilter, setMentionFilter] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [mentionIndex, setMentionIndex] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(0);
    const [cursorPosition, setCursorPosition] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(0);
    const messagesEndRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
    const inputRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
    const mentionStartPos = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(-1);
    // 可引用的字段（已完成的）
    const completedFields = fields.filter((f)=>f.status === "completed");
    // 过滤后的字段列表
    const filteredFields = completedFields.filter((f)=>f.name.toLowerCase().includes(mentionFilter.toLowerCase()) || f.phase.toLowerCase().includes(mentionFilter.toLowerCase()));
    // 自动滚动到底部
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        messagesEndRef.current?.scrollIntoView({
            behavior: "smooth"
        });
    }, [
        messages
    ]);
    const insertMention = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useCallback"])((field)=>{
        const beforeMention = input.slice(0, mentionStartPos.current);
        const afterMention = input.slice(cursorPosition);
        const newInput = `${beforeMention}@${field.name}${afterMention}`;
        setInput(newInput);
        setShowMentions(false);
        setMentionFilter("");
        mentionStartPos.current = -1;
        // 聚焦回输入框
        setTimeout(()=>{
            inputRef.current?.focus();
        }, 0);
    }, [
        input,
        cursorPosition
    ]);
    const handleInputChange = (e)=>{
        const value = e.target.value;
        const selectionStart = e.target.selectionStart || 0;
        setInput(value);
        setCursorPosition(selectionStart);
        // 检测@符号
        const lastAtPos = value.lastIndexOf("@", selectionStart - 1);
        if (lastAtPos !== -1) {
            const textAfterAt = value.slice(lastAtPos + 1, selectionStart);
            // 如果@后面没有空格，显示菜单
            if (!textAfterAt.includes(" ")) {
                mentionStartPos.current = lastAtPos;
                setMentionFilter(textAfterAt);
                setShowMentions(true);
                setMentionIndex(0);
                return;
            }
        }
        setShowMentions(false);
        setMentionFilter("");
    };
    const handleKeyDown = (e)=>{
        if (showMentions && filteredFields.length > 0) {
            if (e.key === "ArrowDown") {
                e.preventDefault();
                setMentionIndex((prev)=>(prev + 1) % filteredFields.length);
                return;
            }
            if (e.key === "ArrowUp") {
                e.preventDefault();
                setMentionIndex((prev)=>(prev - 1 + filteredFields.length) % filteredFields.length);
                return;
            }
            if (e.key === "Enter" || e.key === "Tab") {
                e.preventDefault();
                insertMention(filteredFields[mentionIndex]);
                return;
            }
            if (e.key === "Escape") {
                setShowMentions(false);
                return;
            }
        }
        if (e.key === "Enter" && !e.shiftKey && !showMentions) {
            e.preventDefault();
            handleSend();
        }
    };
    const handleSend = async ()=>{
        if (!input.trim() || !projectId || sending) return;
        const userMessage = input.trim();
        setInput("");
        setSending(true);
        setShowMentions(false);
        // 添加用户消息
        setMessages((prev)=>[
                ...prev,
                {
                    role: "user",
                    content: userMessage
                }
            ]);
        try {
            const response = await onSendMessage?.(userMessage);
            if (response) {
                setMessages((prev)=>[
                        ...prev,
                        {
                            role: "assistant",
                            content: response
                        }
                    ]);
            }
        } catch (error) {
            setMessages((prev)=>[
                    ...prev,
                    {
                        role: "assistant",
                        content: `抱歉，发生了错误：${error instanceof Error ? error.message : "未知错误"}`
                    }
                ]);
        } finally{
            setSending(false);
        }
    };
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "flex flex-col h-full",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "px-4 py-3 border-b border-surface-3",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                        className: "font-semibold text-zinc-100",
                        children: "AI Agent"
                    }, void 0, false, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 164,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-xs text-zinc-500",
                        children: projectId ? "与 Agent 对话推进内容生产" : "请先选择项目"
                    }, void 0, false, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 165,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/agent-panel.tsx",
                lineNumber: 163,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "flex-1 overflow-y-auto p-4 space-y-4",
                children: [
                    messages.length === 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "text-center text-zinc-500 py-8",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                children: "开始对话吧！"
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 174,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "text-sm mt-2",
                                children: '你可以说 "开始" 来启动内容生产流程'
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 175,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 173,
                        columnNumber: 11
                    }, this),
                    messages.map((msg, idx)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(MessageBubble, {
                            message: msg
                        }, idx, false, {
                            fileName: "[project]/components/agent-panel.tsx",
                            lineNumber: 182,
                            columnNumber: 11
                        }, this)),
                    sending && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "flex items-center gap-2 text-zinc-500",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "w-2 h-2 bg-brand-500 rounded-full animate-pulse"
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 187,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "text-sm",
                                children: "Agent 正在思考..."
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 188,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 186,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        ref: messagesEndRef
                    }, void 0, false, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 192,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/agent-panel.tsx",
                lineNumber: 171,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "p-4 border-t border-surface-3",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "relative",
                        children: [
                            showMentions && filteredFields.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "absolute bottom-full left-0 right-0 mb-1 bg-surface-2 border border-surface-3 rounded-lg shadow-xl max-h-48 overflow-y-auto z-10",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        className: "p-2 text-xs text-zinc-500 border-b border-surface-3",
                                        children: "选择要引用的字段"
                                    }, void 0, false, {
                                        fileName: "[project]/components/agent-panel.tsx",
                                        lineNumber: 201,
                                        columnNumber: 15
                                    }, this),
                                    filteredFields.map((field, idx)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                            onClick: ()=>insertMention(field),
                                            className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("w-full px-3 py-2 text-left hover:bg-surface-3 flex items-center gap-2", idx === mentionIndex && "bg-surface-3"),
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "text-xs text-zinc-500",
                                                    children: __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["PHASE_NAMES"][field.phase] || field.phase
                                                }, void 0, false, {
                                                    fileName: "[project]/components/agent-panel.tsx",
                                                    lineNumber: 213,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "text-sm text-zinc-200",
                                                    children: field.name
                                                }, void 0, false, {
                                                    fileName: "[project]/components/agent-panel.tsx",
                                                    lineNumber: 214,
                                                    columnNumber: 19
                                                }, this)
                                            ]
                                        }, field.id, true, {
                                            fileName: "[project]/components/agent-panel.tsx",
                                            lineNumber: 205,
                                            columnNumber: 17
                                        }, this))
                                ]
                            }, void 0, true, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 200,
                                columnNumber: 13
                            }, this),
                            showMentions && filteredFields.length === 0 && mentionFilter && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "absolute bottom-full left-0 right-0 mb-1 bg-surface-2 border border-surface-3 rounded-lg p-3 text-center text-sm text-zinc-500",
                                children: "没有找到匹配的字段"
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 221,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "flex gap-2",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                        ref: inputRef,
                                        type: "text",
                                        value: input,
                                        onChange: handleInputChange,
                                        onKeyDown: handleKeyDown,
                                        placeholder: projectId ? "输入消息... 使用 @ 引用字段" : "请先选择项目",
                                        disabled: !projectId || sending,
                                        className: "flex-1 px-4 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                                    }, void 0, false, {
                                        fileName: "[project]/components/agent-panel.tsx",
                                        lineNumber: 227,
                                        columnNumber: 13
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                        onClick: handleSend,
                                        disabled: !projectId || !input.trim() || sending,
                                        className: "px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:bg-surface-3 disabled:cursor-not-allowed rounded-lg transition-colors",
                                        children: "发送"
                                    }, void 0, false, {
                                        fileName: "[project]/components/agent-panel.tsx",
                                        lineNumber: 237,
                                        columnNumber: 13
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 226,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 197,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "flex gap-2 mt-2",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(QuickAction, {
                                label: "继续",
                                onClick: ()=>setInput("继续"),
                                disabled: !projectId || sending
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 249,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(QuickAction, {
                                label: "开始调研",
                                onClick: ()=>setInput("开始消费者调研"),
                                disabled: !projectId || sending
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 254,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(QuickAction, {
                                label: "评估",
                                onClick: ()=>setInput("评估当前内容"),
                                disabled: !projectId || sending
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 259,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 248,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/agent-panel.tsx",
                lineNumber: 196,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/components/agent-panel.tsx",
        lineNumber: 161,
        columnNumber: 5
    }, this);
}
function MessageBubble({ message }) {
    const isUser = message.role === "user";
    // 高亮@引用
    const renderContent = (content)=>{
        const parts = content.split(/(@[\u4e00-\u9fffa-zA-Z0-9_]+)/g);
        return parts.map((part, i)=>{
            if (part.startsWith("@")) {
                return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                    className: "text-brand-400 font-medium",
                    children: part
                }, i, false, {
                    fileName: "[project]/components/agent-panel.tsx",
                    lineNumber: 279,
                    columnNumber: 11
                }, this);
            }
            return part;
        });
    };
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("flex", isUser ? "justify-end" : "justify-start"),
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
            className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("max-w-[85%] px-4 py-2 rounded-2xl", isUser ? "bg-brand-600 text-white rounded-br-md" : "bg-surface-3 text-zinc-200 rounded-bl-md"),
            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "whitespace-pre-wrap text-sm",
                children: renderContent(message.content)
            }, void 0, false, {
                fileName: "[project]/components/agent-panel.tsx",
                lineNumber: 298,
                columnNumber: 9
            }, this)
        }, void 0, false, {
            fileName: "[project]/components/agent-panel.tsx",
            lineNumber: 290,
            columnNumber: 7
        }, this)
    }, void 0, false, {
        fileName: "[project]/components/agent-panel.tsx",
        lineNumber: 289,
        columnNumber: 5
    }, this);
}
function QuickAction({ label, onClick, disabled }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
        onClick: onClick,
        disabled: disabled,
        className: "px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 disabled:opacity-50 disabled:cursor-not-allowed rounded transition-colors",
        children: label
    }, void 0, false, {
        fileName: "[project]/components/agent-panel.tsx",
        lineNumber: 316,
        columnNumber: 5
    }, this);
}
}),
"[project]/app/workspace/page.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "default",
    ()=>WorkspacePage
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$components$2f$layout$2f$workspace$2d$layout$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/components/layout/workspace-layout.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$components$2f$progress$2d$panel$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/components/progress-panel.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$components$2f$content$2d$panel$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/components/content-panel.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$components$2f$agent$2d$panel$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/components/agent-panel.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/api.ts [app-ssr] (ecmascript)");
// frontend/app/workspace/page.tsx
// 功能: 内容生产工作台主页面
// 主要组件: WorkspacePage
"use client";
;
;
;
;
;
;
;
function WorkspacePage() {
    const [projects, setProjects] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])([]);
    const [currentProject, setCurrentProject] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [fields, setFields] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])([]);
    const [loading, setLoading] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(true);
    const [error, setError] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    // 加载项目列表
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        loadProjects();
    }, []);
    // 加载当前项目的字段
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        if (currentProject) {
            loadFields(currentProject.id);
        }
    }, [
        currentProject?.id
    ]);
    const loadProjects = async ()=>{
        try {
            const data = await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["projectAPI"].list();
            setProjects(data);
            // 自动选择第一个项目
            if (data.length > 0 && !currentProject) {
                setCurrentProject(data[0]);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : "加载项目失败");
        } finally{
            setLoading(false);
        }
    };
    const loadFields = async (projectId)=>{
        try {
            const data = await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["fieldAPI"].listByProject(projectId);
            setFields(data);
        } catch (err) {
            console.error("加载字段失败:", err);
        }
    };
    const handlePhaseClick = (phase)=>{
        if (currentProject) {
            setCurrentProject({
                ...currentProject,
                current_phase: phase
            });
        }
    };
    const handlePhaseReorder = async (newPhaseOrder)=>{
        if (!currentProject) return;
        try {
            // 更新本地状态
            setCurrentProject({
                ...currentProject,
                phase_order: newPhaseOrder
            });
            // 保存到服务器
            await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["projectAPI"].update(currentProject.id, {
                phase_order: newPhaseOrder
            });
        } catch (err) {
            console.error("更新阶段顺序失败:", err);
        }
    };
    const handleAutonomyChange = async (autonomy)=>{
        if (!currentProject) return;
        try {
            // 更新本地状态
            setCurrentProject({
                ...currentProject,
                agent_autonomy: autonomy
            });
            // 保存到服务器
            await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["projectAPI"].update(currentProject.id, {
                agent_autonomy: autonomy
            });
        } catch (err) {
            console.error("更新自主权设置失败:", err);
        }
    };
    const handleFieldUpdate = async (fieldId, content)=>{
        try {
            await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["fieldAPI"].update(fieldId, {
                content
            });
            // 重新加载字段
            if (currentProject) {
                loadFields(currentProject.id);
            }
        } catch (err) {
            console.error("更新字段失败:", err);
        }
    };
    const handleSendMessage = async (message)=>{
        if (!currentProject) {
            throw new Error("请先选择项目");
        }
        const response = await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["agentAPI"].chat(currentProject.id, message, currentProject.current_phase);
        // 更新项目状态
        if (response.phase_status) {
            setCurrentProject({
                ...currentProject,
                phase_status: response.phase_status
            });
        }
        // 重新加载字段
        loadFields(currentProject.id);
        return response.message;
    };
    const handleCreateProject = async ()=>{
        const name = prompt("请输入项目名称:");
        if (!name) return;
        try {
            const project = await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["projectAPI"].create({
                name
            });
            setProjects([
                ...projects,
                project
            ]);
            setCurrentProject(project);
        } catch (err) {
            alert("创建项目失败: " + (err instanceof Error ? err.message : "未知错误"));
        }
    };
    if (loading) {
        return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
            className: "flex items-center justify-center h-screen bg-surface-0",
            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "text-zinc-400",
                children: "加载中..."
            }, void 0, false, {
                fileName: "[project]/app/workspace/page.tsx",
                lineNumber: 155,
                columnNumber: 9
            }, this)
        }, void 0, false, {
            fileName: "[project]/app/workspace/page.tsx",
            lineNumber: 154,
            columnNumber: 7
        }, this);
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "h-screen flex flex-col",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                className: "h-14 flex-shrink-0 border-b border-surface-3 bg-surface-1 flex items-center justify-between px-4",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "flex items-center gap-4",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h1", {
                                className: "text-lg font-semibold bg-gradient-to-r from-brand-400 to-brand-600 bg-clip-text text-transparent",
                                children: "内容生产系统"
                            }, void 0, false, {
                                fileName: "[project]/app/workspace/page.tsx",
                                lineNumber: 165,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                value: currentProject?.id || "",
                                onChange: (e)=>{
                                    const project = projects.find((p)=>p.id === e.target.value);
                                    setCurrentProject(project || null);
                                },
                                className: "px-3 py-1.5 bg-surface-2 border border-surface-3 rounded-lg text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                        value: "",
                                        children: "选择项目"
                                    }, void 0, false, {
                                        fileName: "[project]/app/workspace/page.tsx",
                                        lineNumber: 178,
                                        columnNumber: 13
                                    }, this),
                                    projects.map((p)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                            value: p.id,
                                            children: [
                                                p.name,
                                                " (v",
                                                p.version,
                                                ")"
                                            ]
                                        }, p.id, true, {
                                            fileName: "[project]/app/workspace/page.tsx",
                                            lineNumber: 180,
                                            columnNumber: 15
                                        }, this))
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/workspace/page.tsx",
                                lineNumber: 170,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                onClick: handleCreateProject,
                                className: "px-3 py-1.5 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors",
                                children: "+ 新建项目"
                            }, void 0, false, {
                                fileName: "[project]/app/workspace/page.tsx",
                                lineNumber: 186,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/workspace/page.tsx",
                        lineNumber: 164,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "flex items-center gap-4",
                        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("a", {
                            href: "/settings",
                            className: "text-sm text-zinc-400 hover:text-zinc-200 transition-colors",
                            children: "后台设置"
                        }, void 0, false, {
                            fileName: "[project]/app/workspace/page.tsx",
                            lineNumber: 195,
                            columnNumber: 11
                        }, this)
                    }, void 0, false, {
                        fileName: "[project]/app/workspace/page.tsx",
                        lineNumber: 194,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/workspace/page.tsx",
                lineNumber: 163,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "flex-1 overflow-hidden",
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$components$2f$layout$2f$workspace$2d$layout$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["WorkspaceLayout"], {
                    leftPanel: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$components$2f$progress$2d$panel$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["ProgressPanel"], {
                        project: currentProject,
                        onPhaseClick: handlePhaseClick,
                        onPhaseReorder: handlePhaseReorder,
                        onAutonomyChange: handleAutonomyChange
                    }, void 0, false, {
                        fileName: "[project]/app/workspace/page.tsx",
                        lineNumber: 208,
                        columnNumber: 13
                    }, void 0),
                    centerPanel: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$components$2f$content$2d$panel$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["ContentPanel"], {
                        projectId: currentProject?.id || null,
                        currentPhase: currentProject?.current_phase || "intent",
                        fields: fields,
                        onFieldUpdate: handleFieldUpdate,
                        onFieldsChange: ()=>currentProject && loadFields(currentProject.id)
                    }, void 0, false, {
                        fileName: "[project]/app/workspace/page.tsx",
                        lineNumber: 216,
                        columnNumber: 13
                    }, void 0),
                    rightPanel: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$components$2f$agent$2d$panel$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["AgentPanel"], {
                        projectId: currentProject?.id || null,
                        fields: fields,
                        onSendMessage: handleSendMessage
                    }, void 0, false, {
                        fileName: "[project]/app/workspace/page.tsx",
                        lineNumber: 225,
                        columnNumber: 13
                    }, void 0)
                }, void 0, false, {
                    fileName: "[project]/app/workspace/page.tsx",
                    lineNumber: 206,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/app/workspace/page.tsx",
                lineNumber: 205,
                columnNumber: 7
            }, this),
            error && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "fixed bottom-4 right-4 px-4 py-2 bg-red-600 text-white rounded-lg",
                children: [
                    error,
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        onClick: ()=>setError(null),
                        className: "ml-2 text-red-200 hover:text-white",
                        children: "✕"
                    }, void 0, false, {
                        fileName: "[project]/app/workspace/page.tsx",
                        lineNumber: 238,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/workspace/page.tsx",
                lineNumber: 236,
                columnNumber: 9
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/workspace/page.tsx",
        lineNumber: 161,
        columnNumber: 5
    }, this);
}
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__2fdb166f._.js.map