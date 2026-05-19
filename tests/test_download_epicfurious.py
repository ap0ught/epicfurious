from __future__ import annotations

import http.server
import socketserver
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from download_epicfurious import _rewrite_css, main


# ---------------------------------------------------------------------------
# Minimal local HTTP server that serves a small site with two assets
# ---------------------------------------------------------------------------

_HTML = b"""<!DOCTYPE html>
<html>
<head>
  <link rel="stylesheet" href="/style.css">
  <script src="/app.js"></script>
</head>
<body>
  <img src="/logo.png" alt="logo">
  <p>Epic Furious</p>
</body>
</html>"""

_CSS = b"body { background: url('/bg.png'); color: red; }"
_JS = b"console.log('epic furious');"
_PNG = b"\x89PNG\r\n"  # minimal fake PNG bytes


_ROUTES: dict[str, tuple[bytes, str]] = {
    "/":          (_HTML, "text/html; charset=utf-8"),
    "/style.css": (_CSS,  "text/css"),
    "/app.js":    (_JS,   "application/javascript"),
    "/logo.png":  (_PNG,  "image/png"),
    "/bg.png":    (_PNG,  "image/png"),
}


class _SiteHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body, content_type = _ROUTES.get(self.path, (b"Not Found", "text/plain"))
        status = 200 if self.path in _ROUTES else 404
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def _run_server(output_dir: Path) -> tuple[str, int]:
    """Start a local HTTP server, run main() against it, and return (url, exit_code)."""
    with socketserver.TCPServer(("127.0.0.1", 0), _SiteHandler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            url = f"http://127.0.0.1:{port}/"
            code = main(["--url", url, "--output-dir", str(output_dir)])
        finally:
            server.shutdown()
            thread.join()
    return url, code


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class DownloadSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = TemporaryDirectory()
        self.output_dir = Path(self._tmpdir.name)
        _, self.exit_code = _run_server(self.output_dir)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_exit_code_is_zero(self) -> None:
        self.assertEqual(self.exit_code, 0)

    def test_index_html_is_created(self) -> None:
        self.assertTrue((self.output_dir / "index.html").exists())

    def test_index_html_rewrites_css_link(self) -> None:
        content = (self.output_dir / "index.html").read_text()
        self.assertIn("style.css", content)

    def test_css_asset_downloaded(self) -> None:
        self.assertTrue((self.output_dir / "style.css").exists())

    def test_js_asset_downloaded(self) -> None:
        self.assertTrue((self.output_dir / "app.js").exists())

    def test_img_asset_downloaded(self) -> None:
        self.assertTrue((self.output_dir / "logo.png").exists())

    def test_css_bg_image_downloaded(self) -> None:
        self.assertTrue((self.output_dir / "bg.png").exists())

    def test_rejects_non_http_urls(self) -> None:
        with self.assertRaises(ValueError):
            main(["--url", "file:///tmp/example.html"])


class RewriteCSSTests(unittest.TestCase):
    def test_rewrites_url_references(self) -> None:
        css = "body { background: url('/images/bg.png'); }"
        rewritten, assets = _rewrite_css(css, "http://example.com/css/main.css", Path("/out"))
        self.assertEqual(len(assets), 1)
        _, local, absolute = assets[0]
        self.assertEqual(absolute, "http://example.com/images/bg.png")
        self.assertIn("url(", rewritten)

    def test_skips_data_uris(self) -> None:
        css = "body { background: url('data:image/png;base64,abc'); }"
        rewritten, assets = _rewrite_css(css, "http://example.com/main.css", Path("/out"))
        self.assertEqual(assets, [])
        self.assertIn("data:image/png", rewritten)


if __name__ == "__main__":
    unittest.main()
