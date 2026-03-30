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
            "以下の要求に対して、構造化された情報収集計画を生成してください。\n\n"
            "要求: {user_request}\n\n"
            "出力は JSON のみとし、説明文・コードフェンス・前置き・後書きは含めないでください。\n"
            "以下のスキーマに厳密に従ってください:\n"
            "{\n"
            '  "objective": "調査の目的",\n'
            '  "scope": "調査の範囲",\n'
            '  "key_questions": ["主要な問い1", "主要な問い2"],\n'
            '  "topics": [\n'
            "    {\n"
            '      "name": "トピック名",\n'
            '      "questions": ["このトピックで答える問い"],\n'
            '      "information_to_collect": ["収集すべき情報"]\n'
            "    }\n"
            "  ],\n"
            '  "steps": [\n'
            "    {\n"
            '      "step_number": 1,\n'
            '      "action": "実行する行動",\n'
            '      "method": "進め方",\n'
            '      "expected_output": "得られる成果"\n'
            "    }\n"
            "  ],\n"
            '  "deliverable_format": "成果物の形式"\n'
            "}\n\n"
            "`steps` は必ずトップレベルの配列にしてください。"
            "`topics[].information_to_collect` には文字列だけを入れてください。\n"
            "計画は小さく実用的にまとめてください。"
        )
    else:
        improvement_text = "\n".join(
            f"- 問題: {r.issue}\n  改善指示: {r.suggestion}"
            for r in feedback.improvement_requests
        )
        description = (
            "以下の改善フィードバックをもとに、構造化された情報収集計画を改訂してください。\n\n"
            f"元の要求: {feedback.original_request}\n\n"
            f"前回の計画:\n{feedback.current_plan}\n\n"
            f"改善要求:\n{improvement_text}\n\n"
            "改善要求をすべて反映したうえで、JSON のみを出力してください。\n"
            "説明文・コードフェンス・前置き・後書きは含めないでください。\n"
            "出力スキーマ:\n"
            "{\n"
            '  "objective": "調査の目的",\n'
            '  "scope": "調査の範囲",\n'
            '  "key_questions": ["主要な問い1", "主要な問い2"],\n'
            '  "topics": [\n'
            "    {\n"
            '      "name": "トピック名",\n'
            '      "questions": ["このトピックで答える問い"],\n'
            '      "information_to_collect": ["収集すべき情報"]\n'
            "    }\n"
            "  ],\n"
            '  "steps": [\n'
            "    {\n"
            '      "step_number": 1,\n'
            '      "action": "実行する行動",\n'
            '      "method": "進め方",\n'
            '      "expected_output": "得られる成果"\n'
            "    }\n"
            "  ],\n"
            '  "deliverable_format": "成果物の形式"\n'
            "}\n\n"
            "`steps` は必ずトップレベルの配列にしてください。"
            "`topics[].information_to_collect` には文字列だけを入れてください。"
        )

    return Task(
        description=description,
        expected_output=(
            "Plan スキーマに一致する妥当な JSON オブジェクトのみ。"
            "有効な JSON であること。"
        ),
        agent=planner,
    )
