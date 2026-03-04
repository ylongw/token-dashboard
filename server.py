#!/usr/bin/env python3
"""Simple HTTP server for the token dashboard."""

import os
import http.server
import functools

PORT = int(os.environ.get("PORT", 8901))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """Serve public/ for static files and data/ for JSON data."""

    def translate_path(self, path):
        # Strip query string and leading slash
        from urllib.parse import urlparse
        parsed = urlparse(path)
        rel = parsed.path.lstrip("/")

        if rel.startswith("data/"):
            return os.path.join(BASE_DIR, rel)

        # Everything else from public/
        if rel == "" or rel == "/":
            rel = "index.html"
        return os.path.join(BASE_DIR, "public", rel)

    def end_headers(self):
        # CORS for local dev and cache control for data
        self.send_header("Access-Control-Allow-Origin", "*")
        if self.path.startswith("/data/"):
            self.send_header("Cache-Control", "no-cache, max-age=0")
        super().end_headers()

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")


def main():
    handler = functools.partial(DashboardHandler)
    server = http.server.HTTPServer(("0.0.0.0", PORT), handler)
    print(f"Token Dashboard serving on http://0.0.0.0:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
