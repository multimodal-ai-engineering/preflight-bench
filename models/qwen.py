"""Qwen3-VL 2B / 4B Instruct, 4-bit MLX weights, run locally with mlx-vlm. Temperature 0."""
import time

from PIL import Image

REPOS = {"2b": "mlx-community/Qwen3-VL-2B-Instruct-4bit", "4b": "mlx-community/Qwen3-VL-4B-Instruct-4bit"}
_CACHE = {}


class Qwen:
    def __init__(self, size="4b"):
        from mlx_vlm import load
        from mlx_vlm.utils import load_config
        self.size, self.repo = size, REPOS[size]
        if size not in _CACHE:
            model, processor = load(self.repo)
            _CACHE[size] = (model, processor, load_config(self.repo))
        self.model, self.processor, self.config = _CACHE[size]

    def ask(self, images: list[Image.Image], text: str, max_tokens=64):
        """Returns (raw_text, ms). Images are passed in memory, in order."""
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template
        p = apply_chat_template(self.processor, self.config, text, num_images=len(images))
        t0 = time.perf_counter()
        out = generate(self.model, self.processor, p, image=[im.convert("RGB") for im in images],
                       max_tokens=max_tokens, temperature=0.0, verbose=False)
        ms = (time.perf_counter() - t0) * 1000
        return (out.text if hasattr(out, "text") else str(out)), ms
