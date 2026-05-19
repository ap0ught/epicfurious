from __future__ import annotations

import http.server
import socketserver
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from download_epicfurious import main


class _StaticHandler(http.server.BaseHTTPRequestHandler):
    response_body = b"<html><body>epic furious</body></html>"

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(self.response_body)))
        self.end_headers()
        self.wfile.write(self.response_body)

    def log_message(self, format: str, *args: object) -> None:
        return


class DownloadEpicFuriousTests(unittest.TestCase):
    def test_downloads_content_to_requested_output_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "nested" / "index.html"
            with socketserver.TCPServer(("127.0.0.1", 0), _StaticHandler) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    url = f"http://127.0.0.1:{server.server_address[1]}/"
                    result = main(["--url", url, "--output", str(output)])
                finally:
                    server.shutdown()
                    thread.join()

            self.assertEqual(result, 0)
            self.assertEqual(output.read_bytes(), _StaticHandler.response_body)

    def test_rejects_non_http_urls(self) -> None:
        with self.assertRaises(ValueError):
            main(["--url", "file:///tmp/example.html"])


if __name__ == "__main__":
    unittest.main()
