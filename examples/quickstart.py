"""Run bounded synthetic JSON/SSE sessions and retain a failed attempt.

No existing server, SDK, account, credential or tool implementation is used.
"""
import argparse
import json
import os
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from mcp_connect_diagnoser.core import _LoopbackHTTPServer
from mcp_connect_diagnoser.reports import compare_reports
from mcp_connect_diagnoser.session_probe import probe_session


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def reply(self, status, payload=None):
        body = b"" if payload is None else json.dumps(payload).encode()
        sse = self.server.phase == "after" and payload is not None
        if sse:
            body = b"event: message\ndata: " + body + b"\n\n"
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream" if sse else "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.send_header("MCP-Session-Id", "synthetic-quickstart-session")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_POST(self):
        self.connection.settimeout(2)
        length = int(self.headers.get("Content-Length", "0"))
        if self.path != "/mcp" or not 0 < length <= 262144 or self.headers.get("Authorization"):
            return self.reply(400)
        request = json.loads(self.rfile.read(length))
        method = request.get("method")
        if method == "initialize":
            result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}},
                      "serverInfo": {"name": "synthetic-meter-workshop", "version": "1"}}
        elif method == "notifications/initialized":
            return self.reply(202)
        elif method == "ping":
            if self.server.phase == "failed":
                return self.reply(200, {"jsonrpc": "2.0", "id": request["id"],
                                       "error": {"code": -32603, "message": "Synthetic ping failure"}})
            result = {}
        elif method == "tools/list":
            revision = "corrected units" if self.server.phase == "after" else "original units"
            result = {"tools": [
                {"name": "meter_reading", "description": revision,
                 "inputSchema": {"type": "object", "properties": {"meter": {"type": "string"}}},
                 "outputSchema": {"type": "object", "properties": {"watts": {"type": "number"}}}},
                {"name": "tariff_lookup", "inputSchema": {"type": "object"}}]}
        else:
            return self.reply(400)
        return self.reply(200, {"jsonrpc": "2.0", "id": request["id"], "result": result})

    def do_DELETE(self):
        self.reply(204)


def save(directory, name, report):
    descriptor = os.open(directory / (name + ".json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="new private report directory")
    args = parser.parse_args()
    request_id = str(uuid.uuid4())
    try:
        args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    except OSError:
        print(json.dumps({"requestID": request_id, "error": {
            "code": "output_exists_or_inaccessible",
            "message": "Use a new writable output directory. Previous attempts are preserved."}}),
            file=sys.stderr)
        return 2

    reports = {}
    with _LoopbackHTTPServer(("127.0.0.1", 0), Handler) as server:
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever,
                                  kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/mcp"
            for phase in ("before", "after", "failed", "recovered"):
                server.phase = phase
                reports[phase] = probe_session(url, timeout=3)
                save(args.output_dir, phase, reports[phase])
        finally:
            server.shutdown()
            thread.join(timeout=2)
    # These comparisons occur after the fixture listener is closed.
    drift = compare_reports(reports["before"], reports["after"])
    recovery = compare_reports(reports["before"], reports["recovered"])
    save(args.output_dir, "drift", drift)
    save(args.output_dir, "recovery", recovery)
    catalogue_status = drift["catalogue_comparisons"][0]["status"]
    recovered = reports["recovered"]["verified"] and recovery["same_observations"]
    verified = (reports["before"]["verified"] and reports["after"]["verified"]
                and not reports["failed"]["verified"] and catalogue_status == "changed" and recovered)
    print(json.dumps({"requestID": request_id, "verified": verified,
                      "catalogue_status": catalogue_status,
                      "failure_stage": reports["failed"].get("failure", {}).get("stage"),
                      "recovered": recovered, "reports_saved": 6}))
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
