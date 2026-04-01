#!/usr/bin/env python3
"""Build index.html from selected Google Sheets form columns."""

from __future__ import annotations

import csv
import html
import io
import os
import re
import sys
from datetime import datetime, timezone
from string import Template
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

QUESTION_KEYS = ["Q1", "Q3", "Q4", "Q5", "Q6", "Q7"]
LABELS = {
    "Q1": "Q1 お名前/ハンドル",
    "Q3": "Q3 参加予定",
    "Q4": "Q4 参加予定時間帯",
    "Q5": "Q5 持参予定の飲食物",
    "Q6": "Q6 持参予定品の扱い",
    "Q7": "Q7 運営への連絡事項",
}


def resolve_csv_url() -> str:
    csv_url = os.getenv("SHEET_CSV_URL", "").strip()
    if csv_url:
        return csv_url

    sheet_id = os.getenv("SHEET_ID", "").strip()
    sheet_gid = os.getenv("SHEET_GID", "").strip()
    if not sheet_id or not sheet_gid:
        raise RuntimeError("Set SHEET_CSV_URL or both SHEET_ID and SHEET_GID.")

    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
        f"?tqx=out:csv&gid={sheet_gid}"
    )


def fetch_csv_text(csv_url: str) -> str:
    request = Request(csv_url, headers={"User-Agent": "github-actions-sheet-sync/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8-sig", errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"Failed to fetch CSV: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch CSV: {exc.reason}") from exc

    if "<!doctype html" in text[:400].lower() or "<html" in text[:400].lower():
        raise RuntimeError(
            "CSV URL returned HTML instead of CSV. "
            "Make the sheet public/readable by link or set SHEET_CSV_URL "
            "to a published CSV URL."
        )

    return text


def find_indexes(header: list[str]) -> dict[str, int]:
    indexes: dict[str, int] = {}
    for key in QUESTION_KEYS:
        pattern = re.compile(rf"^{re.escape(key)}\\.")
        for idx, cell in enumerate(header):
            if pattern.match(cell.strip()):
                indexes[key] = idx
                break

    missing = [key for key in QUESTION_KEYS if key not in indexes]
    if missing:
        raise RuntimeError(f"Missing expected columns: {', '.join(missing)}")

    return indexes


def parse_records(csv_text: str) -> list[dict[str, str]]:
    rows = list(csv.reader(io.StringIO(csv_text)))
    if not rows:
        return []

    header = rows[0]
    indexes = find_indexes(header)
    max_index = max(indexes.values())

    records: list[dict[str, str]] = []
    for row in rows[1:]:
        if len(row) <= max_index:
            row = row + [""] * (max_index + 1 - len(row))

        record = {key: row[idx].strip() for key, idx in indexes.items()}
        if any(record.values()):
            records.append(record)

    return records


def esc(value: str) -> str:
    return html.escape(value, quote=False)


def render_cards(records: list[dict[str, str]]) -> str:
    if not records:
        return """<article class=\"card\"><h2><span class=\"badge\">-</span>回答なし</h2><p>現在、表示できる回答がありません。</p></article>"""

    chunks: list[str] = []
    for i, record in enumerate(records, start=1):
        name = esc(record.get("Q1", "").strip()) or f"回答 {i}"
        q3 = esc(record.get("Q3", "").strip() or "（未記入）")
        q4 = esc(record.get("Q4", "").strip() or "（未記入）")
        q5 = esc(record.get("Q5", "").strip() or "（未記入）")
        q6 = esc(record.get("Q6", "").strip() or "（未記入）")
        q7 = esc(record.get("Q7", "").strip() or "（未記入）")

        chunks.append(
            """
      <article class=\"card\">
        <h2><span class=\"badge\">{i}</span> {name}</h2>
        <dl>
          <dt>{q1_label}</dt>
          <dd>{name}</dd>
          <dt>{q3_label}</dt>
          <dd>{q3}</dd>
          <dt>{q4_label}</dt>
          <dd>{q4}</dd>
          <dt>{q5_label}</dt>
          <dd>{q5}</dd>
          <dt>{q6_label}</dt>
          <dd>{q6}</dd>
          <dt>{q7_label}</dt>
          <dd>{q7}</dd>
        </dl>
      </article>""".format(
                i=i,
                name=name,
                q1_label=esc(LABELS["Q1"]),
                q3_label=esc(LABELS["Q3"]),
                q4_label=esc(LABELS["Q4"]),
                q5_label=esc(LABELS["Q5"]),
                q6_label=esc(LABELS["Q6"]),
                q7_label=esc(LABELS["Q7"]),
                q3=q3,
                q4=q4,
                q5=q5,
                q6=q6,
                q7=q7,
            )
        )

    return "\n".join(chunks)


def render_html(records: list[dict[str, str]]) -> str:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    template = Template(
        """<!doctype html>
<html lang=\"ja\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>株クラ新緑ピクニック会 2026 | Q1・Q3〜Q7</title>
  <meta name=\"description\" content=\"株クラ新緑ピクニック会・春の陣2026の回答からQ1,Q3,Q4,Q5,Q6,Q7を抜き出した公開ページ\" />
  <style>
    :root {
      --bg-1: #f8f4ec;
      --bg-2: #e5efe3;
      --ink: #243027;
      --muted: #4d5b51;
      --line: #c6d4c6;
      --card: #fffefb;
      --accent: #2f7d5a;
      --accent-soft: #e9f5ef;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      color: var(--ink);
      font-family: "Hiragino Kaku Gothic ProN", "Yu Gothic", "Noto Sans JP", sans-serif;
      background:
        radial-gradient(1200px 600px at 10% -10%, #fff9e7 0%, transparent 55%),
        radial-gradient(1200px 600px at 95% 0%, #e8f6ee 0%, transparent 60%),
        linear-gradient(160deg, var(--bg-1), var(--bg-2));
      min-height: 100vh;
      line-height: 1.6;
    }

    .wrap {
      width: min(1120px, 92vw);
      margin: 0 auto;
      padding: 40px 0 64px;
    }

    header {
      margin-bottom: 20px;
      padding: 24px;
      border: 1px solid var(--line);
      border-radius: 20px;
      background: rgba(255, 255, 255, 0.72);
      backdrop-filter: blur(4px);
      box-shadow: 0 14px 40px rgba(40, 68, 54, 0.08);
    }

    h1 {
      margin: 0 0 8px;
      font-size: clamp(1.7rem, 4vw, 2.8rem);
      letter-spacing: 0.01em;
      line-height: 1.2;
    }

    .lead {
      margin: 0;
      color: var(--muted);
      font-size: 1rem;
    }

    .summary {
      margin-top: 14px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    .pill {
      padding: 7px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--accent-soft);
      font-size: 0.9rem;
      font-weight: 600;
      color: #1f5f43;
    }

    .list {
      display: grid;
      gap: 14px;
      margin-top: 18px;
    }

    .card {
      border: 1px solid var(--line);
      border-radius: 18px;
      background: var(--card);
      padding: 16px;
      box-shadow: 0 10px 26px rgba(39, 72, 55, 0.08);
      animation: fade-up 0.45s ease both;
    }

    .card h2 {
      margin: 0 0 10px;
      font-size: 1.1rem;
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 1.8rem;
      height: 1.8rem;
      border-radius: 50%;
      background: var(--accent);
      color: #fff;
      font-size: 0.9rem;
      font-weight: 700;
    }

    dl {
      margin: 0;
      display: grid;
      grid-template-columns: 190px 1fr;
      gap: 8px 12px;
    }

    dt {
      margin: 0;
      color: var(--muted);
      font-weight: 700;
      font-size: 0.95rem;
    }

    dd {
      margin: 0;
      font-size: 0.96rem;
      white-space: pre-wrap;
    }

    footer {
      margin-top: 20px;
      color: var(--muted);
      font-size: 0.9rem;
      text-align: right;
    }

    @keyframes fade-up {
      from {
        opacity: 0;
        transform: translateY(8px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    @media (max-width: 760px) {
      .wrap {
        width: min(680px, 94vw);
        padding-top: 24px;
      }

      header {
        padding: 18px;
      }

      dl {
        grid-template-columns: 1fr;
        gap: 4px;
      }

      dt {
        margin-top: 8px;
      }
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <header>
      <h1>株クラ新緑ピクニック会・春の陣2026</h1>
      <p class=\"lead\">Googleフォーム回答から <strong>Q1 / Q3 / Q4 / Q5 / Q6 / Q7</strong> のみを抽出して表示しています。</p>
      <div class=\"summary\">
        <span class=\"pill\">表示件数: $count件</span>
        <span class=\"pill\">公開先: GitHub Pages</span>
      </div>
    </header>

    <main class=\"list\">
$cards
    </main>

    <footer>抽出列: Q1, Q3, Q4, Q5, Q6, Q7 | 最終更新: $updated_at</footer>
  </div>
</body>
</html>
"""
    )

    return template.substitute(
        count=len(records),
        cards=render_cards(records),
        updated_at=now_utc,
    )


def main() -> int:
    csv_url = resolve_csv_url()
    csv_text = fetch_csv_text(csv_url)
    records = parse_records(csv_text)
    html_text = render_html(records)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_text)

    print(f"Updated index.html with {len(records)} records.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
