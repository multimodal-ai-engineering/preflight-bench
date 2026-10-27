"""Running cost meter for paid API calls. Stops the run at the hard cap.

Every call is appended to results/pilot/api_spend.jsonl, so the total survives restarts.
Prices are USD per million tokens, from the Anthropic pricing table as of 2026-10-22
(platform.claude.com/docs/en/about-claude/pricing).
"""
import json, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import os
# PREFLIGHT_STUDY=full|extension switches to that study's own ledger and cap (pilot $25, full $100, extension $15).
STUDY = os.environ.get("PREFLIGHT_STUDY", "pilot")
LEDGER = ROOT / "results" / STUDY / "api_spend.jsonl"
CAP_USD = {"pilot": 25.00, "full": 100.00, "extension": 15.00}[STUDY]
PRICES = {  # (input, output) per MTok
    "claude-opus-5-5": (4.00, 20.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-5-5": (0.10, 0.50),  # prompts up to 100k tokens; over 100k see LONG_PRICES
}
LONG_PRICES = {"claude-haiku-5-5": (100_000, 0.50, 2.50)}  # (threshold, input, output) per MTok


class CapExceeded(RuntimeError):
    pass


class CostMeter:
    def __init__(self, cap=CAP_USD, ledger=LEDGER):
        self.cap, self.ledger = cap, Path(ledger)
        self.lock = threading.Lock()
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        self.total = 0.0
        if self.ledger.exists():
            for line in self.ledger.read_text().splitlines():
                if line.strip():
                    self.total += json.loads(line)["usd"]

    @staticmethod
    def price(model, in_tok, out_tok):
        pi, po = PRICES[model]
        if model in LONG_PRICES and in_tok > LONG_PRICES[model][0]:
            pi, po = LONG_PRICES[model][1:]
        return in_tok * pi / 1e6 + out_tok * po / 1e6

    def check(self, model, est_in, est_out):
        """Raise before a call that could push spend past the cap."""
        with self.lock:
            if self.total + self.price(model, est_in, est_out) > self.cap:
                raise CapExceeded(f"spend ${self.total:.4f} + next call would pass cap ${self.cap:.2f}")

    def record(self, model, usage, tag="", discount=1.0):
        """discount 0.5 for Message Batches (half price)."""
        in_tok = usage.input_tokens + (getattr(usage, "cache_creation_input_tokens", 0) or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0)
        usd = self.price(model, in_tok, usage.output_tokens) * discount
        with self.lock:
            self.total += usd
            with self.ledger.open("a") as f:
                f.write(json.dumps(dict(t=time.strftime("%Y-%m-%dT%H:%M:%S"), model=model, tag=tag, input_tokens=in_tok,
                                        output_tokens=usage.output_tokens, usd=round(usd, 6), total=round(self.total, 6))) + "\n")
            if self.total > self.cap:
                raise CapExceeded(f"spend ${self.total:.4f} passed cap ${self.cap:.2f}")
        return usd
