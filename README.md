# epicfurious

A Python script that mirrors [epicfurious.com](https://www.epicfurious.com/) — including all CSS, JavaScript, images, and fonts — and a GitHub Actions workflow that deploys the result to GitHub Pages.

## Usage

```bash
python3 download_epicfurious.py
```

The script downloads the homepage and every referenced asset into the `docs/` directory, rewriting all asset URLs to relative local paths so the mirror works offline.

You can also point it at a different URL or output directory:

```bash
python3 download_epicfurious.py --url https://www.epicfurious.com/ --output-dir ./docs
```

## GitHub Pages

Every push to `main` triggers the [Pages workflow](.github/workflows/pages.yml), which:

1. Runs `download_epicfurious.py` to mirror the latest site.
2. Deploys `docs/` to GitHub Pages.

> **Note:** Enable GitHub Pages in *Settings → Pages → Source → GitHub Actions* before the first deployment.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
