"""
Reviewer Agent — 評価と改善要求生成のみを担う。
状態管理・制御は持たない。
"""
from crewai import Agent

from first_multi_agent.config import get_llm


def build_reviewer() -> Agent:
    return Agent(
        role="計画レビュアー",
        goal=(
            "提示された計画を「具体性・網羅性・実行可能性」の観点で評価し、"
            "必要なら改善要求を生成する"
        ),
        backstory=(
            "あなたは批判的思考が得意なレビュアーです。"
            "計画の品質を公正に評価し、問題点と改善指示を明確に示すことが唯一の責務です。"
            "判定や再実行の制御は行いません。"
        ),
        llm=get_llm(),
        verbose=True,
        allow_delegation=False,
    )
