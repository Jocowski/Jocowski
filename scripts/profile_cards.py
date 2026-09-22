"""Generate theme-aware cards from public GitHub REST data (standard library only).

Usage: python3 scripts/profile_cards.py --username Jocowski --output assets
Forks and private repositories are excluded. Language shares use byte counts
across all owned public repositories, including archived repositories.
Failed API requests abort before replacing the last successful cards.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def api(path):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Jocowski-profile-cards"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(3):
        try:
            with urlopen(Request(f"https://api.github.com{path}", headers=headers), timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)


def collect(username):
    user = api(f"/users/{quote(username)}")
    repositories = []
    page = 1
    while True:
        batch = api(f"/users/{quote(username)}/repos?type=owner&per_page=100&page={page}")
        repositories.extend(r for r in batch if not r["fork"] and not r["private"])
        if len(batch) < 100:
            break
        page += 1
    languages = Counter()
    for repository in repositories:
        languages.update(api(f"/repos/{repository['full_name']}/languages"))
    stats = [
        ("Repositórios próprios", len(repositories)),
        ("Estrelas recebidas", sum(r["stargazers_count"] for r in repositories)),
        ("Forks recebidos", sum(r["forks_count"] for r in repositories)),
        ("Seguidores", user["followers"]),
    ]
    return stats, languages


def svg_card(title, body, dark, date, description):
    bg, border, fg, muted, blue = (
        ("#0d1117", "#30363d", "#e6edf3", "#9da7b3", "#79b8ff") if dark else
        ("#ffffff", "#d8e2ed", "#1f2937", "#566575", "#1769aa")
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="390" height="226" viewBox="0 0 390 226" role="img" aria-labelledby="title description">
  <title id="title">{escape(title)}</title><desc id="description">{escape(description)}</desc>
  <style>text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; fill: {fg}; }} .heading {{ font-size: 17px; font-weight: 600; fill: {blue}; }} .label {{ font-size: 12px; fill: {muted}; }} .number {{ font-size: 28px; font-weight: 600; }} .small {{ font-size: 10px; fill: {muted}; }}</style>
  <rect x="0.5" y="0.5" width="389" height="225" rx="10" fill="{bg}" stroke="{border}" />
  <text class="heading" x="22" y="32">{escape(title)}</text>
  {body}
  <text class="small" x="22" y="209">GitHub · dados públicos · {date}</text>
</svg>
'''


def render_stats(stats, dark, date):
    elements = []
    for i, (label, value) in enumerate(stats):
        x, y = 22 + (i % 2) * 186, 78 + (i // 2) * 70
        formatted = f"{value:,}".replace(",", ".")
        elements.append(f'<text class="number" x="{x}" y="{y}">{formatted}</text><text class="label" x="{x}" y="{y + 20}">{escape(label)}</text>')
    description = "; ".join(f"{label}: {value}" for label, value in stats)
    return svg_card("Código em público", "".join(elements), dark, date, description)


def render_languages(languages, dark, date):
    total = sum(languages.values())
    rows = sorted(languages.items(), key=lambda item: (-item[1], item[0]))
    if len(rows) > 6:
        rows = rows[:5] + [("Outras", sum(n for _, n in rows[5:]))]
    blue = "#79b8ff" if dark else "#1769aa"
    track = "#212b38" if dark else "#edf2f7"
    elements = []
    description = []
    for i, (language, count) in enumerate(rows):
        share = count / total
        percent = f"{share * 100:.1f}%".replace(".", ",")
        y = 61 + i * 24
        label = escape(language)
        elements.append(f'<text class="label" x="22" y="{y}">{label}</text><rect x="147" y="{y-8}" width="151" height="6" rx="3" fill="{track}"/><rect x="147" y="{y-8}" width="{151*share:.2f}" height="6" rx="3" fill="{blue}"/><text class="label" x="368" y="{y}" text-anchor="end">{percent}</text>')
        description.append(f"{language}: {percent}")
    if not total:
        elements.append('<text class="label" x="22" y="95">Nenhuma linguagem detectada nos repositórios.</text>')
    return svg_card("Linguagens por volume de código", "".join(elements), dark, date, "; ".join(description) or "Nenhuma linguagem detectada")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="Jocowski")
    parser.add_argument("--output", type=Path, default=Path("assets"))
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", args.username):
        parser.error("Invalid GitHub username")
    stats, languages = collect(args.username)
    date = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    cards = {}
    for dark, suffix in [(False, ""), (True, "-dark")]:
        cards[f"stats{suffix}.svg"] = render_stats(stats, dark, date)
        cards[f"languages{suffix}.svg"] = render_languages(languages, dark, date)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, contents in cards.items():
        target = args.output / name
        temporary = target.with_suffix(".tmp")
        temporary.write_text(contents, encoding="utf-8")
        temporary.replace(target)
    print(f"Generated {len(cards)} cards for {args.username}: {stats[0][1]} repositories, {len(languages)} languages.")


if __name__ == "__main__":
    main()
