"""Small local GGUF wrapper for reproducible BTBC A/B experiments.

llama-cpp-python is imported lazily so memory-only metrics can run without a
model or the native runtime installed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import os


@dataclass(frozen=True)
class LLMConfig:
    model_path: str
    n_gpu_layers: int = 0
    n_ctx: int = 4096
    seed: int = 0
    max_tokens: int = 128
    temperature: float = 0.0


class LocalLLM:
    def __init__(
        self,
        model_path: str,
        *,
        n_gpu_layers: Optional[int] = None,
        n_ctx: int = 4096,
        seed: int = 0,
    ) -> None:
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"GGUF model not found: {model_path}")
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError(
                "llama-cpp-python is required for the LLM stage. "
                "Install requirements-local-agent.txt or use --only-metrics."
            ) from exc

        if n_gpu_layers is None:
            n_gpu_layers = int(os.environ.get("BTBC_N_GPU_LAYERS", "0"))
        self.config = LLMConfig(
            model_path=model_path,
            n_gpu_layers=int(n_gpu_layers),
            n_ctx=int(n_ctx),
            seed=int(seed),
        )
        self._llm = Llama(
            model_path=model_path,
            n_gpu_layers=int(n_gpu_layers),
            n_ctx=int(n_ctx),
            seed=int(seed),
            verbose=False,
        )

    def chat(
        self,
        *,
        system_prompt: str,
        memory_context: str,
        user_message: str,
        max_tokens: int = 128,
        temperature: float = 0.0,
    ) -> str:
        # A plain deterministic prompt avoids model-specific chat-template
        # differences and makes the only A/B prompt difference the memory block.
        prompt = (
            f"SYSTEM:\n{system_prompt.strip()}\n\n"
            f"MEMORY:\n{memory_context.strip()}\n\n"
            f"USER:\n{user_message.strip()}\n\nASSISTANT:\n"
        )
        out = self._llm(
            prompt,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            top_p=1.0,
            top_k=0,
            repeat_penalty=1.0,
            echo=False,
        )
        choices = out.get("choices") or []
        if not choices:
            raise RuntimeError("llama-cpp-python returned no choices")
        return str(choices[0].get("text", "")).strip()
