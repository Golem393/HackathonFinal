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


class Trimming(unittest.TestCase):
    PAGE = "URL: https://site.example/a\nTitle: T\n\n" + "\n".join(f"Menu line {n}" for n in range(8))

    def test_the_older_view_loses_only_what_the_newer_repeats(self):
        older = self.PAGE + "\nRow 1 | 12,50\nRow 2 | 7,00\n" + "\n".join(f"Footer line number {n}" for n in range(60))
        newer = self.PAGE + "\nRow 1 | 12,50\nRow 2 | 9,99\n" + "\n".join(f"Footer line number {n}" for n in range(60))
        cut = llm.same_edges(older, newer)
        self.assertIn("lines as in the next result", cut)
        self.assertIn("Row 2 | 7,00", cut)  # the line that differs stays
        self.assertIn("URL: https://site.example/a", cut)
        self.assertLess(len(cut), len(older))
        self.assertEqual(llm.same_edges(older, older + "\n[… 900 more characters: more() shows them, find(text) "
                                                       "searches them]"), older)  # a part of a long page: kept

    def test_earlier_finish_arguments_are_not_repeated(self):
        call = lambda n: {"id": f"c{n}", "type": "function",
                          "function": {"name": "finish", "arguments": '{"summary": "a long summary"}'}}
        messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
                    {"role": "assistant", "content": "", "tool_calls": [call(1)]},
                    {"role": "tool", "tool_call_id": "c1", "content": "Not yet"},
                    {"role": "assistant", "content": "", "tool_calls": [call(2)]},
                    {"role": "tool", "tool_call_id": "c2", "content": "Not yet"}]
        out = llm.trimmed(messages)
        self.assertIn("refused, not kept", out[2]["tool_calls"][0]["function"]["arguments"])
        self.assertIn("a long summary", out[4]["tool_calls"][0]["function"]["arguments"])  # the latest stays

    def test_finish_arguments_written_as_text_are_taken_as_the_call(self):
        agent = llm.Agent("t", "s", [], deadline=time.time() + 60, finish={"tan": {"type": "string"}})
        self.assertEqual(agent._finish_in_text('```json\n{"tan": "7F3A"}\n```'), {"tan": "7F3A"})
        self.assertIsNone(agent._finish_in_text("I will now look for the TAN."))
        self.assertIsNone(agent._finish_in_text('{"other": 1}'))


if __name__ == "__main__":
    unittest.main()
