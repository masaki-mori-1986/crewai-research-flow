# crewai-research-flow

CrewAI ベースの情報収集マルチエージェント — **Flow-first** 設計の最小骨格。

計画生成（Planner）→ 評価（Reviewer）→ Flow による判定・フィードバック・再実行のループを構成します。Planner は自由文ではなく、後続実行に使いやすい構造化 Plan を生成します。

---

## アーキテクチャ

```
UserRequest
    │
    ▼
┌─────────────────────────────────────────┐
│  ResearchFlow（制御主体）               │
│                                         │
│  ┌──────────┐    ┌──────────────────┐  │
│  │ Planner  │───▶│   PlanningTask   │  │
│  └──────────┘    └────────┬─────────┘  │
│                           │ Plan       │
│  ┌──────────┐    ┌────────▼─────────┐  │
│  │ Reviewer │───▶│   ReviewTask     │  │
│  └──────────┘    └────────┬─────────┘  │
│                           │ Review     │
│                   ┌───────▼──────────┐ │
│                   │  evaluate()      │ │
│                   │  判定・分岐      │ │
│                   └───────┬──────────┘ │
│              ┌────────────┴──────────┐ │
│         accepted        needs_improvement│
│              │                │        │
│         FlowResult      Feedback生成   │
│                               │        │
│                          re-planning   │
└─────────────────────────────────────────┘
```

### 責務分離

| コンポーネント | 責務 |
|---|---|
| `Planner` Agent | 構造化された計画 JSON の生成のみ |
| `Reviewer` Agent | 計画の評価と改善要求の生成のみ |
| `PlanningTask` | Planner の入出力契約定義 |
| `ReviewTask` | Reviewer の入出力契約定義（評価観点を保持） |
| `ResearchFlow` | 状態管理・判定・再実行制御・終了制御 |

### 評価観点

Reviewer は以下の3観点で計画を評価します。

- **具体性** — 各ステップが誰でも実行できる具体的な内容か
- **網羅性** — 要求で求められた調査範囲が過不足なくカバーされているか
- **実行可能性** — 現実的に実行できる内容か

---

## 前提

- [uv](https://docs.astral.sh/uv/) がインストール済みであること
- [Ollama](https://ollama.com/) が起動済みで `qwen2.5:7b` が利用可能であること

```bash
ollama pull qwen2.5:7b
ollama serve
```

---

## セットアップ

```bash
# リポジトリをクローン
git clone https://github.com/<your-username>/crewai-research-flow.git
cd crewai-research-flow

# 依存関係をインストール
uv sync
uv pip install -e .

# 環境変数を設定（デフォルトのまま動作します）
cp .env.example .env
```

### `.env` の設定項目

```
# Ollama 接続設定（デフォルト値で動作）
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=ollama/qwen2.5:7b
```

---

## 実行

```bash
# デフォルトの要求で実行
uv run python main.py

# 要求を指定して実行
uv run python main.py "生成AIが製造業に与える影響について調査してほしい"
```

### 実行フロー

1. Planner が構造化された情報収集計画を生成
2. Reviewer が計画を評価（具体性・網羅性・実行可能性）
3. Flow が評価結果を判定
   - `accepted` → 終了（FlowResult を返す）
   - `needs_improvement` → Feedback を生成して Planner に再入力
4. 試行上限（デフォルト: 3回）に達した場合は未達で終了

### Plan の構造

Planner は以下のような構造を持つ Plan を JSON として出力し、Flow はこれをパースして保持します。

- `objective`
- `scope`
- `key_questions`
- `topics[]`
- `steps[]`
- `deliverable_format`

---

## プロジェクト構成

```
src/first_multi_agent/
├── config.py           # LLM 設定の一元管理
├── models.py           # 契約定義（Plan / Review / Feedback / FlowResult）
├── agents/
│   ├── planner.py      # Planner Agent
│   └── reviewer.py     # Reviewer Agent
├── tasks/
│   ├── planning_task.py  # PlanningTask
│   └── review_task.py    # ReviewTask
├── flow/
│   └── research_flow.py  # ResearchFlow（Flow 制御主体）
└── main.py             # エントリポイント
```

---

## 今後の拡張予定（スコープ外）

- Researcher / Analyst / Writer Agent の追加
- 外部ツール連携（Web検索など）
- Human-in-the-loop
- 評価スコアリングの詳細化
