from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_URL = "https://www.epicfurious.com/"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "downloads" / "www.epicfurious.com" / "index.html"
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; epicfurious-downloader/1.0)"


def download(url: str, output: Path) -> Path:
    request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urlopen(request, timeout=30) as response:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(response.read())
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download the Epic Furious homepage.")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL to download.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="File path where the downloaded content will be stored.",
    )
    args = parser.parse_args(argv)

    parsed = urlparse(args.url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https.")

    output = download(args.url, Path(args.output).resolve())
    print(f"Saved {args.url} to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
