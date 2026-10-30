#!/usr/bin/env python3
"""A localhost stand-in for a model, for smoke tests of harnesses without a key:
the Responses API, streaming. The first answer runs argv[2] with the shell tool,
the next one finishes. usage: fake_responses.py <port> <command>"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT, COMMAND = int(sys.argv[1]), sys.argv[2]
USAGE = {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10,
         "input_tokens_details": {"cached_tokens": 0},
         "output_tokens_details": {"reasoning_tokens": 0}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        finished = any(i.get("type", "").endswith("_output")
                       for i in body.get("input") or ())
        if finished:
            item = {"type": "message", "role": "assistant", "id": "m1",
                    "content": [{"type": "output_text", "text": "done"}]}
        else:
            item = {"type": "function_call", "id": "f1", "call_id": "call_1",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": COMMAND})}
        rid = f"resp_{len(body.get('input') or ())}"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for event in ({"type": "response.created", "response": {"id": rid}},
                      {"type": "response.output_item.done", "item": item},
                      {"type": "response.completed",
                       "response": {"id": rid, "usage": USAGE}}):
            self.wfile.write(
                f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode())


ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
