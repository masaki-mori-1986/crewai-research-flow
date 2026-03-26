"""
ReviewTask — Reviewer の入出力契約を定義する。
評価観点（具体性・網羅性・実行可能性）を Task レベルで保持する。
"""
from crewai import Agent, Task


def build_review_task(reviewer: Agent, plan_content: str, user_request: str) -> Task:
    """
    Args:
        reviewer: Reviewer Agent
        plan_content: 評価対象の計画テキスト
        user_request: 元のユーザ要求（評価の基準として使用）
    """
    description = (
        "以下の情報収集計画を評価してください。\n\n"
        f"元の要求:\n{user_request}\n\n"
        f"評価対象の計画:\n{plan_content}\n\n"
        "【評価観点】\n"
        "1. 具体性: 各ステップが曖昧でなく、誰でも実行できる具体的な内容か\n"
        "2. 網羅性: 要求で求められた調査範囲が過不足なくカバーされているか\n"
        "3. 実行可能性: 現実的に実行できる内容か\n\n"
        "【出力形式】\n"
        "以下の JSON 形式で出力してください:\n"
        "{\n"
        '  "verdict": "accepted" または "needs_improvement",\n'
        '  "specificity_ok": true/false,\n'
        '  "coverage_ok": true/false,\n'
        '  "feasibility_ok": true/false,\n'
        '  "improvement_requests": [\n'
        '    {"issue": "問題点", "suggestion": "改善指示"}\n'
        "  ],\n"
        '  "summary": "評価サマリ"\n'
        "}\n\n"
        "verdict が accepted の場合、improvement_requests は空リストにしてください。"
    )

    return Task(
        description=description,
        expected_output=(
            "指定された JSON 形式の評価結果。"
            "verdict / specificity_ok / coverage_ok / feasibility_ok / "
            "improvement_requests / summary をすべて含むこと。"
        ),
        agent=reviewer,
    )
