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
from typing import Any, Optional

from crewai import Crew
from crewai.flow.flow import Flow, listen, start
from json_repair import repair_json

from first_multi_agent.agents.planner import build_planner
from first_multi_agent.agents.reviewer import build_reviewer
from first_multi_agent.models import (
    Feedback,
    FlowResult,
    ImprovementRequest,
    Plan,
    PlanStep,
    PlanTopic,
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
    current_plan_raw: str = ""
    current_plan_structured: Optional[Plan] = None
    approved_plan: Optional[Plan] = None
    latest_plan_error: Optional[str] = None
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

        plan_raw = str(result.raw) if hasattr(result, "raw") else str(result)
        self.state.current_plan_raw = plan_raw
        self.state.latest_plan_error = None
        try:
            plan = self._parse_plan(plan_raw)
        except ValueError as e:
            self.state.current_plan_structured = None
            self.state.latest_plan_error = str(e)
            print(f"[Flow] WARNING: {e}")
            return self._render_plan_parse_failure(plan_raw, str(e))

        self.state.current_plan_structured = plan

        rendered_plan = self.render_plan(plan)
        print(f"[Flow] Plan generated ({len(plan_raw)} chars raw)")
        return rendered_plan

    # -----------------------------------------------------------------------
    # Step 2: ReviewTask 実行
    # -----------------------------------------------------------------------

    @listen(run_planning)
    def run_review(self, plan_text: str) -> Optional[Review]:
        print(f"[Flow] ▶ Reviewing plan (attempt {self.state.attempts})")

        if self.state.current_plan_structured is None:
            review = self._build_plan_parse_failure_review()
            self.state.latest_review = review
            print(
                "[Flow] Skipped reviewer because planner output did not match the "
                "Plan schema."
            )
            return review

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
            self.state.approved_plan = self.state.current_plan_structured
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

    @staticmethod
    def render_plan(plan: Plan) -> str:
        """構造化された Plan をレビューしやすい文字列表現に変換する。"""
        lines = [
            f"Objective: {plan.objective}",
            f"Scope: {plan.scope}",
            "",
            "Key Questions:",
        ]
        if plan.key_questions:
            lines.extend(f"- {question}" for question in plan.key_questions)
        else:
            lines.append("- (none)")

        lines.extend(["", "Topics:"])
        if plan.topics:
            for topic in plan.topics:
                lines.append(f"- {topic.name}")
                if topic.questions:
                    lines.append("  Questions:")
                    lines.extend(f"  - {question}" for question in topic.questions)
                if topic.information_to_collect:
                    lines.append("  Information to collect:")
                    lines.extend(
                        f"  - {item}" for item in topic.information_to_collect
                    )
        else:
            lines.append("- (none)")

        lines.extend(["", "Steps:"])
        if plan.steps:
            for step in sorted(plan.steps, key=lambda item: item.step_number):
                lines.append(
                    f"{step.step_number}. Action: {step.action}"
                )
                lines.append(f"   Method: {step.method}")
                lines.append(f"   Expected Output: {step.expected_output}")
        else:
            lines.append("- (none)")

        lines.extend(["", f"Deliverable Format: {plan.deliverable_format}"])
        return "\n".join(lines)

    def _parse_json_block(self, raw: str, label: str) -> dict:
        """LLM 出力から JSON オブジェクトを抽出して辞書化する。"""
        start_idx = raw.find("{")
        end_idx = raw.rfind("}")
        if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
            raise ValueError(f"No JSON found in {label} output")

        json_block = raw[start_idx : end_idx + 1]
        try:
            return json.loads(json_block)
        except json.JSONDecodeError:
            return json.loads(repair_json(json_block))

    def _parse_plan(self, raw: str) -> Plan:
        """PlanningTask の出力を Plan モデルにパースする。"""
        try:
            data = self._parse_json_block(raw, label="plan")
            data = self._normalize_plan_payload(data)
            self._validate_required_plan_fields(data)
            topics = [PlanTopic(**topic) for topic in data.get("topics", [])]
            steps = [PlanStep(**step) for step in data.get("steps", [])]
            return Plan(
                objective=data["objective"],
                scope=data["scope"],
                key_questions=data.get("key_questions", []),
                topics=topics,
                steps=steps,
                deliverable_format=data["deliverable_format"],
            )
        except Exception as e:
            raise ValueError(f"Failed to parse structured plan: {e}") from e

    def _normalize_plan_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        """LLM が崩した Plan JSON を最小限だけ正規化する。"""
        if not isinstance(data, dict):
            raise ValueError("Plan payload must be a JSON object")

        data = dict(data)
        data["objective"] = self._coerce_required_string(
            data.get("objective"),
            field_name="objective",
        )
        data["scope"] = self._coerce_required_string(
            data.get("scope"),
            field_name="scope",
        )
        data["key_questions"] = self._coerce_string_list(
            data.get("key_questions", []),
            field_name="key_questions",
        )

        normalized_topics = []
        lifted_steps = []
        for index, topic in enumerate(data.get("topics", [])):
            if not isinstance(topic, dict):
                raise ValueError(f"topics[{index}] must be an object")

            normalized_topic = dict(topic)
            normalized_topic["questions"] = self._coerce_string_list(
                normalized_topic.get("questions", []),
                field_name=f"topics[{index}].questions",
            )
            info_items, discovered_steps = self._extract_topic_information(
                normalized_topic.get("information_to_collect", []),
                field_name=f"topics[{index}].information_to_collect",
            )
            normalized_topic["information_to_collect"] = info_items
            normalized_topics.append(normalized_topic)
            lifted_steps.extend(discovered_steps)

        data["topics"] = normalized_topics

        if data.get("steps") in (None, []):
            data["steps"] = lifted_steps
        elif lifted_steps:
            print(
                "[Flow] WARNING: Ignored step-like data embedded in "
                "topics[*].information_to_collect because top-level steps already exist."
            )

        data["deliverable_format"] = self._extract_deliverable_format(data)
        return data

    def _validate_required_plan_fields(self, data: dict[str, Any]) -> None:
        """Plan として最低限必要な項目の有無を確認する。"""
        missing_fields = [
            field_name
            for field_name in ("objective", "scope", "deliverable_format")
            if not isinstance(data.get(field_name), str) or not data[field_name].strip()
        ]
        if missing_fields:
            raise ValueError(
                "Missing required plan field(s): " + ", ".join(missing_fields)
            )

    def _coerce_required_string(self, value: Any, field_name: str) -> Optional[str]:
        """必須文字列候補を整形する。"""
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a string")

        normalized = value.strip()
        return normalized or None

    def _coerce_string_list(self, value: Any, field_name: str) -> list[str]:
        """list[str] を期待する項目を厳密に整形する。"""
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"{field_name} must be a list")

        items = []
        for index, item in enumerate(value):
            if not isinstance(item, str):
                raise ValueError(
                    f"{field_name}[{index}] must be a string, got {type(item).__name__}"
                )
            items.append(item)
        return items

    def _extract_topic_information(
        self,
        value: Any,
        field_name: str,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """
        information_to_collect を整形し、誤って埋め込まれた steps を回収する。
        """
        if value is None:
            return [], []
        if not isinstance(value, list):
            raise ValueError(f"{field_name} must be a list")

        info_items = []
        lifted_steps = []
        for index, item in enumerate(value):
            if isinstance(item, str):
                info_items.append(item)
                continue

            if self._looks_like_step_list(item):
                lifted_steps.extend(item)
                print(
                    f"[Flow] WARNING: Recovered misplaced steps from {field_name}[{index}]."
                )
                continue

            raise ValueError(
                f"{field_name}[{index}] must be a string, got {type(item).__name__}"
            )

        return info_items, lifted_steps

    def _extract_deliverable_format(self, data: dict[str, Any]) -> Optional[str]:
        """deliverable_format の別名や崩れを最小限補正する。"""
        direct_value = self._coerce_optional_string(data.get("deliverable_format"))
        if direct_value:
            return direct_value

        for alias in ("deliverable", "output_format", "final_output_format"):
            alias_value = self._coerce_optional_string(data.get(alias))
            if alias_value:
                print(
                    f"[Flow] WARNING: Using '{alias}' as deliverable_format fallback."
                )
                return alias_value

        return None

    @staticmethod
    def _coerce_optional_string(value: Any) -> Optional[str]:
        """任意文字列を strip して返す。"""
        if value is None:
            return None
        if not isinstance(value, str):
            return None

        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _looks_like_step_list(value: Any) -> bool:
        """steps 配列が誤って別フィールドに埋め込まれたケースを検出する。"""
        if not isinstance(value, list) or not value:
            return False

        required_keys = {"step_number", "action", "method", "expected_output"}
        return all(
            isinstance(item, dict) and required_keys.issubset(item.keys())
            for item in value
        )

    def _build_plan_parse_failure_review(self) -> Review:
        """Planner の schema 不整合を再計画用レビューに変換する。"""
        error_message = self.state.latest_plan_error or "Planner output schema mismatch"
        return Review(
            verdict=ReviewVerdict.NEEDS_IMPROVEMENT,
            specificity_ok=False,
            coverage_ok=False,
            feasibility_ok=False,
            improvement_requests=[
                ImprovementRequest(
                    issue=f"Planner output could not be parsed: {error_message}",
                    suggestion=(
                        "Plan スキーマに厳密に従った JSON のみを再生成してください。"
                        "必須項目 objective / scope / deliverable_format を含め、"
                        "steps はトップレベル配列に置いてください。"
                    ),
                )
            ],
            summary=(
                "Planner output was not valid against the Plan schema. "
                "The flow will request a corrected plan."
            ),
        )

    def _render_plan_parse_failure(self, plan_raw: str, error_message: str) -> str:
        """レビュー・ログ用に計画パース失敗内容を整形する。"""
        return (
            "Planner output could not be parsed into the Plan schema.\n"
            f"Error: {error_message}\n\n"
            "Raw planner output:\n"
            f"{plan_raw}"
        )

    def _parse_review(self, raw: str) -> Optional[Review]:
        """ReviewTask の出力を Review モデルにパースする。失敗時は None を返す。"""
        try:
            data = self._parse_json_block(raw, label="review")

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
        current_plan = self.state.current_plan_structured
        if current_plan is not None:
            current_plan_text = self.render_plan(current_plan)
        elif self.state.latest_plan_error:
            current_plan_text = self._render_plan_parse_failure(
                self.state.current_plan_raw,
                self.state.latest_plan_error,
            )
        else:
            current_plan_text = self.state.current_plan_raw

        return Feedback(
            original_request=self.state.user_request,
            current_plan=current_plan_text,
            improvement_requests=review.improvement_requests,
        )

    def _finish(self, accepted: bool, reason: str) -> None:
        """終了処理 — FlowResult を生成してフラグを立てる。"""
        review = self.state.latest_review
        self.state.flow_result = FlowResult(
            accepted=accepted,
            final_plan=self.state.approved_plan if accepted else self.state.current_plan_structured,
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
