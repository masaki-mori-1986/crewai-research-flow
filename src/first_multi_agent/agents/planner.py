"""
Planner Agent — 計画生成のみを担う。
状態管理・判定・制御は持たない。
"""
from crewai import Agent, LLM

from first_multi_agent.config import get_llm


def build_planner() -> Agent:
    return Agent(
        role="情報収集プランナー",
        goal="ユーザの要求に対して、具体的・網羅的・実行可能な情報収集計画を生成する",
        backstory=(
            "あなたは情報収集の専門家です。"
            "与えられた要求と（あれば）フィードバックをもとに、"
            "質の高い情報収集計画を生成することが唯一の責務です。"
        ),
        llm=get_llm(),
        verbose=True,
        allow_delegation=False,
    )
