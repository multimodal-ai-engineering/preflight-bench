# Third-party methods, models and libraries (pilot)

## PUSV (W. Xu 2026, arXiv 2604.18860)

PUSV is a **security defense built for adversarial change** between an agent's screenshot and its action. This pilot evaluates its checks on **ordinary moving pages**, a workload it was not designed for. The checks were reimplemented from the paper's text only. No copy of its code was searched for or used.

Choices the paper leaves open, and what this pilot did:

| Open choice | Pilot choice |
|---|---|
| Which two frames Layer 1 compares | `planned_a` (planning screenshot) vs `current_b` (pre-action screenshot) |
| Patch placement at the screen edge | 160×160 patch centred on the click, shifted inward to stay inside the 1280×800 frame |
| SSIM settings | scikit-image `structural_similarity` defaults, `data_range=255`, on grayscale (ITU-R 601 luma via Pillow `convert("L")`) |
| Layer 2a "pixels outside the patch" | every pixel of the frame outside the 160×160 patch; diff threshold 20/255 on grayscale |
| Layer 2b (window list) | omitted: a browser page has no OS window list |
| What a flag triggers | re-plan (no re-aim in PUSV as published) |
| Check time | compute time only; PUSV takes one pre-action screenshot, which every condition also takes, so capture time is not charged to any condition |

## DynaCU-Bench (arXiv 2606.29472)

Cited only. No tasks or code used (no license seen).

## Models

| Model | Use | License | Source |
|---|---|---|---|
| Qwen3-VL-2B-Instruct (`Qwen/Qwen3-VL-2B-Instruct`, snapshot 8964489), fp16 | C5, Q3 | Apache-2.0 (model card) | Hugging Face |
| Qwen3-VL-4B-Instruct (`Qwen/Qwen3-VL-4B-Instruct`, snapshot ebb281e), fp16 | C6, C7, Q3 | Apache-2.0 (model card) | Hugging Face |
| Qwen3-VL-2B/4B-Instruct, 4-bit MLX (`mlx-community/...-4bit`) | laptop smoke test only, no reported numbers | Apache-2.0 (model card) | Hugging Face |
| Claude Opus 5.5 (`claude-opus-5-5`, models endpoint 2026-10-22) | C8, Q3 | Anthropic commercial terms (API) | Anthropic API |
| Claude Haiku 5.5 (`claude-haiku-5-5`, models endpoint 2026-10-22) | C9, Q3 | Anthropic commercial terms (API) | Anthropic API |

Qwen box format: the Qwen3-VL model card does not state it; the official Qwen3-VL 2D-grounding cookbook says Qwen3-VL uses **relative coordinates from 0 to 1000** (`bbox_2d = [x1, y1, x2, y2]`). Prompts ask for that format and the code converts to pixels.

Qwen runtime: the reported Qwen numbers come from a Google Colab runtime with a Tesla T4 (15 GB; no L4 was assigned), transformers 5.20.2, torch 2.11.0+cu130, fp16 weights (the T4 has no native bf16), greedy decoding (`colab/qwen_runner.py`). Model latencies are T4 numbers; pixel-check latencies are laptop numbers. The laptop (8 GB) could not hold the models without swapping, so the MLX 4-bit path was used only for the smoke test.

Hosted calls: structured output (`output_config.format`, JSON schema) for every locate and worked call. Haiku 5.5 runs with thinking disabled and `max_tokens` 100. Opus 5.5 cannot disable thinking; it runs at effort `low` with `max_tokens` 1024 (its dev outputs reached 211 tokens).

## Libraries

| Library | Version | License |
|---|---|---|
| Playwright (Python) | 1.64.1 | Apache-2.0 |
| Chromium (Playwright build 1248) | bundled | BSD-3-Clause and others |
| opencv-python-headless | 5.0.0 | Apache-2.0 (OpenCV) / MIT (wheel packaging) |
| numpy | see uv.lock | BSD-3-Clause |
| scikit-image | 0.26.0 | BSD-3-Clause |
| Pillow | see uv.lock | MIT-CMU (HPND) |
| pandas | see uv.lock | BSD-3-Clause |
| scipy | see uv.lock | BSD-3-Clause |
| matplotlib | see uv.lock | PSF-based (matplotlib license) |
| mlx / mlx-vlm | 0.7.10 (mlx-vlm) | MIT |
| transformers (Colab runtime) | 5.20.2 | Apache-2.0 |
| torch (Colab runtime) | 2.11.0+cu130 | BSD-3-Clause |
| anthropic (Python SDK) | 2.1.0 | MIT |

## Tier 0 page

`pages/tier0_booking.html` is derived from `booking-screenshots/local_booking.html` (a fictional hotel, "The Ferrow"). For this pilot the Google Fonts links and Wikimedia photos were removed and replaced with system fonts and flat colour blocks, so the page makes no network requests and renders deterministically. No third-party images ship with the pilot data.

## Full study (2026-10-23/24)

Models (zero-shot, greedy decoding, `colab/vlm_runner.py`):

| Model | Snapshot | License (model card) | Runtime |
|---|---|---|---|
| Qwen3-VL-2B-Instruct (`Qwen/Qwen3-VL-2B-Instruct`) | 8964489 | Apache-2.0 | Colab Tesla T4, fp16, transformers 5.20.2 |
| Qwen3-VL-4B-Instruct (`Qwen/Qwen3-VL-4B-Instruct`) | ebb281e | Apache-2.0 | Colab A100-SXM4-40GB, bf16, transformers 5.20.2 |
| SmolVLM2-2.2B-Instruct (`HuggingFaceTB/SmolVLM2-2.2B-Instruct`) | 482adb5 | Apache-2.0 | 259 jobs on the T4 (fp16), the rest on the A100 (bf16); transformers 4.57.1 + num2words (it fails in 5.20.2 with an image-feature shape error) |
| Florence-2-large (`florence-community/Florence-2-large`, native transformers port) | 4271c66 | MIT | Colab A100, bf16, transformers 5.20.2, `<OCR>` task on 2x2 tiles |
| Claude Haiku 5.5 (`claude-haiku-5-5`) | API | Anthropic commercial terms | Message Batches API (test and dev), 150 standard calls for latency, live-loop planner |
| Claude Opus 5.5 (`claude-opus-5-5`) | API | Anthropic commercial terms | Message Batches API (test, 300 dev), 150 standard calls for latency |

GPU: the run started on a T4; Qwen 4B, most of SmolVLM2 and all of Florence-2 ran on an A100 after a switch made to finish in one day (the preregistration named T4 or L4). Small-model latency is reported from T4 rows where they exist (Qwen 2B; 259 SmolVLM2 jobs) and labelled A100 otherwise. torch 2.11.0+cu130 on both runtimes.

Real-site set: public pages approved by the author (time.gov, census.gov popclock, USGS earthquake map, NWS radar, NOAA SWPC, Wikipedia Main Page, OpenStreetMap, arXiv cs.AI new, nasa.gov, gnu.org), loaded read-only (no clicks, no input, no login) with a research user-agent. Screenshots contain third-party content, stay in gitignored `data/realsite/`, and are never released.
