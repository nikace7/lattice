"""Pinned CPU E5 inference. Only prepare_model performs network I/O."""

import hashlib
import json
import math
from pathlib import Path

from .chunking import InvalidIndex

MODEL = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
PROFILE = {
    "provider": "local",
    "model": MODEL,
    "revision": REVISION,
    "dimensions": 384,
    "tokenizer": REVISION,
    "preprocessing": "e5-prefix-mean-l2-v1",
}
FILES = [
    "config.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "sentencepiece.bpe.model",
]


def prepare_model(root):
    from huggingface_hub import snapshot_download

    directory = Path(root) / REVISION
    snapshot_download(
        MODEL, revision=REVISION, local_dir=directory, allow_patterns=FILES + ["README.md"]
    )
    manifest = {"profile": PROFILE, "license": "MIT", "files": {}}
    for name in FILES:
        with (directory / name).open("rb") as stream:
            manifest["files"][name] = hashlib.file_digest(stream, "sha256").hexdigest()
    temporary = directory / "manifest.tmp"
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temporary.replace(directory / "manifest.json")
    return directory


def model_directory(root):
    directory = Path(root) / REVISION
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest["profile"] != PROFILE or set(manifest["files"]) != set(FILES):
            raise InvalidIndex("Model profile mismatch.")
        for name in FILES:
            with (directory / name).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != manifest["files"][name]:
                    raise InvalidIndex("Model artifact checksum mismatch.")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise InvalidIndex("Local model missing or invalid. Run pnpm models:prepare.") from error
    return directory


def load_tokenizer(directory):
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(directory, local_files_only=True, trust_remote_code=False)


def validate_vectors(vectors, count):
    if len(vectors) != count:
        raise InvalidIndex("Embedding count mismatch.")
    for vector in vectors:
        if (
            len(vector) != 384
            or not all(math.isfinite(v) for v in vector)
            or not math.isclose(sum(v * v for v in vector), 1.0, abs_tol=1e-4)
        ):
            raise InvalidIndex("Embeddings must be finite normalized 384-dimensional vectors.")


class LocalEmbedder:
    def __init__(self, directory):
        import torch
        from transformers import AutoModel

        torch.set_num_threads(2)
        self.tokenizer = load_tokenizer(directory)
        self.model = (
            AutoModel.from_pretrained(
                directory,
                local_files_only=True,
                trust_remote_code=False,
                use_safetensors=True,
            )
            .eval()
            .to("cpu")
        )

    def embed(self, texts, *, query=False):
        import torch

        if not 1 <= len(texts) <= 32 or any(not isinstance(t, str) or not t.strip() for t in texts):
            raise InvalidIndex("Embed 1–32 nonempty texts at a time.")
        inputs = [("query: " if query else "passage: ") + text for text in texts]
        encoded = self.tokenizer(inputs, padding=True, truncation=False, return_tensors="pt")
        if encoded["input_ids"].shape[1] > 512:
            raise InvalidIndex("Embedding input exceeds 512 tokens; split it before embedding.")
        with torch.inference_mode():
            hidden = self.model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).bool()
            pooled = hidden.masked_fill(~mask, 0).sum(1) / mask.sum(1)
            vectors = torch.nn.functional.normalize(pooled, p=2, dim=1).tolist()
        validate_vectors(vectors, len(texts))
        return vectors
