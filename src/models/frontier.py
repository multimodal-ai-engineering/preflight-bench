"""Hosted Claude models through the Anthropic API, on the personal key in PREFLIGHT_API_KEY.

The key is read from PREFLIGHT_API_KEY only and passed explicitly; ANTHROPIC_API_KEY is never used.
If the key is not scoped to a workspace, set PREFLIGHT_WORKSPACE_ID (sent as anthropic-workspace-id).
Every call goes through the cost meter, which stops the run at the $25 cap.
"""
import base64, io, os, time

import anthropic
from PIL import Image

from models.cost_meter import CostMeter

OPUS = "claude-opus-5-5"
SMALL_HOSTED = os.environ.get("PREFLIGHT_SMALL_MODEL", "claude-haiku-5-5")
_meter = None


def meter():
    global _meter
    if _meter is None:
        _meter = CostMeter()
    return _meter


def client():
    headers = {}
    if os.environ.get("PREFLIGHT_WORKSPACE_ID"):
        headers["anthropic-workspace-id"] = os.environ["PREFLIGHT_WORKSPACE_ID"]
    return anthropic.Anthropic(api_key=os.environ["PREFLIGHT_API_KEY"], default_headers=headers, max_retries=4)


def img_block(im: Image.Image):
    if im.width > 1280:
        im = im.resize((1280, round(im.height * 1280 / im.width)))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PNG")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.standard_b64encode(buf.getvalue()).decode()}}


def content(images, text):
    return [img_block(im) for im in images] + [{"type": "text", "text": text}]


def _params(model, max_tokens):
    p = dict(model=model, max_tokens=max_tokens)
    if model == OPUS:
        # Thinking cannot be disabled on Opus 5.5 (400 on type=disabled). Lowest effort is the closest setting.
        p["output_config"] = {"effort": "low"}
    else:
        p["thinking"] = {"type": "disabled"}  # Haiku 5.5 accepts disabled (models endpoint, 2026-10-22)
    return p


def count(model, images, text):
    """Free token count for one request."""
    c = client()
    r = c.messages.count_tokens(model=model, messages=[{"role": "user", "content": content(images, text)}])
    return r.input_tokens


def ask(model, images, text, max_tokens=100, tag="", est_in=2000, schema=None):
    """Returns dict(text, ms, usd, usage, stop_reason, request_id). schema: JSON schema for structured output."""
    m = meter()
    m.check(model, est_in, max_tokens)
    c = client()
    t0 = time.perf_counter()
    p = _params(model, max_tokens)
    if schema is not None:
        p["output_config"] = {**p.get("output_config", {}), "format": {"type": "json_schema", "schema": schema}}
    r = c.messages.create(messages=[{"role": "user", "content": content(images, text)}], **p)
    ms = (time.perf_counter() - t0) * 1000
    usd = m.record(model, r.usage, tag)
    txt = "".join(b.text for b in r.content if b.type == "text")
    return dict(text=txt, ms=ms, usd=usd, stop_reason=r.stop_reason, request_id=r._request_id,
                usage=dict(input=r.usage.input_tokens, output=r.usage.output_tokens), model=r.model)


def list_models():
    return [(m.id, m.display_name) for m in client().models.list(limit=100)]
