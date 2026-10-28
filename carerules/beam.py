"""Minimal client for Beam through Hugging Face Inference Providers (OpenAI-compatible chat completions).

Reasoning tokens count against max_completion_tokens; when the budget runs out Beam returns empty content with
finish_reason "length". Budgets below are sized per effort so that doesn't happen silently, and every call
records finish_reason, token counts and cost."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

URL = "https://router.huggingface.co/v1/chat/completions"
MODEL = "reflection/Beam-1.0-501B-A23B"
PRICE_IN, PRICE_OUT = 0.40, 1.20  # USD per million tokens (Baseten via Hugging Face, October 2026)
BUDGET = {"low": 8192, "medium": 16384, "high": 32768, "xhigh": 49152, "max": 65536}


LEDGER = Path(__file__).resolve().parent.parent / "results" / "spend.jsonl"


def spent() -> float:
    """Total spent on Beam by the benchmark scripts so far (from the ledger)."""
    if not LEDGER.exists():
        return 0.0
    return sum(json.loads(line)["cost"] for line in LEDGER.read_text().splitlines() if line.strip())


def _check_budget() -> None:
    cap = os.environ.get("CARERULES_BUDGET")
    if cap and spent() >= float(cap):
        raise SystemExit(f"Budget reached: ${spent():.2f} of ${float(cap):.2f} spent. Nothing more was sent to Beam.")


def token() -> str:
    tok = os.environ.get("HF_TOKEN")
    if not tok:
        path = Path(os.environ.get("CARERULES_TOKEN_FILE", Path.home() / ".config/carerules/hf-token"))
        tok = path.read_text().strip() if path.exists() else ""
    if not tok:
        raise SystemExit("Set HF_TOKEN or put a token in ~/.config/carerules/hf-token")
    return tok


@dataclass
class Reply:
    content: str
    reasoning: str
    tool_calls: list
    finish: str
    tokens_in: int
    tokens_out: int
    seconds: float
    raw: dict = field(repr=False, default_factory=dict)

    @property
    def cost(self) -> float:
        return (self.tokens_in * PRICE_IN + self.tokens_out * PRICE_OUT) / 1e6


def chat(messages: list[dict], effort: str = "low", tools: list | None = None, max_tokens: int | None = None,
         temperature: float = 0.0, api_key: str | None = None, retries: int = 4) -> Reply:
    _check_budget()
    body = {"model": MODEL, "messages": messages, "reasoning_effort": effort,
            "max_completion_tokens": max_tokens or BUDGET[effort], "temperature": temperature}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {api_key or token()}", "Content-Type": "application/json"})
    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(10 * 2**attempt)
                continue
            raise RuntimeError(f"HTTP {e.code}: {msg}") from None
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries:
                time.sleep(10 * 2**attempt)
                continue
            raise
    choice = data["choices"][0]
    msg = choice.get("message") or {}
    usage = data.get("usage") or {}
    rep = Reply(
        content=msg.get("content") or "",
        reasoning=msg.get("reasoning_content") or msg.get("reasoning") or "",
        tool_calls=msg.get("tool_calls") or [],
        finish=choice.get("finish_reason") or "",
        tokens_in=usage.get("prompt_tokens", 0),
        tokens_out=usage.get("completion_tokens", 0),
        seconds=round(time.time() - t0, 2),
        raw=data,
    )
    if os.environ.get("CARERULES_BUDGET"):  # benchmark runs keep a ledger; the Space doesn't
        LEDGER.parent.mkdir(exist_ok=True)
        with LEDGER.open("a") as f:
            f.write(json.dumps({"t": int(time.time()), "effort": effort, "in": rep.tokens_in, "out": rep.tokens_out,
                                "cost": round(rep.cost, 6), "finish": rep.finish}) + "\n")
    return rep
