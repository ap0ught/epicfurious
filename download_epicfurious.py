from __future__ import annotations

import argparse
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_URL = "https://www.epicfurious.com/"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "docs"
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; epicfurious-downloader/1.0)"

# HTML tags whose attributes may reference downloadable assets
_TAG_ASSET_ATTRS: dict[str, list[str]] = {
    "img":    ["src", "data-src"],
    "script": ["src"],
    "link":   ["href"],
    "source": ["src"],
    "video":  ["src", "poster"],
    "audio":  ["src"],
    "input":  ["src"],
    "track":  ["src"],
    "iframe": ["src"],
}

# Matches url(...) inside CSS, with or without quotes
_CSS_URL_RE = re.compile(r"""url\(\s*['"]?([^)'"]+?)['"]?\s*\)""")


def _fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def _url_to_asset(asset_url: str, base_url: str, output_dir: Path) -> tuple[str, Path, str] | None:
    """
    Return (rel_path, local_path, resolved_url) for an asset URL, or None when
    the URL should be skipped (non-http/https scheme or data URI).
    """
    if asset_url.startswith("data:"):
        return None
    absolute = urljoin(base_url, asset_url)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    # Derive a stable local path from the URL
    path = parsed.path.lstrip("/")
    if not path or path.endswith("/"):
        path = (path or "") + "index.html"
    return path, output_dir / path, absolute


class _HTMLRewriter(HTMLParser):
    """Parse an HTML document, queue all referenced assets, and rewrite their
    URLs to relative local paths."""

    def __init__(self, base_url: str, output_dir: Path) -> None:
        super().__init__(convert_charrefs=False)
        self._base_url = base_url
        self._output_dir = output_dir
        self.assets: list[tuple[str, Path, str]] = []  # (rel_path, local_path, abs_url)
        self._parts: list[str] = []

    # ------------------------------------------------------------------
    def _queue(self, asset_url: str) -> str:
        """Queue an asset for download and return the rewritten relative path."""
        result = _url_to_asset(asset_url, self._base_url, self._output_dir)
        if result is None:
            return asset_url
        rel, local, absolute = result
        self.assets.append((rel, local, absolute))
        return rel

    def _rewrite_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> list[tuple[str, str | None]]:
        out = []
        for name, value in attrs:
            if value and name in _TAG_ASSET_ATTRS.get(tag, []):
                value = self._queue(value)
            out.append((name, value))
        return out

    @staticmethod
    def _attrs_str(attrs: list[tuple[str, str | None]]) -> str:
        parts = []
        for name, value in attrs:
            if value is None:
                parts.append(name)
            else:
                parts.append(f'{name}="{value.replace(chr(34), "&quot;")}"')
        return (" " + " ".join(parts)) if parts else ""

    # ------------------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._parts.append(f"<{tag}{self._attrs_str(self._rewrite_attrs(tag, attrs))}>")

    def handle_endtag(self, tag: str) -> None:
        self._parts.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._parts.append(f"<{tag}{self._attrs_str(self._rewrite_attrs(tag, attrs))}/>")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_comment(self, data: str) -> None:
        self._parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self._parts.append(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self._parts.append(f"<?{data}>")

    def handle_entityref(self, name: str) -> None:
        self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._parts.append(f"&#{name};")

    def unknown_decl(self, data: str) -> None:
        self._parts.append(f"<![{data}]>")

    def result(self) -> str:
        return "".join(self._parts)


def _rewrite_css(css_text: str, css_url: str, output_dir: Path) -> tuple[str, list[tuple[str, Path, str]]]:
    """Rewrite url() references inside a CSS document and return the rewritten
    text plus the list of assets to download."""
    assets: list[tuple[str, Path, str]] = []
    css_local_dir = output_dir / Path(urlparse(css_url).path.lstrip("/")).parent

    def _replace(m: re.Match) -> str:
        orig = m.group(1).strip()
        result = _url_to_asset(orig, css_url, output_dir)
        if result is None:
            return m.group(0)
        rel, local, absolute = result
        assets.append((rel, local, absolute))
        # Make the reference relative to the CSS file's own directory
        try:
            rel_from_css = (output_dir / rel).relative_to(css_local_dir)
        except ValueError:
            rel_from_css = Path(rel)
        return f"url({rel_from_css.as_posix()})"

    return _CSS_URL_RE.sub(_replace, css_text), assets


def download_site(url: str, output_dir: Path) -> None:
    """Download *url* and all referenced assets into *output_dir*."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fetch and rewrite the main HTML page
    html_bytes = _fetch(url)
    rewriter = _HTMLRewriter(url, output_dir)
    rewriter.feed(html_bytes.decode("utf-8", "replace"))
    index_html = output_dir / "index.html"
    index_html.write_text(rewriter.result(), encoding="utf-8")
    print(f"Saved HTML → {index_html}")

    # 2. Download every collected asset (CSS files are also parsed for their own assets)
    pending = list(rewriter.assets)
    seen: set[str] = {url}

    while pending:
        rel, local, absolute = pending.pop(0)
        if absolute in seen:
            continue
        seen.add(absolute)

        try:
            data = _fetch(absolute)
        except Exception as exc:
            print(f"  SKIP  {absolute}: {exc}")
            continue

        local.parent.mkdir(parents=True, exist_ok=True)

        if local.suffix.lower() == ".css":
            css_text, css_assets = _rewrite_css(data.decode("utf-8", "replace"), absolute, output_dir)
            local.write_text(css_text, encoding="utf-8")
            pending.extend(a for a in css_assets if a[2] not in seen)
        else:
            local.write_bytes(data)

        print(f"  Saved {absolute} → {local.relative_to(output_dir)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mirror the Epic Furious homepage and its assets for offline/GitHub Pages hosting."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Homepage URL to mirror.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where the mirrored site will be stored (default: docs/).",
    )
    args = parser.parse_args(argv)

    parsed = urlparse(args.url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https.")

    download_site(args.url, Path(args.output_dir).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
