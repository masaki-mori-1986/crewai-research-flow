"""
ResearchFlow — Flow-first の制御主体。

責務:
- 状態管理（元要求 / 現在計画 / 最新評価 / 改善要求 / 試行回数 / 実行ID）
- 実行順序制御（Plan → Review → 判定 → Feedback → 再実行）
- 判定ロジック（受け入れ可否・上限到達）
- 終了制御（FlowResult の生成）

Agent / Task は出力生成のみ担い、判定・制御はここに集約する。
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from crewai import Crew
from crewai.flow.flow import Flow, listen, start
from json_repair import repair_json

from first_multi_agent.agents.planner import build_planner
from first_multi_agent.agents.reviewer import build_reviewer
from first_multi_agent.models import (
    Feedback,
    FlowResult,
    ImprovementRequest,
    Review,
    ReviewVerdict,
)
from first_multi_agent.tasks.planning_task import build_planning_task
from first_multi_agent.tasks.review_task import build_review_task
from pydantic import BaseModel, Field

MAX_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# Flow State
# ---------------------------------------------------------------------------

class ResearchFlowState(BaseModel):
    """Flow が保持する最小状態"""
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_request: str = ""
    current_plan: str = ""
    latest_review: Optional[Review] = None
    latest_feedback: Optional[Feedback] = None
    attempts: int = 0
    finished: bool = False
    flow_result: Optional[FlowResult] = None


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------

class ResearchFlow(Flow[ResearchFlowState]):
    """情報収集 Flow の最小骨格（Plan → Review → 判定 → Feedback ループ）"""

    # -----------------------------------------------------------------------
    # Step 1: PlanningTask 実行
    # -----------------------------------------------------------------------

    @start()
    def run_planning(self) -> str:
        self.state.attempts += 1
        print(
            f"\n[Flow] ▶ Planning (attempt {self.state.attempts}/{MAX_ATTEMPTS})"
            f" | execution_id={self.state.execution_id}"
        )

        planner = build_planner()
        task = build_planning_task(planner, feedback=self.state.latest_feedback)

        # user_request をタスクの入力として渡す
        crew = Crew(
            agents=[planner],
            tasks=[task],
            verbose=False,
        )
        result = crew.kickoff(
            inputs={"user_request": self.state.user_request}
        )

        plan_text = str(result.raw) if hasattr(result, "raw") else str(result)
        self.state.current_plan = plan_text
        print(f"[Flow] Plan generated ({len(plan_text)} chars)")
        return plan_text

    # -----------------------------------------------------------------------
    # Step 2: ReviewTask 実行
    # -----------------------------------------------------------------------

    @listen(run_planning)
    def run_review(self, plan_text: str) -> Optional[Review]:
        print(f"[Flow] ▶ Reviewing plan (attempt {self.state.attempts})")

        reviewer = build_reviewer()
        task = build_review_task(
            reviewer,
            plan_content=plan_text,
            user_request=self.state.user_request,
        )

        crew = Crew(
            agents=[reviewer],
            tasks=[task],
            verbose=False,
        )
        result = crew.kickoff()
        raw = str(result.raw) if hasattr(result, "raw") else str(result)

        review = self._parse_review(raw)
        self.state.latest_review = review
        if review is None:
            print("[Flow] WARNING: Review parsing failed. Handing over to evaluate().")
            return None

        print(f"[Flow] Review verdict: {review.verdict} | summary: {review.summary}")
        return review

    # -----------------------------------------------------------------------
    # Step 3: 判定ロジック（Flow が担う）
    # -----------------------------------------------------------------------

    @listen(run_review)
    def evaluate(self, review: Optional[Review]) -> None:
        """
        判定ポイント — 後から拡張しやすいよう分離。
        現在の判定規則:
          - review が None: 判定情報不足 → 上限到達扱い（TODO: 将来拡張点）
          - verdict == ACCEPTED: 終了
          - verdict == NEEDS_IMPROVEMENT かつ attempts < MAX_ATTEMPTS: Feedback 生成
          - verdict == NEEDS_IMPROVEMENT かつ attempts >= MAX_ATTEMPTS: 上限到達で終了
        """
        if review is None:
            # 判定情報不足 — 現状は上限到達扱いで終了（将来の拡張点）
            self._finish(accepted=False, reason="review_parse_failed")
            return

        if review.verdict == ReviewVerdict.ACCEPTED:
            self._finish(accepted=True, reason="accepted")
            return

        if self.state.attempts >= MAX_ATTEMPTS:
            self._finish(accepted=False, reason="max_attempts_reached")
            return

        # NEEDS_IMPROVEMENT かつ再実行可能 → Feedback を生成して再実行
        feedback = self._build_feedback(review)
        self.state.latest_feedback = feedback
        print(
            f"[Flow] Feedback generated "
            f"({len(feedback.improvement_requests)} requests). Re-running."
        )
        # Flow の再起動: run_planning を再度呼ぶ
        self.run_planning()

    # -----------------------------------------------------------------------
    # 内部ヘルパー
    # -----------------------------------------------------------------------

    def _parse_review(self, raw: str) -> Optional[Review]:
        """ReviewTask の出力を Review モデルにパースする。失敗時は None を返す。"""
        try:
            # JSON 部分を抽出（コードフェンスや前後テキストを許容）
            start_idx = raw.find("{")
            end_idx = raw.rfind("}")
            if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
                raise ValueError("No JSON found in review output")

            json_block = raw[start_idx : end_idx + 1]
            try:
                data = json.loads(json_block)
            except json.JSONDecodeError:
                # ローカルLLMで崩れたJSONを最小限修復して再試行
                data = json.loads(repair_json(json_block))

            verdict_raw = str(data.get("verdict", "")).strip().lower()
            if verdict_raw not in {"accepted", "needs_improvement"}:
                raise ValueError(f"Invalid verdict: {verdict_raw}")

            requests = [
                ImprovementRequest(**r) for r in data.get("improvement_requests", [])
            ]
            return Review(
                verdict=ReviewVerdict(verdict_raw),
                specificity_ok=data.get("specificity_ok", False),
                coverage_ok=data.get("coverage_ok", False),
                feasibility_ok=data.get("feasibility_ok", False),
                improvement_requests=requests,
                summary=data.get("summary", ""),
            )
        except Exception as e:
            print(f"[Flow] WARNING: Failed to parse review output: {e}")
            return None

    def _build_feedback(self, review: Review) -> Feedback:
        """Review から Planner へのフィードバックを生成する。"""
        return Feedback(
            original_request=self.state.user_request,
            current_plan=self.state.current_plan,
            improvement_requests=review.improvement_requests,
        )

    def _finish(self, accepted: bool, reason: str) -> None:
        """終了処理 — FlowResult を生成してフラグを立てる。"""
        review = self.state.latest_review
        self.state.flow_result = FlowResult(
            accepted=accepted,
            final_plan=self.state.current_plan if accepted else self.state.current_plan,
            attempts=self.state.attempts,
            termination_reason=reason,
            last_review_summary=review.summary if review else None,
        )
        self.state.finished = True
        status = "✅ ACCEPTED" if accepted else f"⛔ {reason.upper()}"
        print(
            f"[Flow] {status} after {self.state.attempts} attempt(s). "
            f"execution_id={self.state.execution_id}"
        )
