"""CareRules as a reinforcement-learning environment. The reward is the same word-for-word checker the benchmark
uses, so a policy is paid for answers a person can confirm, and loses reward for inventing quotes.

    from carerules.env import tasks, reward
    for task in tasks():
        completion = my_model(task["prompt"])          # or a tool-using rollout with carerules.agent.TOOLS
        r = reward(task["item"], completion)

Reward:  1.0  right answer with a real quote that backs it (traps: correctly says the section doesn't exist)
         0.3  right answer, but no quote or a quote that doesn't back it
         0.0  wrong answer, no quote
        -0.5  any quote that isn't in the official rulebook (invented evidence)"""
from __future__ import annotations

from .agent import RULES, SYSTEM, TOOLS, run_tool
from .grade import grade, parse_json
from .items import all_items

__all__ = ["tasks", "reward", "SYSTEM", "TOOLS", "run_tool"]


def tasks() -> list[dict]:
    """One task per benchmark item: a chat prompt for the tool-using setup plus the item for grading."""
    return [{"id": i["id"], "item": i,
             "prompt": [{"role": "system", "content": SYSTEM},
                        {"role": "user", "content": f"State: {i['state']}\nQuestion: {i['question']}"}]}
            for i in all_items()]


def reward(item: dict, completion: str | dict) -> float:
    reply = completion if isinstance(completion, dict) else parse_json(completion)
    if not isinstance(reply, dict):
        reply = {"answer": str(completion)}
    g = grade(item, reply)
    if g["quote"].strip() and not g["cited"]:
        return -0.5
    if g["verified"]:
        return 1.0
    return 0.3 if g["correct"] else 0.0


if __name__ == "__main__":
    ts = tasks()
    it = ts[0]["item"]
    print(len(ts), "tasks;", RULES[:60] + "…")
    print("perfect:", reward(it, {"answer": it["answer"], "quote": it.get("quote", "")}),
          "| invented quote:", reward(it, {"answer": it["answer"], "quote": "Staff shall be kind to all children."}),
          "| no quote:", reward(it, {"answer": it["answer"]}))
