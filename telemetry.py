"""Observability for the agents: structured events, switched on and off per feature with environment flags.

    AGENT_LOG       which features to record, comma-separated (default: steps,usage,errors,summary)
                    "all", "none", or a list; "all,-pages" means everything except pages
    AGENT_LOG_DIR   also append every recorded event as one JSON line to <dir>/events.jsonl (locally: dev/out/log)
    AGENT_LOG_CONSOLE=0   keep the console quiet (the file still gets the events)

Features:
    steps    each tool call the model makes            model    the model's reasoning and text
    pages    each page view sent to the model          usage    tokens and simulated cost per model call
    timing   how long model calls and actions take     notes    facts the model recorded with `note`
    errors   failed actions and exceptions             summary  totals per agent and overall, at the end

Logins and other secrets registered with `redact()` are masked in every sink. Nothing here changes what the agents
do: with AGENT_LOG=none they run exactly the same, only silently.
"""
import json
import os
import sys
import time
from contextlib import contextmanager

FEATURES = ("steps", "model", "pages", "usage", "timing", "notes", "errors", "summary")
DEFAULT = "steps,usage,errors,summary"

# Simulated prices in USD per million tokens, as published for the hosted models (input, cached input, output).
PRICES = {"qwen3.8-flash-next": (0.15, 0.016, 0.47), "qwen": (0.15, 0.016, 0.47)}


def parse_flags(spec: str) -> set[str]:
    enabled: set[str] = set()
    for item in (part.strip() for part in spec.split(",")):
        if item == "all":
            enabled |= set(FEATURES)
        elif item == "none":
            enabled.clear()
        elif item.startswith("-"):
            enabled.discard(item[1:])
        elif item in FEATURES:
            enabled.add(item)
    return enabled


FLAGS = parse_flags(os.environ.get("AGENT_LOG", DEFAULT))
CONSOLE = os.environ.get("AGENT_LOG_CONSOLE", "1") != "0"
LOG_DIR = os.environ.get("AGENT_LOG_DIR")
STARTED = time.time()
_secrets: set[str] = set()
_trackers: dict[str, "Tracker"] = {}


def enabled(feature: str) -> bool:
    return feature in FLAGS


def redact(*values) -> None:
    """Mask these values (logins, TANs) wherever they would appear in a log."""
    _secrets.update(str(v) for v in values if v and len(str(v)) >= 4)


def _clean(text: str) -> str:
    for secret in _secrets:
        text = text.replace(secret, "***")
    return text


def _write(record: dict, line: str) -> None:
    if CONSOLE:
        print(_clean(line), file=sys.stderr if record["feature"] == "errors" else sys.stdout, flush=True)
    if LOG_DIR:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "events.jsonl"), "a") as file:
            file.write(_clean(json.dumps(record, ensure_ascii=False, default=str)) + "\n")


def cost_of(model: str, usage) -> float | None:
    """Simulated USD cost of one call from its usage, or None for a model without a known price."""
    price = PRICES.get(model)
    if not price or usage is None:
        return None
    cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    fresh = (usage.prompt_tokens or 0) - cached
    return (fresh * price[0] + cached * price[1] + (usage.completion_tokens or 0) * price[2]) / 1e6


class Tracker:
    """The events and running totals of one agent."""

    def __init__(self, label: str):
        self.label = label
        self.started = time.time()
        self.totals = {"model_calls": 0, "prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0,
                       "cost_usd": 0.0, "model_seconds": 0.0, "actions": 0, "action_seconds": 0.0, "errors": 0}

    def event(self, feature: str, message: str, **data) -> None:
        if feature == "errors":
            self.totals["errors"] += 1
        if not enabled(feature):
            return
        record = {"t": round(time.time() - STARTED, 3), "agent": self.label, "feature": feature,
                  "message": message, **data}
        _write(record, f"[{self.label}] {message}")

    def model_call(self, step: int, model: str, reply, seconds: float, thinking: bool | None = None) -> None:
        usage = getattr(reply, "usage", None)
        cost = cost_of(model, usage)
        cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        totals = self.totals
        totals["model_calls"] += 1
        totals["model_seconds"] += seconds
        if usage is not None:
            totals["prompt_tokens"] += usage.prompt_tokens or 0
            totals["cached_tokens"] += cached
            totals["completion_tokens"] += usage.completion_tokens or 0
        totals["cost_usd"] += cost or 0.0
        if thinking:
            totals["thinking_calls"] = totals.get("thinking_calls", 0) + 1
        if usage is not None:
            self.event("usage", f"step {step}: {usage.prompt_tokens} in ({cached} cached) / "
                                f"{usage.completion_tokens} out" + (f" ≈ ${cost:.5f}" if cost is not None else "")
                                + (" (thinking)" if thinking else ""),
                       step=step, model=model, thinking=thinking, prompt_tokens=usage.prompt_tokens, cached_tokens=cached,
                       completion_tokens=usage.completion_tokens, cost_usd=cost)
        self.event("timing", f"step {step}: model {seconds:.1f}s", step=step, what="model", seconds=round(seconds, 3))

    @contextmanager
    def action(self, step: int, name: str):
        """Times one browser action; failures are recorded by the caller as errors."""
        started = time.time()
        try:
            yield
        finally:
            seconds = time.time() - started
            self.totals["actions"] += 1
            self.totals["action_seconds"] += seconds
            self.event("timing", f"step {step}: {name} {seconds:.1f}s", step=step, what=name,
                       seconds=round(seconds, 3))

    def finish(self, outcome: str) -> None:
        totals = self.totals
        totals["wall_seconds"] = round(time.time() - self.started, 1)
        self.event("summary", f"{outcome}: {totals['model_calls']} model calls, "
                              f"{totals['prompt_tokens'] + totals['completion_tokens']} tokens, "
                              f"${totals['cost_usd']:.4f}, {totals['wall_seconds']}s "
                              f"(model {totals['model_seconds']:.0f}s, browser {totals['action_seconds']:.0f}s), "
                              f"{totals['errors']} errors", outcome=outcome, **totals)


def tracker(label: str) -> Tracker:
    """The tracker for one agent; asking again with the same label returns the same one."""
    if label not in _trackers:
        _trackers[label] = Tracker(label)
    return _trackers[label]


def summary() -> dict:
    """Totals over every agent of this process; also logged under the `summary` feature."""
    keys = ("model_calls", "prompt_tokens", "completion_tokens", "cost_usd", "errors")
    total = {k: sum(t.totals.get(k, 0) for t in _trackers.values()) for k in keys}
    total["wall_seconds"] = round(time.time() - STARTED, 1)
    if enabled("summary"):
        _write({"t": total["wall_seconds"], "agent": "all", "feature": "summary", "message": "total", **total},
               f"[all] total: {len(_trackers)} agents, {total['model_calls']} model calls, "
               f"{total['prompt_tokens'] + total['completion_tokens']} tokens, ${total['cost_usd']:.4f}, "
               f"{total['wall_seconds']}s, {total['errors']} errors")
    return total
