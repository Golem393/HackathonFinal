"""The agent loop against a stub model: time limits, not step counts, end an investigator, and nothing a model does
keeps the solver past the moment the submission must start."""
import asyncio
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import llm  # noqa: E402


def reply(*calls):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=list(calls)))])


class Loop(unittest.TestCase):
    def test_an_investigator_works_until_its_deadline_not_a_step_count(self):
        async def chat(messages, tools=None, effort="none"):
            return reply(llm._Call(f"c{len(messages)}", "look", "{}"))

        async def look() -> str:
            return "a page"

        agent = llm.Agent("test", "system", [(llm.tool("look", "Look.", {}), look)], deadline=time.time() + 1.0)
        with patch.object(llm, "chat", chat):
            started = time.time()
            asyncio.run(agent.run("task", max_steps=100000))
        self.assertGreater(agent.steps, 150)  # the old cap would have stopped it here
        self.assertLess(time.time() - started, 3)

    def test_the_solver_never_answers_after_its_hard_deadline(self):
        async def chat(messages, tools=None, effort="none"):
            await asyncio.sleep(60)  # reasoning that never ends

        agent = llm.Agent("solver", "system", [], deadline=time.time() + 1, effort="medium",
                          hard_deadline=time.time() + 8)
        with patch.object(llm, "chat", chat):
            started = time.time()
            self.assertIsNone(asyncio.run(agent.run("task", max_steps=4)))
        self.assertLess(time.time() - started, 8)

    def test_a_refused_finish_says_its_summary_is_not_saved(self):
        async def record(topic: str = "", facts=None) -> str:
            return "Recorded."

        agent = llm.Agent("test", "system", [(llm.tool("record", "Save.", {}), record)], deadline=time.time() + 60,
                          stay_until=time.time() + 60, refusals=1)
        answer = asyncio.run(agent._call("finish", '{"summary": "the rate is 1.1"}'))
        self.assertTrue(answer.startswith("Your finish summary is not saved"), answer)


if __name__ == "__main__":
    unittest.main()
