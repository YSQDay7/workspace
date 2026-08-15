import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import agent, llm  # noqa: E402

QUESTIONS_PATH = Path(__file__).resolve().parent / "eval_questions.json"
RESULT_PATH = Path(__file__).resolve().parent / "eval_results.json"

JUDGE_SYSTEM = """你是旅游问答系统的评测员。你只判断"助手回答"是否准确、完整地回答了"游客问题"。
评分要点：
1. 事实是否与参考回答一致，尤其是票价、开放时间等数字；
2. 路线类问题必须包含具体时间安排（几点到哪个景点）；
3. 天气类问题必须使用实际天气信息回答（描述天气并给出建议）；
4. 跨景区类问题必须覆盖问题中提到的多个景区；
5. 回答即使措辞不同，只要信息正确完整就算正确。
只输出 JSON，格式：{"correct": true 或 false, "reason": "一句话说明"}。"""


def judge(question: str, reference: str, answer: str) -> dict:
    prompt = f"""游客问题：{question}

参考回答：{reference}

助手回答：{answer}

请判断助手回答是否正确完整。"""
    try:
        raw = llm.chat(
            [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=300,
            json_mode=True,
        )
        result = json.loads(raw)
        return {"correct": bool(result.get("correct")), "reason": result.get("reason", "")}
    except Exception as exc:
        return {"correct": False, "reason": f"评测失败：{exc}"}


def run() -> None:
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    results = []
    for index, item in enumerate(questions, start=1):
        question = item["question"]
        print(f"[{index}/{len(questions)}] {question}")
        try:
            response = agent.handle_chat([{"role": "user", "content": question}])
            answer = response["reply"]
        except Exception as exc:
            answer = f"（系统异常：{exc}）"
        verdict = judge(question, item["reference"], answer)
        results.append(
            {
                "question": question,
                "category": item["category"],
                "correct": verdict["correct"],
                "reason": verdict["reason"],
                "reply": answer[:500],
                "has_itinerary": response.get("itinerary") is not None,
                "source_count": len(response.get("sources", [])),
            }
        )
        print(f"   {'PASS' if verdict['correct'] else 'FAIL'} - {verdict['reason']}")

    total = len(results)
    passed = sum(1 for r in results if r["correct"])
    categories = {}
    for r in results:
        categories.setdefault(r["category"], {"total": 0, "passed": 0})
        categories[r["category"]]["total"] += 1
        categories[r["category"]]["passed"] += 1 if r["correct"] else 0

    summary = {
        "total": total,
        "passed": passed,
        "accuracy": round(passed / total, 4) if total else 0,
        "categories": categories,
        "results": results,
    }
    RESULT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== 评测结果 ===")
    print(f"总正确率：{passed}/{total} = {passed / total:.0%}")
    for category, stat in categories.items():
        print(f"  {category}: {stat['passed']}/{stat['total']} = {stat['passed'] / stat['total']:.0%}")
    print(f"明细已保存到 {RESULT_PATH}")


if __name__ == "__main__":
    run()
