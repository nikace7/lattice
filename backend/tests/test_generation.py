import json
import time
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

import pytest

from pipeline import generation
from pipeline.grounding import AnswerBudgetExceeded


def test_http_boundary_is_local_bounded_and_does_not_follow_redirects():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"response":"ok"}')

        def do_GET(self):
            if self.path == "/slow":
                self.send_response(200)
                self.end_headers()
                try:
                    for _ in range(30):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                        time.sleep(0.02)
                except OSError:
                    pass
                return
            if self.path == "/large":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b" " * (1024 * 1024 + 1))
                return
            self.send_response(302)
            self.send_header("Location", "https://example.invalid")
            self.end_headers()

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        assert generation.request(origin, "/api/generate", {"prompt": "synthetic"}) == {
            "response": "ok"
        }
        assert received == [{"prompt": "synthetic"}]
        with pytest.raises(generation.GenerationUnavailable):
            generation.request(origin, "/redirect")
        with pytest.raises(generation.GenerationUnavailable):
            generation.request(origin, "/large")
        with pytest.raises(generation.GenerationTimeout):
            generation.request(origin, "/slow", timeout=0.1)

        def revoked():
            raise PermissionError("Access changed")

        with pytest.raises(PermissionError, match="Access changed"):
            generation.request(origin, "/slow", timeout=3, check=revoked)
        for bad in [
            "https://example.invalid",
            "http://127.0.0.1@evil.invalid",
            "http://localhost/path",
            "http://localhost?url=x",
            "file:///private",
            "http://localhost:bad",
        ]:
            with pytest.raises(generation.GenerationUnavailable):
                generation.local_origin(bad)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


class Tokenizer:
    def __call__(self, text, **_):
        return {"input_ids": list(text)}


def generator(tmp_path, record_usage=None):
    directory = tmp_path / "generation"
    directory.mkdir(exist_ok=True)
    (directory / "model-manifest.json").write_text(
        json.dumps(
            {
                "profile": generation.PROFILE,
                "digest": "a" * 64,
            }
        )
    )
    with patch.object(generation, "generation_tokenizer", return_value=Tokenizer()):
        return generation.LocalGenerator(
            tmp_path, "http://localhost:11434", record_usage=record_usage
        )


def response(**changes):
    return {
        "model": "qwen3:4b",
        "done": True,
        "done_reason": "stop",
        "response": "{}",
        "prompt_eval_count": 5,
        "eval_count": 2,
        **changes,
    }


def test_digest_token_budget_non_thinking_and_usage_are_enforced(tmp_path):
    model = generator(tmp_path)
    with (
        patch.object(generation, "installed_digest", return_value="a" * 64),
        patch.object(generation, "request", return_value=response()) as request,
    ):
        assert model.complete("hello", {}, 100, lambda: None) == "{}"
        payload = request.call_args.args[2]
        assert payload["raw"] and payload["think"] is False and payload["stream"] is False
        assert payload["options"]["num_ctx"] == 16384 and "tools" not in payload
        assert {k: v for k, v in model.usage[0].items() if k != "timings"} == {
            "reserved": 105,
            "input": 5,
            "output": 2,
            "uncertain": False,
        }
        for changes, error in [
            ({"prompt_eval_count": 4}, generation.GenerationUnavailable),
            ({"done_reason": "length"}, AnswerBudgetExceeded),
            ({"thinking": "hidden"}, generation.GenerationUnavailable),
            ({"response": ""}, generation.GenerationRefused),
        ]:
            request.return_value = response(**changes)
            with pytest.raises(error):
                generator(tmp_path).complete("hello", {}, 100, lambda: None)
    with (
        patch.object(generation, "installed_digest", return_value="b" * 64),
        patch.object(generation, "request") as request,
    ):
        with pytest.raises(generation.GenerationUnavailable):
            model.complete("hello", {}, 100, lambda: None)
        request.assert_not_called()
    with pytest.raises(AnswerBudgetExceeded):
        model.complete("x" * 10001, {}, 100, lambda: None)


def test_ambiguous_failure_keeps_reservation_and_cancelled_completion_keeps_usage(tmp_path):
    model = generator(tmp_path)
    with (
        patch.object(generation, "installed_digest", return_value="a" * 64),
        patch.object(
            generation, "request", side_effect=generation.GenerationTimeout("timeout")
        ) as request,
    ):
        with pytest.raises(generation.GenerationTimeout):
            model.complete("hello", {}, 100, lambda: None)
        assert request.call_count == 1 and model.usage[0]["uncertain"]
        request.side_effect = None
        request.return_value = response()
        checks = 0

        def cancelled():
            nonlocal checks
            checks += 1
            if checks == 3:
                raise PermissionError("cancelled")

        with pytest.raises(PermissionError):
            model.complete("hello", {}, 100, cancelled)
        assert model.usage[-1]["output"] == 2 and not model.usage[-1]["uncertain"]


def test_call_timings_are_persisted_without_changing_token_charges(tmp_path):
    from modules.conversations.service import usage_charge

    snapshots, clock = [], [100.0]
    model = generator(tmp_path, lambda rows, **kw: snapshots.append((deepcopy(rows), kw)))

    def completed(*_, **__):
        clock[0] += 0.25
        return response(
            total_duration=240000000,
            load_duration=10000000,
            prompt_eval_duration=20000000,
            eval_duration=210000000,
        )

    with (
        patch.object(generation, "installed_digest", return_value="a" * 64),
        patch.object(generation.time, "monotonic", side_effect=lambda: clock[0]),
        patch.object(generation, "request", side_effect=completed),
    ):
        model.complete("hello", {}, 100, lambda: None)
    assert snapshots[0][1] == {"starting": True} and snapshots[0][0][0]["uncertain"]
    assert len(snapshots) == 2 and snapshots[-1][0] == model.usage
    assert model.usage[0]["timings"] == {
        "requestMs": 250,
        "totalMs": 240,
        "loadMs": 10,
        "promptEvalMs": 20,
        "generationMs": 210,
    }
    assert usage_charge(model.usage) == 7

    def timed_out(*_, **__):
        clock[0] += 0.5
        raise generation.GenerationTimeout("timeout")

    with (
        patch.object(generation, "installed_digest", return_value="a" * 64),
        patch.object(generation.time, "monotonic", side_effect=lambda: clock[0]),
        patch.object(generation, "request", side_effect=timed_out) as request,
    ):
        with pytest.raises(generation.GenerationTimeout):
            model.complete("hello", {}, 100, lambda: None)
    assert request.call_count == 1 and model.usage[-1]["uncertain"]
    assert snapshots[-1][0] == model.usage
    assert model.usage[-1]["timings"] == {
        "requestMs": 500,
        "totalMs": None,
        "loadMs": None,
        "promptEvalMs": None,
        "generationMs": None,
    }
    assert usage_charge(model.usage) == 7 + 105


@pytest.mark.parametrize("invalid", [None, True, -1, 1.5, float("nan"), 10**400])
def test_invalid_optional_runtime_timing_does_not_reject_a_valid_answer(tmp_path, invalid):
    model = generator(tmp_path)
    with (
        patch.object(generation, "installed_digest", return_value="a" * 64),
        patch.object(
            generation,
            "request",
            return_value=response(load_duration=invalid, eval_duration=1000000),
        ),
    ):
        assert model.complete("hello", {}, 100, lambda: None) == "{}"
    assert model.usage[0]["timings"]["loadMs"] is None
    assert model.usage[0]["timings"]["generationMs"] == 1
