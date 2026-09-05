# -*- coding: utf-8 -*-
"""
가톨릭신문 '기획특집'(list/108) 목록에서 최근 기사들을 모아
data/ct_feature.json 으로 저장한다.

카드에서 무엇을 보여 줄지는 화면(index.html)이 정한다.
여기서는 '최근 기사 목록'만 만들어 두고, 그중 하루에 한 건을 골라
보여 주는 일은 화면 쪽에서 한국 날짜를 기준으로 처리한다.
수집이 하루에 여러 번 돌아도 카드가 하루 한 번만 바뀌게 하려는 것이다.

목록 페이지 구조
----------------
  <div class="gisa_list">
    <div class="thum_box">
      <div class="thum_body">
        <h3><a href="/article/20260831500115">제목</a></h3>
        <p class="description">...본문 전체...</p>
        <span class="gisa_date">발행일 2026-09-06 제3506호 17면</span>
      <div class="thum_img"><a ...><img src="..."></a></div>

제목·주소·발행일만 가져온다. 본문 전체도 같은 자리에 들어 있지만
저작권 때문에 옮겨 담지 않는다 — 읽는 것은 원문 링크로 넘긴다.

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
LIST_URL = BASE + "/list/108"          # 기획특집

# 카드가 돌아가며 보여 줄 기사 수. 목록 첫 화면이 최근 10건을 준다.
MAX_ITEMS = 10

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "ct_feature.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

LIST_RE = re.compile(r'class="gisa_list"')
# 목록 오른쪽 사이드바에도 같은 모양의 thum_box 가 9건쯤 더 있다(말씀묵상 등 다른 연재).
# 기획특집이 10건보다 적게 올라온 날 사이드바 기사를 섞어 담지 않도록 여기서 끊는다.
SIDEBAR_RE = re.compile(r'right_wrap')
BOX_RE = re.compile(r'<div class="thum_box">')
TITLE_RE = re.compile(r'<h3>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', re.S)
DATE_RE = re.compile(r'class="gisa_date">\s*발행일\s*(\d{4}-\d{2}-\d{2})')
IMG_RE = re.compile(r'<div class="thum_img">.*?<img src="([^"]+)"', re.S)


def strip_tags(raw_html: str) -> str:
    """태그를 걷어내고 엔티티를 되돌린 뒤 공백을 한 칸으로 정리한다.
    html.unescape 를 쓰면 &#39; 처럼 흔치 않은 엔티티도 놓치지 않는다."""
    text = html.unescape(re.sub(r"<[^>]+>", "", raw_html))
    return re.sub(r"\s+", " ", text).strip()


def absolute(href: str) -> str:
    """urljoin 을 쓰면 '/a', 'a', '//host/a', 'http://a' 모두 규칙대로 처리된다
    ('//host/a' 같은 프로토콜 상대 주소를 BASE 뒤에 그냥 이어 붙이면 깨진다)."""
    return urljoin(BASE + "/", href)


def parse_list(html: str) -> list:
    """목록 영역에서 기사 항목들을 순서대로(최신순) 뽑는다."""
    m = LIST_RE.search(html)
    if not m:
        raise ValueError("기획특집 목록 영역(gisa_list)을 찾지 못했습니다.")
    side = SIDEBAR_RE.search(html, m.end())
    seg = html[m.start():side.start() if side else len(html)]

    starts = [b.start() for b in BOX_RE.finditer(seg)]
    if not starts:
        raise ValueError("기획특집 목록에 기사 항목(thum_box)이 없습니다.")
    starts.append(len(seg))

    items = []
    for i in range(len(starts) - 1):
        box = seg[starts[i]:starts[i + 1]]

        t = TITLE_RE.search(box)
        if not t:
            continue
        title = strip_tags(t.group(2))
        if not title:
            continue

        d = DATE_RE.search(box)
        img = IMG_RE.search(box)

        items.append({
            "title": title,
            "url": absolute(t.group(1)),
            "date": d.group(1) if d else "",
            "image": absolute(img.group(1)) if img else "",
        })
        if len(items) >= MAX_ITEMS:
            break

    if not items:
        raise ValueError("기획특집 기사를 한 건도 읽지 못했습니다.")
    return items


def main() -> int:
    try:
        r = requests.get(LIST_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        # 서버가 charset을 선언하지 않아 requests가 기본값(iso-8859-1)으로
        # 떨어졌을 때만 utf-8로 보정한다. 서버가 이미 올바르게 선언했다면
        # (지금이 그렇다) 그 값을 그대로 믿는다 — 무조건 덮어쓰면 나중에
        # 사이트 인코딩이 바뀌었을 때 오히려 깨진 글자를 만들 수 있다.
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding or "utf-8"
        items = parse_list(r.text)
    except Exception as e:
        print("ct_feature fetch/parse failed:", e, file=sys.stderr)
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
    for it in items:
        print("  ", it["date"], it["title"][:40])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
