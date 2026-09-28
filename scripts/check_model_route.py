#!/usr/bin/env python3
"""Exercise the submitted client contract against a local fake House route."""

import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent_v2.cli import run


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        assert self.path == "/v1/chat/completions"
        assert self.headers["Authorization"] == "Bearer local-test-token"
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert payload["model"] == "house"
        assert payload["max_tokens"] <= 4000
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
        prompt = json.loads(payload["messages"][1]["content"].splitlines()[-1])
        excerpt = prompt["excerpts"][0]["text"]
        answer = {
            "label": "beat",
            "point_forecast": 1.6,
            "interval": {"lo": 1.3, "hi": 1.9},
            "evidence": [{"source": 1, "quote": excerpt[:80], "claim": excerpt[:80]}],
        }
        body = json.dumps({"choices": [{"message": {"content": json.dumps(answer)}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ["MODEL_ENDPOINT"] = f"http://127.0.0.1:{server.server_port}"
    os.environ["MODEL_NAME"] = "house"
    os.environ["MODEL_TOKEN"] = "local-test-token"
    unit = Path("/tmp/agenthon-t4/units/t4-EXAMPLE-eps-beat")
    try:
        with tempfile.TemporaryDirectory() as directory:
            answer = run(unit / "task.json", unit / "corpus", Path(directory) / "answer.json")
        row = answer["entity_predictions"][0]
        assert row["label"] == "beat" and row["point_forecast"] == 1.6
        assert row["claims"] and "model predictions" in answer["evidence_trace"]
        print("House route contract and model-to-citation path: PASS")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
