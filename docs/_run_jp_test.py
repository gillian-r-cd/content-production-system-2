#!/usr/bin/env python3
"""
日语本地化 - 多模型并行翻译测试 & 对比报告生成

用法:
    python3 docs/_run_jp_test.py

设计思路 (第一性原理):
    1. 核心问题: "中文控制层 + 日语内容层" 的混合 prompt 下，LLM 能否产出高质量日语翻译？
    2. 测试方法: 同一任务 × 3 个模型 (Claude / GPT / Gemini)，并行调用，侧重:
       - 翻译质量 (自然度、简洁度)
       - UTJ 风格指南遵守度 (4条规则)
       - 术语一致性 (术语表遵守)
       - 格式合规性 (全角/半角数字)
    3. 输出: docs/data/jp_comparison_<timestamp>.md — 完整的 side-by-side 对比
"""

import asyncio
import sys
import os
import io
import time
import traceback

# ── Path Setup ──
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_SCRIPT_DIR, "..", "backend")
sys.path.insert(0, _BACKEND_DIR)

# 切换到 backend/ 目录，确保 pydantic-settings 能找到 .env
os.chdir(_BACKEND_DIR)

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from langchain_core.messages import SystemMessage, HumanMessage

# ====================================================================
# 测试配置
# ====================================================================

MODELS = [
    "claude-opus-4-6",
    "gpt-5.1",
    "gemini-3.1-pro-preview",
]

TEMPERATURE = 0.7

# ====================================================================
# UTJ スタイルガイド + 術語表 (共通 system prompt)
# ====================================================================

STYLE_GUIDE = r"""# あなたの役割
あなたはUMU JAPANチーム(UTJ)の専属翻訳者です。以下の「翻訳スタイルガイド」と「術語表」に**100%準拠**して、中国語のビジネス研修コンテンツを自然で洗練された日本語に翻訳してください。

---

# 翻訳スタイルガイド

【1. 数字と記号のフォーマット規則（必須）】
- 半角：数量、日付、番号、ページ数、英語とセットの数字（例: 10個、2025年、Ver 2.0）
- 全角：言葉の一部となっている数字（例: ステップ１、 第１章）

【2. プロジェクト固有の語尾ルール（必須）】
- 「制約」の文末は必ず「〜てください」で統一する。

【3. UTJチームの翻訳スタイル：過去の修正事例に学ぶ（Style Guide）】
以下のNG（AI直訳）とOK（UTJ定稿）の比較を熟読し、UTJチームが好む「自然で洗練された日本のビジネス表現」を完全に模倣してください。

* ルール1：冗長な説明を避け、短く的確な表現（体言止め等）を好む
中国語の長い修飾語や状況説明をそのまま訳さず、日本語としてスッキリとした表現に意訳してください。
- 🇨🇳原文：到了下班时
- ❌NG(初稿)：いざ退勤時間になってみると
- ✅OK(定稿)：気づけば定時。
- 🇨🇳原文：能动性的计划不足...
- ❌NG(初稿)：能動的な計画が不足しているために、逆に
- ✅OK(定稿)：計画不足により

* ルール2：ビジネスシーンに相応しい「慣用句（イディオム）」の活用
直訳的な表現を避け、日本のビジネスパーソンが日常的に使う自然な言い回しに変換してください。
- 🇨🇳原文：不仅仅是停留在计划上，而是切实执行
- ❌NG(初稿)：物事が単に計画されるだけでなく、確実に実行される
- ✅OK(定稿)：計画が絵に描いた餅にならず、確実に実行される
- 🇨🇳原文：才真正想清楚了某个方法该怎么用
- ❌NG(初稿)：どう使うべきかが本当の意味でわかった
- ✅OK(定稿)：具体的な活用イメージが湧き、初めて腹落ちした

* ルール3：抽象的な概念の具体化と、文脈に合った単語の選択
直訳では意味が通じにくい言葉は補足を入れ、職場環境に合わない単語は適切なビジネス用語に置き換えてください。
- 🇨🇳原文：帮你想果断地做减法
- ❌NG(初稿)：思い切って「引き算」を行い
- ✅OK(定稿)：思い切って「引き算」、つまりやらない決断をして
- 🇨🇳原文：幸福感
- ❌NG(初稿)：幸福感
- ✅OK(定稿)：充実感（※仕事の文脈では幸福感より充実感が適切）
- 🇨🇳原文：随机的、被动的
- ❌NG(初稿)：ランダムで受動的なもの
- ✅OK(定稿)：無計画で受動的なもの

* ルール4：大げさな表現を避け、より直接的で自然な動詞を使う
- 🇨🇳原文：大脑很容易过载
- ❌NG(初稿)：脳は簡単にオーバーロードを起こし
- ✅OK(定稿)：脳は簡単にパンクしてしまい
- 🇨🇳原文：心理动机
- ❌NG(初稿)：心理的動機を深く掘り下げ
- ✅OK(定稿)：心理的メカニズムを理解した上で

【4. 最新術語表（必ず準拠）】
干系人 -> ステークホルダー
提示词 -> プロンプト
RSTCC 提示词框架 -> RSTCCプロンプトフレームワーク
角色 -> 役割
技能 -> スキル
任务 -> タスク
上下文背景 -> 文脈
限制规则 -> 制約
AI 力练习 -> AIプロンプト演習
小节 -> セッション
双环学习 -> ダブルループ学習
单环学习 -> シングルループ学習
大模型 -> LLM
项目管理 -> プロジェクトマネジメント
项目经理 -> プロジェクトマネージャー
信任并验证 -> 信頼と検証

---

# 出力ルール
- 翻訳結果のみを出力してください。挨拶・説明・メタコメントは不要です。
- 原文のMarkdownフォーマット（見出し、段落区切り）を維持してください。
"""

# ====================================================================
# 中文原文 (代表性抜粋 — コースの冒頭 + 核心コンセプト + 案例 の3部分)
# ====================================================================

CHINESE_SOURCE = """你好，欢迎你来到《如何应对多任务工作的挑战》这门课程。

今天的工作中，你会发现自己经常要同时处理很多事情。比如你正在写一份报告，突然收到一条必须要回的消息；或者你正在开会，却还要想着待会儿要提交的报表。这种"多任务工作"的状态，已经成为我们大多数人的日常常态。面对各种突发的、并行的任务，我们很容易感到手忙脚乱，不知道该先做哪个。今天，你将学习一种行之有效的时间管理方法，帮助你在这种复杂的多任务环境中，依然能保持清醒，找到平衡，从容应对。

在课程的开始，请你想象一个场景。你面前有一个空杯子和许多大小不一的石头、沙子和水。请你来思考一下，要想让这些东西全都能装进杯子里，要按照什么顺序来放呢？

你一定能想到：最合理的方式是先放大石头，再放小石头，然后是沙子，最后倒入水。这样才能最大限度地利用杯子的空间。

这个比喻非常恰当地揭示了时间管理的核心原则。在日常工作中，你的任务就像这些石头、沙子和水。"大石头"代表最重要的任务，"小石头"是次要任务，"沙子"和"水"则是一些琐碎的事情。如果你一开始就让沙子、水和小石头占据了杯子的大部分空间，那么大石头就很难再放进去了。同样的道理，如果你在工作中被琐事和不重要的任务占据了大部分时间，真正重要的任务就会被挤到一边，甚至被忽略。

那么你可能会说：理念我已经理解了，那具体要怎么做呢？具体来说有三个主要步骤，非常清晰、很容易上手。

首先，你需要明确自己目前承担的关键角色。每个人在工作和生活中都不仅仅是一个身份。比如，你可能既是"某个具体业务的执行者"，又是"团队协作中的支持者"，甚至还是"自我成长的负责人"。

找出这些角色后，更重要的一步是：定义每个角色的成功标准。问问自己："在这个角色上，我要达成什么结果才算成功？"如果不清楚这一点，你就很难判断哪些任务是真正重要的。

明确了角色的成功标准后，接下来就是以"周"为单位，思考：为了达成这个角色的成功，本周我必须做完哪三件最重要的事？这三件事，就是你的"大石头"。

在这里，你要特别注意及时与直属领导和干系人对齐你的大石头。因为你挑选出的"大石头"未必准确。因此，在这个过程中，一定要和你的直属领导对齐。你可以主动找领导沟通三件事：

首先是对齐优先级。确认你手头事情的排序是否正确。一旦确认了第一优先级，就要敢于坚持，对于干扰核心任务的其他琐事，要学会适度地说"不"。

第二件事是验证大石头与目标是否关联。确认你选的这些大石头，是否真的有助于实现团队的目标？这能防止你方向跑偏。

第三件事是明确直属领导对你的期望。询问领导对这几块大石头有什么具体的交付期望？做成什么样才算好？

只有经过了和领导的对齐，你的"忙碌"才是有价值的。"""

# ====================================================================
# User Message (发给每个模型的翻译指令)
# ====================================================================

USER_MESSAGE = """以下の中国語テキストを、翻訳スタイルガイドと術語表に100%準拠して日本語に翻訳してください。

---

""" + CHINESE_SOURCE


# ====================================================================
# 并行测试引擎
# ====================================================================

async def call_model(model_name: str) -> dict:
    """调用单个模型并返回结果。"""
    from core.llm import get_chat_model, parse_llm_error
    from core.llm_compat import normalize_content

    result = {
        "model": model_name,
        "content": "",
        "elapsed": 0.0,
        "error": None,
        "char_count": 0,
    }

    try:
        llm = get_chat_model(
            model=model_name,
            temperature=TEMPERATURE,
            streaming=True,
        )

        messages = [
            SystemMessage(content=STYLE_GUIDE),
            HumanMessage(content=USER_MESSAGE),
        ]

        print(f"  📤 [{model_name}] 发送请求...")
        start = time.time()
        chunks = []

        async for chunk in llm.astream(messages):
            # normalize_content 处理 Gemini 返回 list 的情况
            token = normalize_content(chunk.content) if chunk.content else ""
            if token:
                chunks.append(token)

        result["content"] = "".join(chunks)
        result["elapsed"] = time.time() - start
        result["char_count"] = len(result["content"])
        print(f"  ✅ [{model_name}] 完成 — {result['elapsed']:.1f}s, {result['char_count']} chars")

    except Exception as e:
        result["elapsed"] = time.time() - start if 'start' in dir() else 0
        try:
            result["error"] = parse_llm_error(e)
        except Exception:
            result["error"] = str(e)
        print(f"  ❌ [{model_name}] 失败: {result['error']}")
        traceback.print_exc()

    return result


async def run_parallel_tests() -> list[dict]:
    """并行调用所有模型。"""
    print(f"\n{'=' * 70}")
    print(f"🧪 日语本地化 — 多模型并行翻译测试")
    print(f"   模型: {', '.join(MODELS)}")
    print(f"   温度: {TEMPERATURE}")
    print(f"   原文: {len(CHINESE_SOURCE)} chars")
    print(f"   Style Guide: {len(STYLE_GUIDE)} chars")
    print(f"{'=' * 70}\n")

    tasks = [call_model(m) for m in MODELS]
    results = await asyncio.gather(*tasks)
    return list(results)


def generate_report(results: list[dict]) -> str:
    """生成 Markdown 对比报告。"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append("# 🇯🇵 日语本地化 — 多模型翻译对比报告\n")
    lines.append(f"**生成时间**: {ts}  ")
    lines.append(f"**温度**: {TEMPERATURE}  ")
    lines.append(f"**原文长度**: {len(CHINESE_SOURCE)} chars\n")

    # ── 摘要表格 ──
    lines.append("## 📊 测试摘要\n")
    lines.append("| 模型 | 耗时 | 输出字数 | 状态 |")
    lines.append("|------|------|----------|------|")
    for r in results:
        status = "✅ 成功" if not r["error"] else f"❌ {r['error'][:30]}"
        lines.append(f"| {r['model']} | {r['elapsed']:.1f}s | {r['char_count']} | {status} |")
    lines.append("")

    # ── 中文原文 ──
    lines.append("---\n")
    lines.append("## 📄 中文原文\n")
    lines.append("<details>")
    lines.append("<summary>点击展开原文（折叠）</summary>\n")
    lines.append(CHINESE_SOURCE)
    lines.append("\n</details>\n")

    # ── UTJ スタイルガイド摘要 ──
    lines.append("---\n")
    lines.append("## 📋 UTJ スタイルガイド（摘要）\n")
    lines.append("| ルール | 内容 |")
    lines.append("|--------|------|")
    lines.append("| ルール1 | 冗長な説明を避け、短く的確な表現（体言止め等）を好む |")
    lines.append("| ルール2 | ビジネスシーンに相応しい「慣用句」の活用 |")
    lines.append("| ルール3 | 抽象的な概念の具体化と、文脈に合った単語の選択 |")
    lines.append("| ルール4 | 大げさな表現を避け、より直接的で自然な動詞を使う |")
    lines.append("| 数字 | 半角: 数量・日付 / 全角: 言葉の一部 |")
    lines.append("| 術語 | 干系人→ステークホルダー, 提示词→プロンプト 等 |")
    lines.append("")

    # ── 各模型翻訳結果 ──
    lines.append("---\n")
    lines.append("## 🔍 翻訳結果の比較\n")

    for r in results:
        lines.append(f"### 📝 {r['model']}\n")
        lines.append(f"- **耗时**: {r['elapsed']:.1f}s")
        lines.append(f"- **字数**: {r['char_count']} chars\n")
        if r["error"]:
            lines.append(f"> ❌ エラー: {r['error']}\n")
        else:
            lines.append(r["content"])
        lines.append("\n---\n")

    # ── 质量检查点 (给日语同事的 review checklist) ──
    lines.append("## ✅ 品質チェックリスト（レビュー用）\n")
    lines.append("各翻訳結果を以下の観点で評価してください：\n")
    lines.append("| # | チェック項目 | 説明 |")
    lines.append("|---|------------|------|")
    lines.append("| 1 | **術語の一致** | 「干系人→ステークホルダー」等、術語表どおりか？ |")
    lines.append("| 2 | **数字フォーマット** | 半角/全角が規則どおりか？(例: 3つ=半角, 第１=全角) |")
    lines.append("| 3 | **簡潔さ (ルール1)** | 冗長な説明がなく、体言止め等でスッキリしているか？ |")
    lines.append("| 4 | **慣用句 (ルール2)** | ビジネスシーンに合った自然な言い回しか？ |")
    lines.append("| 5 | **具体化 (ルール3)** | 抽象的な言葉が具体化されているか？ |")
    lines.append("| 6 | **自然さ (ルール4)** | 大げさな表現がなく、直接的で自然な動詞か？ |")
    lines.append("| 7 | **全体の読みやすさ** | 日本のビジネスパーソンが違和感なく読めるか？ |")
    lines.append("| 8 | **フォーマット保持** | 段落区切り・構成が原文と一致しているか？ |")
    lines.append("")

    lines.append("### 評価テンプレート\n")
    lines.append("```")
    lines.append("モデル名: ___________")
    lines.append("総合評価: ⭐⭐⭐⭐⭐ (5段階)")
    lines.append("術語一致: ○ / △ / ×")
    lines.append("簡潔さ:   ○ / △ / ×")
    lines.append("自然さ:   ○ / △ / ×")
    lines.append("コメント: ")
    lines.append("```\n")

    return "\n".join(lines)


async def cross_evaluate(results: list[dict]) -> str:
    """
    用 Claude 对三个翻译结果进行交叉评估。
    返回 AI 的评估结论（日语），可直接嵌入报告。
    """
    from core.llm import get_chat_model
    from core.llm_compat import normalize_content

    # 只评估成功的结果
    valid = [r for r in results if not r["error"]]
    if len(valid) < 2:
        return "(评估跳过：成功的翻译结果不足2个)"

    eval_prompt = """あなたはUMU JAPANチーム(UTJ)の翻訳品質レビュアーです。
以下の翻訳結果を、UTJスタイルガイドの基準で比較評価してください。

【評価基準】
1. 術語一致: 干系人→ステークホルダー 等、術語表どおりか
2. 数字フォーマット: 半角/全角が規則どおりか
3. 簡潔さ (ルール1): 体言止め等で冗長さを排除しているか
4. 慣用句 (ルール2): 自然なビジネス表現が使われているか
5. 具体化 (ルール3): 抽象表現が具体化されているか
6. 自然さ (ルール4): 大げさでなく直接的な表現か

【出力フォーマット】
各モデルについて以下の形式で評価してください：

#### [モデル名]
- 術語一致: ○/△/× — 具体的な指摘
- 数字フォーマット: ○/△/× — 具体的な指摘
- 簡潔さ: ○/△/× — 具体的な指摘
- 慣用句: ○/△/× — 具体的な指摘
- 具体化: ○/△/× — 具体的な指摘
- 自然さ: ○/△/× — 具体的な指摘
- **総合評価**: ⭐⭐⭐⭐⭐ (5段階)

最後に「### 総合所見」として、どのモデルが最もUTJ基準に合致しているか、改善点は何かを簡潔にまとめてください。
"""

    translations_section = ""
    for r in valid:
        translations_section += f"\n---\n## {r['model']} の翻訳結果\n\n{r['content']}\n"

    eval_llm = get_chat_model(model="claude-opus-4-6", temperature=0.2, streaming=True)
    messages = [
        SystemMessage(content=eval_prompt),
        HumanMessage(content=translations_section),
    ]

    print("  📤 [交叉评估] Claude 正在评审三个翻译...")
    start = time.time()
    chunks = []
    async for chunk in eval_llm.astream(messages):
        token = normalize_content(chunk.content) if chunk.content else ""
        if token:
            chunks.append(token)

    result = "".join(chunks)
    elapsed = time.time() - start
    print(f"  ✅ [交叉评估] 完成 — {elapsed:.1f}s, {len(result)} chars")
    return result


async def main():
    # ── 1. 并行测试 ──
    results = await run_parallel_tests()

    # ── 2. 在终端预览每个模型的前 300 字 ──
    print(f"\n{'=' * 70}")
    print("📋 各模型输出预览 (前300字)")
    print(f"{'=' * 70}")
    for r in results:
        print(f"\n--- {r['model']} ---")
        if r["error"]:
            print(f"  ❌ {r['error']}")
        else:
            preview = r["content"][:300].replace("\n", "\n  ")
            print(f"  {preview}...")
    print()

    # ── 3. AI 交叉评估 ──
    print(f"{'=' * 70}")
    print("🔬 AI 交叉评估 (Claude 作为评审)")
    print(f"{'=' * 70}")
    eval_result = await cross_evaluate(results)

    # ── 4. 生成报告 ──
    report = generate_report(results)

    # 在报告末尾插入 AI 评估结果
    report += "\n---\n\n"
    report += "## 🤖 AI 交叉評価（Claude による自動レビュー）\n\n"
    report += eval_result
    report += "\n"

    data_dir = os.path.join(_SCRIPT_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(data_dir, f"jp_comparison_{timestamp}.md")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n💾 对比报告已保存: {filepath}")
    print(f"   共 {len(report)} chars, 可直接发给日语同事 review")

    # ── 5. 返回路径供外部使用 ──
    return filepath


if __name__ == "__main__":
    asyncio.run(main())
