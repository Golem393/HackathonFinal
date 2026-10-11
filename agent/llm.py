"""The model side: OpenAI calls with retries, and the tool loop every agent runs.

Every call goes to OpenAI through the run's metering proxy (OPENAI_BASE_URL), with the team's key (a team secret,
OPENAI_API_KEY). Each agent says how much reasoning its job needs: none for operating a form, a little for
investigating a website, more for the solver that applies every rule. Tools and reasoning together need OpenAI's
Responses API, so that is the one used.

An agent is a system prompt, a task and a set of tools. The model picks a tool, the code runs it and returns what
happened, until the model calls finish() or its time is up. Old page views are trimmed from the history, so a long
investigation stays small and fast.
"""
import asyncio
import json
import os
import re
import time
from types import SimpleNamespace

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

FAST = "gpt-6-luna"  # browsing, forms, the TAN: many small steps
STRONG = "gpt-6-sol"  # the solver: one careful reading of all the rules and evidence
CALL_SECONDS = 30  # a step that takes longer is asked again: a stalled call usually answers at once when re-asked
KEEP_FULL = 2  # the latest tool results shown in full; older ones are cut to their first lines
TOOL_SECONDS = 90.0  # a tool that has not returned by then (a stuck page) is abandoned and the model told
SLOW_TOOLS = {"get_tan": 200.0, "configure": 150.0}  # tools that run several steps or an agent of their own
# tools whose result's first line goes to the log (the platform log is the only record of a run)
REPORTED = {"configure", "fill", "close_topic", "get_tan", "check_summary", "delegate", "login"}
_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=os.environ.get("OPENAI_BASE_URL"), api_key=os.environ["OPENAI_API_KEY"],
                              timeout=300, max_retries=1)
    return _client


async def chat(messages: list[dict], tools: list[dict] | None = None, effort: str = "none"):
    """One model answer, in the shape of a chat completion; retried on server errors, rate limits and lost
    connections. effort is "none", "low" or "medium": medium goes to the strong model."""
    request = {"model": STRONG if effort == "medium" else FAST, "input": _items(messages), "store": False,
               "reasoning": {"effort": effort},
               "instructions": "\n\n".join(m["content"] for m in messages if m["role"] == "system")}
    if tools:
        request["tools"] = [{"type": "function", **schema["function"]} for schema in tools]
    for attempt in range(6):
        try:
            response = await client().responses.create(**request)
            break
        except APIStatusError as error:
            if error.status_code == 400 and "reasoning" in str(error).lower() and "reasoning" in request:
                print(f"[model] {request['model']} refused effort {effort}; asking without it", flush=True)
                request.pop("reasoning")
                continue
            if error.status_code < 500 and error.status_code != 429:
                raise
            print(f"[model] HTTP {error.status_code}, retrying", flush=True)
        except (APIConnectionError, APITimeoutError) as error:
            print(f"[model] {type(error).__name__}, retrying", flush=True)
        await asyncio.sleep(min(20, 2 ** attempt))
    else:
        raise RuntimeError("OpenAI did not answer after several attempts")
    text = "".join(part.text for item in response.output if item.type == "message"
                   for part in item.content if getattr(part, "type", "") == "output_text")
    calls = [_Call(item.call_id, item.name, item.arguments) for item in response.output if item.type == "function_call"]
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=calls or None))])


def _items(messages: list[dict]) -> list[dict]:
    """The conversation as Responses API input items."""
    items = []
    for message in messages:
        if message["role"] == "user":
            items.append({"role": "user", "content": message["content"]})
        elif message["role"] == "assistant":
            if message.get("content"):
                items.append({"role": "assistant", "content": message["content"]})
            for call in message.get("tool_calls") or []:
                items.append({"type": "function_call", "call_id": call["id"], "name": call["function"]["name"],
                              "arguments": call["function"]["arguments"]})
        elif message["role"] == "tool":
            items.append({"type": "function_call_output", "call_id": message["tool_call_id"],
                          "output": message["content"]})
    return items


class _Call:
    """A Responses API function call, in the shape of a chat completion's tool call."""

    def __init__(self, call_id: str, name: str, arguments: str):
        self.id, self.function = call_id, SimpleNamespace(name=name, arguments=arguments)

    def model_dump(self) -> dict:
        return {"id": self.id, "type": "function",
                "function": {"name": self.function.name, "arguments": self.function.arguments}}


def tool(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    """A tool schema."""
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, **({"required": required} if required else {})}}}


class Agent:
    """A model with tools, working on one task until it calls finish() or its deadline passes.

    `stay_until`: a finish() before this time is refused (twice at most) and the agent is sent back to work, so an
    investigator does not give up on a website while the team still has time."""

    def __init__(self, name: str, system: str, tools: list[tuple[dict, object]], deadline: float,
                 finish: dict | None = None, effort: str = "none", stay_until: float = 0.0, check=None,
                 refusals: int = 2, news=None, warn_at: float = 0.0, warning: str = "",
                 hard_deadline: float = float("inf"), enough=None, max_stalls: int = 4):
        self.name, self.system, self.deadline, self.effort = name, system, deadline, effort
        self.hard_deadline = hard_deadline  # never answered after this, whatever happens (the submission waits)
        self.max_stalls = max_stalls  # unanswered calls in a row before giving up (the submitter keeps trying)
        self.check = check  # finish() is refused while check(arguments) names a problem
        self.stay_until, self.refusals, self.max_refusals = stay_until, 0, refusals
        self.news = news  # news() -> what the rest of the team found, shown when an early finish is refused
        self.enough = enough  # enough() -> True when refusing an early finish has stopped bringing anything new
        self.warn_at, self.warning = warn_at, warning  # one message at warn_at, e.g. to wrap up before the end
        self.schemas = [schema for schema, _ in tools]
        self.functions = {schema["function"]["name"]: function for schema, function in tools}
        finish = finish or {"summary": {"type": "string", "description": "A few words; facts go to record(), not here"}}
        self.schemas.append(tool("finish", "Call this when your task is done.", finish, list(finish)))
        self.result: dict | None = None
        self.steps = 0

    async def run(self, task: str, max_steps: int = 150) -> dict | None:
        messages = [{"role": "system", "content": self.system}, {"role": "user", "content": task}]
        idle, stalls, warned, reason = 0, 0, False, "finished"
        while self.result is None:
            if self.steps >= max_steps:
                reason = f"step limit {max_steps}"
                break
            if time.time() > self.hard_deadline - 5:
                reason = "hard deadline"
                break
            if self.warn_at and time.time() > self.warn_at:
                self.warn_at = 0.0
                print(f"[{self.name}] warned: {self.warning[:120]}", flush=True)
                messages.append({"role": "user", "content": self.warning})
            if time.time() > self.deadline:
                if warned:
                    reason = "out of time"
                    break
                warned = True
                messages.append({"role": "user", "content": "Time is up. Save anything important you have not "
                                                            "saved yet in this turn, then call finish."})
            self.steps += 1
            # one slow answer must not eat the team's clock: a step is asked again after CALL_SECONDS, and the
            # solver's reasoning is lowered when its time runs out
            left = min(max(20.0, self.deadline - time.time()), self.hard_deadline - 5 - time.time())
            try:
                # one answer that reasons over everything (the solver, the plan) takes its time; a browsing step not
                patient = self.effort == "medium" or not self.functions
                reply = await asyncio.wait_for(chat(trimmed(messages), self.schemas, self.effort),
                                               timeout=left if patient else min(CALL_SECONDS, left))
            except asyncio.TimeoutError:
                if self.effort == "medium" and time.time() < self.hard_deadline - 30:
                    print(f"[{self.name}] reasoning took too long; asking again with less", flush=True)
                    self.effort, self.deadline = "low", min(time.time() + 90, self.hard_deadline)
                    continue
                stalls += 1
                print(f"[{self.name}] the model did not answer in time", flush=True)
                if stalls >= self.max_stalls or time.time() > self.deadline:
                    reason = f"{stalls} stalls"
                    break
                continue
            stalls = 0
            message = reply.choices[0].message
            calls = message.tool_calls or []
            messages.append({"role": "assistant", "content": message.content or "",
                             **({"tool_calls": [call.model_dump() for call in calls]} if calls else {})})
            if message.content and message.content.strip():
                print(f"[{self.name}] says: {message.content.strip()[:300]}", flush=True)
            if not calls:
                # the finish arguments written as text instead of a call: taken as the call (one round trip less)
                written = self._finish_in_text(message.content or "")
                if written is not None:
                    answer = await self._call("finish", json.dumps(written))
                    if self.result is None:
                        messages.append({"role": "user", "content": answer})
                    continue
                idle += 1
                if idle >= 3:
                    reason = "no tool calls"
                    break
                messages.append({"role": "user", "content": "Continue by calling a tool, or call finish if "
                                                            "your task is done."})
                continue
            idle = 0
            images = []
            for call in calls:
                result = await self._call(call.function.name, call.function.arguments)
                if isinstance(result, dict):  # a screenshot: the text answers the call, the picture follows it
                    images.append(result["image"])
                    result = result["text"]
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            for image in images:
                messages.append({"role": "user", "content": [
                    {"type": "input_text", "text": "The screenshot:"},
                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image}"}]})
        print(f"[{self.name}] stopped: {reason} ({self.steps} steps, {self.refusals} refusals)", flush=True)
        return self.result

    def _finish_in_text(self, text: str) -> dict | None:
        """The finish arguments when a text answer is exactly one JSON object holding every one of them."""
        body = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        if not body.startswith("{"):
            return None
        try:
            args = json.loads(body)
        except ValueError:
            return None
        required = next((schema["function"]["parameters"].get("required") or [] for schema in self.schemas
                         if schema["function"]["name"] == "finish"), [])
        return args if isinstance(args, dict) and required and all(key in args for key in required) else None

    async def _call(self, name: str, arguments: str) -> str | dict:
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError as error:
            return f"Your arguments were not valid JSON ({error}); call the tool again."
        shown = json.dumps(args, ensure_ascii=False)
        print(f"[{self.name}] {name}({shown[:400 if name in REPORTED else 200]})", flush=True)
        if name == "finish":
            # a refused finish keeps nothing of its summary: facts only reach the team through record()
            unsaved = "Your finish summary is not saved: record() any fact in it first. " \
                if "record" in self.functions else ""
            problem = await self.check(args) if self.check else None
            if problem:
                return unsaved + problem
            if time.time() < self.stay_until and self.refusals < self.max_refusals \
                    and not (self.enough and self.enough()):
                self.refusals += 1
                minutes = int((self.stay_until - time.time()) / 60) + 1
                return unsaved + (f"Not yet: the team still has about {minutes} minutes for investigating, and facts the "
                        "brief's rules need may still be on this website. If a route led nowhere, try another one "
                        "(the navigation, menus, document lists, search, the start page). If your work depends on "
                        "facts the other agents have not recorded yet, call wait_for_notes() with what you need "
                        "instead of finishing. Record what you find; call finish again only when you are sure this "
                        "website has nothing more." + (self.news() if self.news else ""))
            self.result = args
            return "Finished."
        function = self.functions.get(name)
        if function is None:
            return f"There is no tool {name!r}."
        seconds = SLOW_TOOLS.get(name, TOOL_SECONDS)
        try:
            result = await asyncio.wait_for(function(**args), seconds)
            if name in REPORTED and isinstance(result, str):  # what happened, not only what was tried
                print(f"[{self.name}]   -> {result.strip().splitlines()[0][:200] if result.strip() else ''}",
                      flush=True)
            return result if isinstance(result, dict) else str(result)
        except asyncio.TimeoutError:
            print(f"[{self.name}] {name} did not return within {seconds:.0f} s", flush=True)
            return (f"{name} did not finish within {seconds:.0f} seconds: the page is probably stuck. Call "
                    "fresh_tab() to continue in a new tab (same login), or reload() / goto() the address again.")
        except TypeError as error:
            return f"Wrong arguments for {name}: {error}"
        except Exception as error:
            print(f"[{self.name}] {name} failed: {type(error).__name__}: {str(error)[:200]}", flush=True)
            return f"{name} failed: {type(error).__name__}: {str(error)[:500]}"


def trimmed(messages: list[dict]) -> list[dict]:
    """The history with older tool results cut short: the model only needs the latest page views in full. Of the two
    kept, the older one loses the lines it shares at its start and end with the newer one (the same header,
    navigation and footer, or the same page), and earlier finish() arguments are not repeated."""
    tool_indices = [i for i, message in enumerate(messages) if message["role"] == "tool"]
    old = set(tool_indices[:-KEEP_FULL])
    pictures = [i for i, message in enumerate(messages) if isinstance(message["content"], list)]
    finishes = [i for i, message in enumerate(messages) if message["role"] == "assistant"
                and any(call["function"]["name"] == "finish" for call in message.get("tool_calls") or [])]
    result = []
    for i, message in enumerate(messages):
        if i in pictures[:-1]:
            message = {**message, "content": "(an earlier screenshot, removed)"}
        elif i in old and len(message["content"]) > 600:
            message = {**message, "content": message["content"][:300] + "\n[… older output trimmed]"}
        elif i in finishes[:-1]:
            message = {**message, "tool_calls": [
                {**call, "function": {**call["function"], "arguments": json.dumps({"summary": "(refused, not kept)"})}}
                if call["function"]["name"] == "finish" else call for call in message["tool_calls"]]}
        result.append(message)
    kept = tool_indices[-KEEP_FULL:]
    if len(kept) == 2 and isinstance(result[kept[0]]["content"], str) and isinstance(result[kept[1]]["content"], str):
        result[kept[0]] = {**result[kept[0]], "content": same_edges(result[kept[0]]["content"],
                                                                    result[kept[1]]["content"])}
    return result


def same_edges(older: str, newer: str) -> str:
    """The older page view without the leading and trailing lines it shares with the newer one (three or more each),
    which the prompt holds in full right after it. Nothing is cut when the newer one is a part of a long page."""
    if len(older) <= 600 or newer.startswith("[page text from") or "more characters: more() shows them" in newer:
        return older
    a, b = older.split("\n"), newer.split("\n")
    body = next((n for n, line in enumerate(a) if not line.startswith(("URL:", "Title:", "Tabs:", "Event:"))
                 and not line.endswith(".") and n > 0 and a[n - 1] == ""), None)
    if body is None:
        return older
    start = body
    while start < len(a) and start < len(b) and a[start] == b[start]:
        start += 1
    end = 0
    while end < len(a) - start and end < len(b) and a[-1 - end] == b[-1 - end]:
        end += 1
    if start - body < 3 and end < 3:
        return older
    head = a[:body] + ([f"[… {start - body} lines as in the next result]"] if start - body >= 3 else a[body:start])
    middle = a[start:len(a) - end] if end else a[start:]
    tail = [f"[… {end} lines as in the next result]"] if end >= 3 else (a[len(a) - end:] if end else [])
    if not middle and start - body >= 3:
        return "\n".join(a[:body] + ["[same page as the next result]"])
    return "\n".join(head + middle + tail)
