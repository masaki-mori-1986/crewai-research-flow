"""
エントリポイント — ResearchFlow を起動する最小スクリプト。
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from first_multi_agent.flow.research_flow import ResearchFlow


def main() -> None:
    user_request = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "生成AIが製造業に与える影響について調査してほしい"
    )

    print(f"\n{'='*60}")
    print(f"[Main] Request: {user_request}")
    print(f"{'='*60}\n")

    flow = ResearchFlow()
    flow.state.user_request = user_request
    flow.kickoff()

    result = flow.state.flow_result
    if result is None:
        print("\n[Main] ERROR: FlowResult が生成されませんでした。")
        return

    print(f"\n{'='*60}")
    print("[Main] Flow 完了")
    print(f"  accepted          : {result.accepted}")
    print(f"  attempts          : {result.attempts}")
    print(f"  termination_reason: {result.termination_reason}")
    print(f"  last_review       : {result.last_review_summary}")
    print(f"{'='*60}")

    if result.final_plan:
        print("\n[Main] 最終計画:\n")
        print(flow.render_plan(result.final_plan))


if __name__ == "__main__":
    main()
