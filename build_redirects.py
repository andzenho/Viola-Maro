#!/usr/bin/env python3

import argparse
import html
import json
import shutil
from pathlib import Path


ORIGIN = "https://violamaro.ru"

REDIRECTS = {
    "": "/zayavka",
    "pre": "/zayavka",
    "zayavka": "/zayavka",
    "bron": "/bron",
    "pay": "/",
    "neudobnye": "/neudobnye",
    "offer": "/offer",
    "offer-prilozhenie": "/offer-prilozhenie",
    "privacy": "/privacy",
    "consent": "/consent",
    "consent-ads": "/consent-ads",
    "terms": "/terms",
    "test": "/test",
    "koleso": "/koleso",
}


def redirect_html(target: str) -> str:
    escaped = html.escape(target, quote=True)
    target_js = json.dumps(target, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, follow">
  <meta http-equiv="refresh" content="0; url={escaped}">
  <link rel="canonical" href="{escaped}">
  <title>Переход на новый сайт</title>
  <script>
    location.replace({target_js} + location.search + location.hash);
  </script>
</head>
<body>
  <p><a href="{escaped}">Перейти на новый сайт</a></p>
</body>
</html>
"""


def fallback_html() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, follow">
  <link rel="canonical" href="https://violamaro.ru/">
  <title>Переход на новый сайт</title>
  <script>
    (function () {
      var path = location.pathname.replace(/^\\/Viola-Maro(?=\\/|$)/, "");
      if (!path || path === "/" || path === "/pre" || path === "/pre/") {
        path = "/zayavka";
      }
      location.replace("https://violamaro.ru" + path + location.search + location.hash);
    }());
  </script>
</head>
<body>
  <p><a href="https://violamaro.ru/">Перейти на новый сайт</a></p>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="redirect-site")
    args = parser.parse_args()

    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for old_path, new_path in REDIRECTS.items():
        page = out if not old_path else out / old_path
        page.mkdir(parents=True, exist_ok=True)
        (page / "index.html").write_text(
            redirect_html(ORIGIN + new_path), encoding="utf-8"
        )

    (out / "404.html").write_text(fallback_html(), encoding="utf-8")
    (out / ".nojekyll").touch()


if __name__ == "__main__":
    main()
