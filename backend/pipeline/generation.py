"""Local Qwen adapter. Downloads happen only in the explicit preparation command."""

import hashlib
import http.client
import json
import re
import socket
import time
from pathlib import Path
from threading import Event, Thread, Timer
from urllib.parse import urlsplit

from .grounding import INPUT_LIMIT, AnswerBudgetExceeded

MODEL = "qwen3:4b"
TOKENIZER_MODEL = "Qwen/Qwen3-4B"
TOKENIZER_REVISION = "1cfa9a7208912126459214e8b04321603b3df60c"
TOKENIZER_FILES = ("tokenizer.json", "tokenizer_config.json")
PROFILE = {
    "model": MODEL,
    "tokenizer": TOKENIZER_MODEL,
    "revision": TOKENIZER_REVISION,
    "context": 16384,
    "thinking": False,
    "prompt": "qwen3-raw-template-v1",
}


class GenerationUnavailable(RuntimeError):
    pass


class GenerationTimeout(GenerationUnavailable):
    pass


class GenerationRefused(GenerationUnavailable):
    pass


def local_origin(origin):
    try:
        url = urlsplit(origin)
        if (
            url.scheme not in ("http", "https")
            or url.hostname not in ("localhost", "127.0.0.1", "::1", "ollama")
            or url.username
            or url.password
            or url.path not in ("", "/")
            or url.query
            or url.fragment
        ):
            raise ValueError
        port = url.port or (443 if url.scheme == "https" else 80)
    except ValueError as error:
        raise GenerationUnavailable(
            "Configure a local Ollama origin without credentials or a path."
        ) from error
    return url, port


def request(origin, path, payload=None, *, timeout=10, check=None):
    url, port = local_origin(origin)
    connection = (
        http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
    )(url.hostname, port, timeout=timeout)
    started, expired, timer = time.monotonic(), Event(), None
    stop, cancelled, monitor = Event(), [], None
    try:
        connection.connect()
        transport = connection.sock

        def abort():
            expired.set()
            try:
                transport.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError
        # A socket timeout alone is only an inactivity limit; stop a slow-drip response too.
        timer = Timer(remaining, abort)
        timer.daemon = True
        timer.start()
        if check is not None:

            def watch():
                while not stop.wait(0.5):
                    try:
                        check()
                    except Exception as error:
                        cancelled.append(error)
                        abort()
                        return

            monitor = Thread(target=watch, daemon=True)
            monitor.start()
        body = json.dumps(payload).encode() if payload is not None else None
        connection.request(
            "POST" if body is not None else "GET", path, body, {"Content-Type": "application/json"}
        )
        with connection.getresponse() as response:
            # No redirect following, environment proxy or unbounded body.
            raw = response.read(1024 * 1024 + 1)
            status = response.status
        if cancelled:
            raise cancelled[0]
        if expired.is_set():
            raise TimeoutError
        if status != 200 or len(raw) > 1024 * 1024:
            raise GenerationUnavailable(
                "The local generation runtime returned an invalid response."
            )
        result = json.loads(raw)
        if not isinstance(result, dict) or "error" in result:
            raise ValueError
        return result
    except TimeoutError as error:
        if cancelled:
            raise cancelled[0] from error
        raise GenerationTimeout("Local generation timed out. No answer was published.") from error
    except (OSError, ValueError, RecursionError, http.client.HTTPException) as error:
        if cancelled:
            raise cancelled[0] from error
        if expired.is_set():
            raise GenerationTimeout(
                "Local generation timed out. No answer was published."
            ) from error
        raise GenerationUnavailable(
            "Local generation is unavailable. Check the Ollama runtime."
        ) from error
    finally:
        stop.set()
        if timer is not None:
            timer.cancel()
        connection.close()
        if monitor is not None:
            monitor.join(timeout=12)


def installed_digest(origin):
    result = request(origin, "/api/tags")
    models = result.get("models")
    if isinstance(models, list):
        for model in models:
            if isinstance(model, dict) and model.get("name") == MODEL:
                digest = model.get("digest", "")
                if isinstance(digest, str) and re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", digest):
                    return digest.removeprefix("sha256:")
    raise GenerationUnavailable(
        "The local qwen3:4b model is missing. Run ollama pull qwen3:4b explicitly."
    )


def prepare_tokenizer(root):
    from huggingface_hub import snapshot_download

    directory = Path(root) / "generation" / TOKENIZER_REVISION
    snapshot_download(
        TOKENIZER_MODEL,
        revision=TOKENIZER_REVISION,
        local_dir=directory,
        allow_patterns=[*TOKENIZER_FILES, "LICENSE"],
    )
    manifest = {"profile": PROFILE, "license": "Apache-2.0", "files": {}}
    for name in TOKENIZER_FILES:
        with (directory / name).open("rb") as stream:
            manifest["files"][name] = hashlib.file_digest(stream, "sha256").hexdigest()
    save_manifest(directory / "tokenizer-manifest.json", manifest)
    return directory


def save_manifest(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def generation_tokenizer(root):
    from transformers import AutoTokenizer

    directory = Path(root) / "generation" / TOKENIZER_REVISION
    try:
        manifest = json.loads((directory / "tokenizer-manifest.json").read_text(encoding="utf-8"))
        if manifest["profile"] != PROFILE or set(manifest["files"]) != set(TOKENIZER_FILES):
            raise ValueError
        for name in TOKENIZER_FILES:
            with (directory / name).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != manifest["files"][name]:
                    raise ValueError
        return AutoTokenizer.from_pretrained(
            directory, local_files_only=True, trust_remote_code=False
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise GenerationUnavailable(
            "Generation tokenizer missing or invalid. Run pnpm generation:prepare."
        ) from error


def pin_model(root, origin):
    digest = installed_digest(origin)
    manifest = {"profile": PROFILE, "digest": digest, "license": "Apache-2.0"}
    save_manifest(Path(root) / "generation" / "model-manifest.json", manifest)
    return manifest


class LocalGenerator:
    def __init__(self, root, origin, expected_digest="", *, record_usage=None):
        local_origin(origin)
        self.origin = origin
        self.tokenizer = generation_tokenizer(root)
        try:
            manifest = json.loads(
                (Path(root) / "generation" / "model-manifest.json").read_text(encoding="utf-8")
            )
            self.digest = manifest["digest"]
            if (
                manifest["profile"] != PROFILE
                or not re.fullmatch(r"[0-9a-f]{64}", self.digest)
                or (expected_digest and expected_digest.removeprefix("sha256:") != self.digest)
            ):
                raise ValueError
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise GenerationUnavailable(
                "Generation model pin missing or mismatched. Run pnpm generation:prepare."
            ) from error
        self.usage = []
        self.record_usage = record_usage
        self.deadline = time.monotonic() + 180

    def count(self, text):
        return len(self.tokenizer(text, add_special_tokens=False)["input_ids"])

    def prompt(self, system, content):
        return self.tokenizer.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": content}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )

    def complete(self, prompt, schema, limit, check):
        count = self.count(prompt)
        if count > INPUT_LIMIT or not 1 <= limit <= 3000 or len(self.usage) >= 3:
            raise AnswerBudgetExceeded("Local generation exceeds the per-answer budget.")
        check()
        if time.monotonic() >= self.deadline:
            raise GenerationTimeout("The answer deadline expired.")
        if installed_digest(self.origin) != self.digest:
            raise GenerationUnavailable(
                "The local model changed. Prepare and pin it again explicitly."
            )
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise GenerationTimeout("The answer deadline expired.")
        check()
        usage = {"reserved": count + limit, "input": None, "output": None, "uncertain": True}
        self.usage.append(usage)
        if self.record_usage is not None:
            self.record_usage(self.usage, starting=True)
        # Do not retry ambiguous failures: computation may already have been incurred.
        result = request(
            self.origin,
            "/api/generate",
            {
                "model": MODEL,
                "prompt": prompt,
                "raw": True,
                "think": False,
                "stream": False,
                "format": schema,
                "keep_alive": "5m",
                "options": {"temperature": 0, "num_ctx": PROFILE["context"], "num_predict": limit},
            },
            timeout=min(60, remaining),
            check=check,
        )
        input_count, output_count = result.get("prompt_eval_count"), result.get("eval_count")
        if (
            type(input_count) is not int
            or type(output_count) is not int
            or input_count < 0
            or output_count < 0
        ):
            raise GenerationUnavailable("The runtime did not report valid generation usage.")
        usage.update(input=input_count, output=output_count, uncertain=False)
        if self.record_usage is not None:
            self.record_usage(self.usage)
        check()
        if time.monotonic() > self.deadline:
            raise GenerationTimeout("The answer deadline expired.")
        if input_count != count:
            raise GenerationUnavailable(
                "Runtime token count differs from the pinned tokenizer; answer withheld."
            )
        if output_count > limit or result.get("done_reason") == "length":
            raise AnswerBudgetExceeded("The answer exhausted its output budget.")
        if (
            result.get("done") is not True
            or result.get("done_reason") != "stop"
            or result.get("thinking")
            or result.get("model") != MODEL
        ):
            raise GenerationUnavailable(
                "The runtime did not complete the required non-thinking response."
            )
        raw = result.get("response")
        if not isinstance(raw, str) or not raw.strip():
            raise GenerationRefused("The model returned no answer.")
        if installed_digest(self.origin) != self.digest:
            raise GenerationUnavailable("The model pin changed during generation; answer withheld.")
        if time.monotonic() > self.deadline:
            raise GenerationTimeout("The answer deadline expired.")
        check()
        return raw
