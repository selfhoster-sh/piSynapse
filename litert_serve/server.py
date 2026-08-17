#!/usr/bin/env python3
"""piServe - a small OpenAI-compatible HTTP server for LiteRT-LM.

Why this exists: `litert-lm serve` hard-caps the KV-cache context at 4096
tokens with no way to raise it (no CLI flag; config.json is ignored by serve).
piSynapse needs up to 8192. This server wraps the litert_lm Python API and
sets max_num_tokens explicitly, exposing only the endpoints piSynapse uses
(/v1/models, /v1/chat/completions including SSE streaming).

Tools are NOT executed here. piSynapse runs its own tool loop, so this server
only (1) feeds the tool schemas to the model, (2) returns tool_calls when the
model asks for one, and (3) accepts tool-result messages in later turns.

Config: config.json next to this file (see DEFAULT_CONFIG). CLI flags override.
Hot reload: POST /v1/admin/reload or send SIGHUP to re-read config.json
and recreate the engine (handles max_num_tokens, model switch, etc.).
"""
import argparse
import json
import logging
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from litert_lm.engine import Engine
from litert_lm.interfaces import Backend, SamplerConfig, ThinkingConfig, Tool

LOG = logging.getLogger("piserve")

DEFAULT_CONFIG = {
    "model_id": "gemma4-e2b",
    "model_path": "/home/salih/.litert-lm/models/gemma4-e2b/model.litertlm",
    "max_num_tokens": 8192,
    "speculative_decoding": True,
    "use_ringbuffers_local_attention": False,
    "enable_ynnpack": False,
    "host": "127.0.0.1",
    "port": 9380,
}

REASONING_BUDGET = {
    "minimal": 256,
    "low": 512,
    "medium": 1024,
    "high": 2048,
    "xhigh": 4096,
}

# Mutable state for hot-reload
_cfg: dict = {}
_config_path: Path | None = None
_reload_lock = threading.Lock()
_active_requests = 0
_active_lock = threading.Lock()
_reload_event = threading.Event()
_reload_event.set()


class RawSchemaTool(Tool):
    """Tool whose OpenAPI description comes straight from the request.

    automatic_tool_calling is disabled, so execute() is never called - the
    client (piSynapse) runs the actual tool code.
    """

    def __init__(self, schema: dict):
        self._schema = schema

    def get_tool_description(self) -> dict:
        return self._schema

    def execute(self, param):
        raise RuntimeError("tools are executed by the client, not by piserve")


def _text_of(resp: dict) -> str:
    """Extract plain text from a litert message dict (content may be blocks)."""
    content = resp.get("content") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content)


def _convert_content(msg: dict) -> dict:
    """Convert OpenAI content blocks to LiteRT-LM format.

    OpenAI sends:  {"type": "input_audio", "input_audio": {"data": "..."}}
                   {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
    LiteRT-LM:    {"type": "audio", "blob": "..."}
                   {"type": "image", "blob": "..."}
    """
    content = msg.get("content")
    if not isinstance(content, list):
        return msg
    converted = []
    for block in content:
        if not isinstance(block, dict):
            converted.append(block)
            continue
        btype = block.get("type", "")
        if btype == "input_audio":
            data = (block.get("input_audio") or {}).get("data", "")
            converted.append({"type": "audio", "blob": data})
        elif btype == "image_url":
            url = (block.get("image_url") or {}).get("url", "")
            if url.startswith("data:"):
                blob = url.split(",", 1)[1] if "," in url else ""
                converted.append({"type": "image", "blob": blob})
            else:
                converted.append(block)
        else:
            converted.append(block)
    return {**msg, "content": converted}


def _create_engine(cfg: dict) -> Engine:
    """Create a new Engine from config dict."""
    LOG.info(
        "creating engine: model=%s max_num_tokens=%d speculative_decoding=%s ringbuffers=%s ynnpack=%s",
        cfg["model_path"], cfg["max_num_tokens"], cfg["speculative_decoding"],
        cfg["use_ringbuffers_local_attention"], cfg["enable_ynnpack"],
    )
    return Engine(
        model_path=cfg["model_path"],
        max_num_tokens=cfg["max_num_tokens"],
        enable_speculative_decoding=bool(cfg["speculative_decoding"]),
        use_ringbuffers_local_attention=bool(cfg["use_ringbuffers_local_attention"]),
        enable_ynnpack=bool(cfg["enable_ynnpack"]),
        vision_backend=Backend.CPU(),
        audio_backend=Backend.CPU(),
    )


def reload_engine() -> dict:
    """Reload config.json and recreate the engine. Thread-safe.

    Waits for in-flight requests to finish, then swaps the engine.
    Returns status dict.
    """
    global _cfg, _active_requests

    if not _config_path or not _config_path.exists():
        return {"ok": False, "error": "config.json not found"}

    with _reload_lock:
        try:
            new_cfg = dict(DEFAULT_CONFIG)
            new_cfg.update(json.loads(_config_path.read_text(encoding="utf-8")))
        except Exception as e:
            return {"ok": False, "error": f"config parse error: {e}"}

        # Compare with current config
        engine_keys = ("model_path", "max_num_tokens", "speculative_decoding",
                        "use_ringbuffers_local_attention", "enable_ynnpack")
        changed = {k: (_cfg.get(k), new_cfg[k]) for k in engine_keys
                   if _cfg.get(k) != new_cfg.get(k)}

        if not changed and _cfg.get("model_id") == new_cfg.get("model_id"):
            return {"ok": True, "changed": False, "message": "no engine-level changes"}

        # Wait for in-flight requests to drain
        LOG.info("reload: waiting for in-flight requests to drain...")
        _reload_event.clear()
        with _active_lock:
            while _active_requests > 0:
                _active_lock.release()
                time.sleep(0.1)
                _active_lock.acquire()
        LOG.info("reload: all requests drained, swapping engine")

        old_engine = Handler.engine
        try:
            new_engine = _create_engine(new_cfg)
            Handler.engine = new_engine
            Handler.model_id = new_cfg.get("model_id", Handler.model_id)
            _cfg = new_cfg
        except Exception as e:
            _reload_event.set()
            return {"ok": False, "error": f"engine creation failed: {e}"}

    # Close old engine outside the lock (may take a moment)
    _reload_event.set()
    if old_engine:
        try:
            old_engine.close()
            LOG.info("reload: old engine closed")
        except Exception:
            LOG.warning("reload: old engine close failed", exc_info=True)

    return {"ok": True, "changed": True, "config": {
        k: new_cfg[k] for k in engine_keys
    }}


class Handler(BaseHTTPRequestHandler):
    engine = None
    model_id = "gemma4-e2b"
    _lock = threading.Lock()
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        LOG.info("http: " + fmt % args)

    def _send_json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, message):
        self._send_json(status, {"error": {"message": message}})

    def _sse(self, obj):
        self.wfile.write(
            ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")
        )
        self.wfile.flush()

    def _sse_done(self):
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/v1/models":
            self._send_json(200, {
                "object": "list",
                "data": [{
                    "id": self.model_id,
                    "object": "model",
                    "created": 0,
                    "owned_by": "litert-lm",
                }],
            })
            return
        if path == "/v1/admin/config":
            self._send_json(200, {
                "model_id": _cfg.get("model_id"),
                "model_path": _cfg.get("model_path"),
                "max_num_tokens": _cfg.get("max_num_tokens"),
                "speculative_decoding": _cfg.get("speculative_decoding"),
                "use_ringbuffers_local_attention": _cfg.get("use_ringbuffers_local_attention"),
                "enable_ynnpack": _cfg.get("enable_ynnpack"),
                "port": _cfg.get("port"),
            })
            return
        self._error(404, "Not found")

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except Exception as e:
            self._error(400, f"Invalid request body: {e}")
            return

        if path == "/v1/admin/reload":
            result = reload_engine()
            self._send_json(200 if result.get("ok") else 500, result)
            return
        if path != "/v1/chat/completions":
            self._error(404, "Not found")
            return
        try:
            _active_lock.acquire()
            global _active_requests
            _active_requests += 1
            _active_lock.release()
            _reload_event.wait()
            self._chat(body)
        except Exception as e:
            LOG.exception("chat request failed")
            try:
                self._error(500, str(e))
            except Exception:
                pass
        finally:
            _active_lock.acquire()
            _active_requests -= 1
            _active_lock.release()

    def _chat(self, body):
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            self._error(400, "messages must be a non-empty list")
            return

        stream = bool(body.get("stream", False))
        max_output = int(body.get("max_completion_tokens") or body.get("max_tokens") or 2048)
        effort = str(body.get("reasoning_effort") or "none").lower()
        tools = body.get("tools")
        tool_objs = (
            [RawSchemaTool(t) for t in tools if isinstance(t, dict)]
            if isinstance(tools, list)
            else None
        )

        temp, top_p, top_k = body.get("temperature"), body.get("top_p"), body.get("top_k")
        sampler = None
        if temp is not None or top_p is not None or top_k is not None:
            sampler = SamplerConfig(
                temperature=None if temp is None else float(temp),
                top_p=None if top_p is None else float(top_p),
                top_k=None if top_k is None else int(top_k),
            )

        thinking = None
        if effort != "none":
            thinking = ThinkingConfig(
                enable_thinking=True,
                thinking_token_budget=REASONING_BUDGET.get(effort, 1024),
            )

        current = _convert_content(messages[-1])
        prelude = [_convert_content(m) for m in messages[:-1]]

        with self._lock:
            conv = self.engine.create_conversation(
                messages=prelude or None,
                tools=tool_objs,
                automatic_tool_calling=False,
                sampler_config=sampler,
                max_output_tokens=max_output,
            )
            try:
                if stream:
                    self._chat_stream(conv, current, max_output, thinking)
                else:
                    self._chat_once(conv, current, max_output, thinking)
            finally:
                conv.close()

    def _chat_once(self, conv, current, max_output, thinking):
        resp = conv.send_message(
            current, max_output_tokens=max_output, thinking_config=thinking
        )
        message = {
            "role": "assistant",
            "content": _text_of(resp),
            "reasoning_content": resp.get("reasoning_content") or "",
        }
        if resp.get("tool_calls"):
            message["tool_calls"] = resp["tool_calls"]
        self._send_json(200, {
            "id": f"chatcmpl-{int(time.time() * 1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.model_id,
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if resp.get("tool_calls") else "stop",
            }],
        })

    def _chat_stream(self, conv, current, max_output, thinking):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.flush()
        saw_tool_calls = False
        try:
            for chunk in conv.send_message_async(
                current, max_output_tokens=max_output, thinking_config=thinking
            ):
                delta = {}
                if chunk.get("reasoning_content"):
                    delta["reasoning_content"] = chunk["reasoning_content"]
                if chunk.get("content"):
                    text = _text_of(chunk)
                    if text:
                        delta["content"] = text
                if chunk.get("tool_calls"):
                    delta["tool_calls"] = chunk["tool_calls"]
                    saw_tool_calls = True
                if delta:
                    self._sse({"choices": [{"index": 0, "delta": delta, "finish_reason": None}]})
            self._sse({"choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "tool_calls" if saw_tool_calls else "stop",
            }]})
            self._sse_done()
        except Exception as e:
            LOG.exception("stream failed")
            try:
                self._sse({"error": {"message": str(e)}})
            except Exception:
                pass


def main():
    global _cfg, _config_path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--max-num-tokens", type=int, default=None)
    parser.add_argument("--model", default=None, help="path to the .litertlm file")
    parser.add_argument("--ringbuffers", action="store_true", default=None, help="use_ringbuffers_local_attention=True")
    parser.add_argument("--no-mtp", action="store_true", default=None, help="disable speculative decoding (MTP)")
    parser.add_argument("--ynnpack", action="store_true", default=None, help="enable YNNPACK delegate")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    cfg = dict(DEFAULT_CONFIG)
    _config_path = Path(__file__).resolve().parent / "config.json"
    if _config_path.exists():
        cfg.update(json.loads(_config_path.read_text(encoding="utf-8")))
    if args.port is not None:
        cfg["port"] = args.port
    if args.max_num_tokens is not None:
        cfg["max_num_tokens"] = args.max_num_tokens
    if args.model is not None:
        cfg["model_path"] = args.model
    if args.ringbuffers is not None:
        cfg["use_ringbuffers_local_attention"] = args.ringbuffers
    if args.no_mtp is not None:
        cfg["speculative_decoding"] = not args.no_mtp
    if args.ynnpack is not None:
        cfg["enable_ynnpack"] = args.ynnpack

    engine = _create_engine(cfg)
    _cfg = cfg

    Handler.engine = engine
    Handler.model_id = cfg["model_id"]

    def _sighup_handler(signum, frame):
        LOG.info("SIGHUP received — reloading config.json")
        result = reload_engine()
        if result.get("ok"):
            LOG.info("reload: %s", result.get("message") or "engine reloaded")
        else:
            LOG.error("reload failed: %s", result.get("error"))

    signal.signal(signal.SIGHUP, _sighup_handler)

    server = ThreadingHTTPServer((cfg["host"], int(cfg["port"])), Handler)
    server.daemon_threads = True
    LOG.info("piserve listening on http://%s:%d (SIGHUP=reload)", cfg["host"], int(cfg["port"]))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        try:
            engine.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
