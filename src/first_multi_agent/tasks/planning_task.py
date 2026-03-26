"""
PlanningTask — Planner の入出力契約を定義する。
初回実行とフィードバックありの再実行を同一 Task 関数で扱う。
"""
from typing import Optional

from crewai import Agent, Task

from first_multi_agent.models import Feedback


def build_planning_task(planner: Agent, feedback: Optional[Feedback] = None) -> Task:
    """
    Args:
        planner: Planner Agent
        feedback: Flowから渡されるフィードバック。None の場合は初回実行。
    """
    if feedback is None:
        description = (
            "以下の要求に対して、情報収集計画を生成してください。\n\n"
            "要求: {user_request}\n\n"
            "計画には以下を含めてください:\n"
            "- 調査対象の明確な定義\n"
            "- 具体的な調査ステップ（順序と方法）\n"
            "- 各ステップで収集する情報の種類\n"
            "- 成果物の形式"
        )
    else:
        improvement_text = "\n".join(
            f"- 問題: {r.issue}\n  改善指示: {r.suggestion}"
            for r in feedback.improvement_requests
        )
        description = (
            "以下の改善フィードバックをもとに、情報収集計画を改訂してください。\n\n"
            f"元の要求: {feedback.original_request}\n\n"
            f"前回の計画:\n{feedback.current_plan}\n\n"
            f"改善要求:\n{improvement_text}\n\n"
            "改善要求をすべて反映した計画を生成してください。"
        )

    return Task(
        description=description,
        expected_output=(
            "具体的・網羅的・実行可能な情報収集計画。"
            "計画本文をそのままテキストで出力すること。"
        ),
        agent=planner,
    )
