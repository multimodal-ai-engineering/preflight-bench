"""Extension B.2: summarize the clean T4 latencies (colab/latency_runner.py output).

  python -m harness.ext_latency    # results/extension/gpu_out/ext_latency.jsonl -> tables/b2_latency.csv
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NAME = {"qwen2b": "qwen3-vl-2b", "qwen4b": "qwen3-vl-4b", "smolvlm2": "smolvlm2-2.2b", "florence2": "florence-2"}


def main():
    d = pd.DataFrame([json.loads(l) for l in (ROOT / "results/extension/gpu_out/ext_latency.jsonl").read_text().splitlines() if l.strip()])
    rows = []
    for (m, k), g in d.groupby(["model_key", "kind"]):
        rows.append(dict(check=NAME[m], job_kind=k, n=len(g), median_ms=float(g.ms.median()), p90_ms=float(np.percentile(g.ms, 90)),
                         gpu=g.gpu.iloc[0], dtype=g.dtype.iloc[0], transformers=g.transformers.iloc[0]))
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "results/extension/tables/b2_latency.csv", index=False)
    print(out.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
