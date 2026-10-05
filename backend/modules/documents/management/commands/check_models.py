import json
import time
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand

from pipeline.chunking import chunk_blocks
from pipeline.embedding import PROFILE, LocalEmbedder, model_directory


class Command(BaseCommand):
    help = "Run real offline E5 inference and compare with reference mean pooling."
    requires_system_checks = []

    def handle(self, *args, **options):
        import torch

        started = time.monotonic()
        embedder = LocalEmbedder(model_directory(settings.MODEL_CACHE_ROOT))
        texts = ["The library opens at nine.", "पुस्तकालय बिहान नौ बजे खुल्छ।"]
        for query in [False, True]:
            actual = torch.tensor(embedder.embed(texts, query=query))
            inputs = [("query: " if query else "passage: ") + text for text in texts]
            encoded = embedder.tokenizer(inputs, padding=True, return_tensors="pt")
            with torch.inference_mode():
                hidden = embedder.model(**encoded).last_hidden_state
                reference = torch.stack(
                    [
                        row[mask.bool()].mean(0)
                        for row, mask in zip(hidden, encoded["attention_mask"], strict=True)
                    ]
                )
                reference = torch.nn.functional.normalize(reference, dim=1)
            torch.testing.assert_close(actual, reference, atol=1e-6, rtol=1e-5)
        blocks = [
            SimpleNamespace(id="english", text=(texts[0] + " ") * 200, locator={"page": 1}),
            SimpleNamespace(id="nepali", text=(texts[1] + " ") * 200, locator={"page": 2}),
        ]
        chunks = chunk_blocks(blocks, embedder.tokenizer)
        by_id = {b.id: b for b in blocks}
        coverage = {b.id: set() for b in blocks}
        for chunk in chunks:
            assert chunk["token_count"] <= 384
            for span in chunk["spans"]:
                source = by_id[span["block_id"]]
                assert (
                    source.text[span["start"] : span["end"]]
                    == chunk["text"][span["chunk_start"] : span["chunk_end"]]
                )
                coverage[source.id].update(range(span["start"], span["end"]))
        for block in blocks:
            assert coverage[block.id] == set(range(len(block.text)))
        for start in range(0, len(chunks), 32):
            embedder.embed([c["text"] for c in chunks[start : start + 32]])
        self.stdout.write(
            json.dumps(
                {
                    "profile": PROFILE,
                    "reference": "passed",
                    "unicode_chunks": len(chunks),
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                }
            )
        )
