"""
契約定義モジュール
Plan / Review / Feedback / FlowResult の構造化契約を定義する。
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ReviewVerdict(str, Enum):
    """評価判定結果"""
    ACCEPTED = "accepted"
    NEEDS_IMPROVEMENT = "needs_improvement"


class Plan(BaseModel):
    """計画生成の出力契約"""
    content: str = Field(description="生成された計画の本文")


class ImprovementRequest(BaseModel):
    """改善要求の1単位（問題点と1対1対応）"""
    issue: str = Field(description="問題点の説明")
    suggestion: str = Field(description="Plannerがそのまま反映可能な改善指示")


class Review(BaseModel):
    """評価の出力契約"""
    verdict: ReviewVerdict = Field(description="受け入れ可否の判定")
    specificity_ok: bool = Field(description="具体性が十分か")
    coverage_ok: bool = Field(description="網羅性が十分か")
    feasibility_ok: bool = Field(description="実行可能性が十分か")
    improvement_requests: List[ImprovementRequest] = Field(
        default_factory=list,
        description="改善要求リスト（verdict が NEEDS_IMPROVEMENT の場合に設定）",
    )
    summary: str = Field(description="評価サマリ")


class Feedback(BaseModel):
    """Flow が Planner へ返すフィードバック契約"""
    original_request: str = Field(description="元のユーザ要求")
    current_plan: str = Field(description="評価対象だった計画")
    improvement_requests: List[ImprovementRequest] = Field(
        description="改善要求リスト"
    )


class FlowResult(BaseModel):
    """Flow の最終出力契約"""
    accepted: bool = Field(description="計画が受け入れられたか")
    final_plan: Optional[str] = Field(default=None, description="最終的な計画")
    attempts: int = Field(description="試行回数")
    termination_reason: str = Field(
        description="終了理由（accepted / max_attempts_reached）"
    )
    last_review_summary: Optional[str] = Field(
        default=None, description="最後の評価サマリ"
    )
