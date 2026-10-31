# -*- coding: utf-8 -*-
"""
가톨릭신문 '신앙 한 컷'(list/96, 열린마당) 목록에서 최근 편들을 모아
data/faith_cut.json 으로 저장한다.

이 연재는 주간이다. 매주 일요일 자(발행일)로 한 컷짜리 그림이 올라온다.
카드에서 무엇을 보여 줄지는 화면(index.html)이 정한다 — 토·일에만 보이고,
그 주 일요일 발행분을 고른다. 여기서는 최근 목록만 만들어 둔다.

목록 페이지 구조
----------------
  <div class="gisa_list">
    <div class="thum_box">
      <h3><a href="/article/20261022500087">[신앙 한 컷] 모든 성인 대축일</a></h3>
      <span class="gisa_date">발행일 2026-11-01 제3513호 20면</span>
      <div class="thum_img"><a ...><img src="..."></a></div>

GitHub Actions에서 주기적으로 실행됨.
"""

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests

BASE = "https://www.catholictimes.org"
LIST_URL = BASE + "/list/96"           # 열린마당 > 신앙 한 컷

# 카드가 고를 수 있도록 남겨 둘 편 수. 목록 첫 화면이 최근 10건을 준다.
MAX_ITEMS = 10

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "faith_cut.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

LIST_RE = re.compile(r'class="gisa_list"')
# 목록 오른쪽 사이드바에도 같은 모양의 thum_box 가 더 있다. 거기까지만 읽는다.
SIDEBAR_RE = re.compile(r'right_wrap')
BOX_RE = re.compile(r'<div class="thum_box">')
TITLE_RE = re.compile(r'<h3>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', re.S)
DATE_RE = re.compile(r'class="gisa_date">\s*발행일\s*(\d{4}-\d{2}-\d{2})')
IMG_RE = re.compile(r'<div class="thum_img">.*?<img src="([^"]+)"', re.S)


def strip_tags(raw_html: str) -> str:
    """태그를 걷어내고 엔티티를 되돌린 뒤 공백을 한 칸으로 정리한다."""
    text = html.unescape(re.sub(r"<[^>]+>", "", raw_html))
    return re.sub(r"\s+", " ", text).strip()


def absolute(href: str) -> str:
    return urljoin(BASE + "/", href)


def parse_list(page: str) -> list:
    """목록 영역에서 신앙 한 컷 편들을 최신순으로 뽑는다."""
    m = LIST_RE.search(page)
    if not m:
        raise ValueError("신앙 한 컷 목록 영역(gisa_list)을 찾지 못했습니다.")
    side = SIDEBAR_RE.search(page, m.end())
    seg = page[m.start():side.start() if side else len(page)]

    starts = [b.start() for b in BOX_RE.finditer(seg)]
    if not starts:
        raise ValueError("신앙 한 컷 목록에 항목(thum_box)이 없습니다.")
    starts.append(len(seg))

    items = []
    for i in range(len(starts) - 1):
        box = seg[starts[i]:starts[i + 1]]

        t = TITLE_RE.search(box)
        if not t:
            continue
        title = strip_tags(t.group(2))
        d = DATE_RE.search(box)
        img = IMG_RE.search(box)
        if not title or not d or not img:
            continue

        items.append({
            "title": re.sub(r"^\[[^\]]*\]\s*", "", title).strip() or title,
            "url": absolute(t.group(1)),
            "date": d.group(1),
            "image": absolute(img.group(1)),
        })
        if len(items) >= MAX_ITEMS:
            break

    if not items:
        raise ValueError("신앙 한 컷 편을 한 건도 읽지 못했습니다.")
    return items


def main() -> int:
    try:
        r = requests.get(LIST_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding or "utf-8"
        items = parse_list(r.text)
    except Exception as e:
        print("faith_cut fetch/parse failed:", e, file=sys.stderr)
        return 1

    data = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "source": LIST_URL,
        "count": len(items),
        "items": items,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("saved:", OUT, f"({len(items)}건)")
    for it in items[:3]:
        print("  ", it["date"], it["title"][:40])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
