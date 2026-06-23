"""Tiny threaded static server for the dashboard (single-threaded http.server can
hang the preview's network-idle wait on keep-alive connections)."""
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial

OUT = os.path.join(os.path.dirname(__file__), "..", "out")


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    h = partial(Handler, directory=OUT)
    srv = ThreadingHTTPServer(("127.0.0.1", 8765), h)
    print("serving", OUT, "on http://127.0.0.1:8765")
    srv.serve_forever()
