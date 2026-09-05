# -*- coding: utf-8 -*-
"""
가톨릭신문(catholictimes.org) 첫 화면의 대표기사(톱기사) 한 건을 뽑아
data/catholictimes.json 으로 저장한다.

첫 화면 구조
------------
첫 화면 왼쪽 맨 위에 `<div class="top_news section">` 영역이 있고,
그 안의 스와이프 배너에 톱기사가 여러 건 들어 있다. 화면을 열었을 때
처음 보이는 첫 번째 슬라이드가 곧 그날의 대표기사다.

  <div class="swiper-slide">
    <div class="top_tit">
      <h2><a href="article/20260827500124">제목</a></h2>
      <strong><a ...>부제</a></strong>
    <div class="top_cont">
      <div class="top_img"><a ...><img src="..."></a></div>

제목과 부제만 가져온다. 본문 전체도 같은 자리에 들어 있지만
저작권 때문에 옮겨 담지 않는다 — 카드에는 제목만 보여 주고
읽는 것은 원문 링크로 넘긴다.

GitHub Actions에서 주기적으로 실행됨.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE = "https://www.catholictimes.org"
HOME_URL = BASE + "/"

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "catholictimes.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

TOP_NEWS_RE = re.compile(r'class="top_news section"')
SLIDE_RE = re.compile(r'<div class="swiper-slide">')
TITLE_RE = re.compile(r'<h2>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', re.S)
SUB_RE = re.compile(r'<strong>\s*<a[^>]*>(.*?)</a>', re.S)
IMG_RE = re.compile(r'<div class="top_img">.*?<img src="([^"]+)"', re.S)

# 기사 주소 끝의 숫자 앞 8자리가 작성일이다. 예: article/20260827500124 → 2026-08-27
ARTICLE_DATE_RE = re.compile(r"/?article/(\d{4})(\d{2})(\d{2})\d+")


def strip_tags(html: str) -> str:
    """태그를 걷어내고 공백을 한 칸으로 정리한다."""
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()


def absolute(href: str) -> str:
    """첫 화면 링크는 'article/2026...' 처럼 앞 슬래시가 없이 온다."""
    if href.startswith("http"):
        return href
    return BASE + "/" + href.lstrip("/")


def first_slide(html: str) -> str:
    """톱기사 영역에서 첫 번째 슬라이드 조각만 잘라 낸다."""
    m = TOP_NEWS_RE.search(html)
    if not m:
        raise ValueError("첫 화면에서 톱기사 영역(top_news)을 찾지 못했습니다.")
    seg = html[m.start():m.start() + 40000]

    starts = [s.start() for s in SLIDE_RE.finditer(seg)]
    if not starts:
        raise ValueError("톱기사 영역에 슬라이드가 없습니다.")
    end = starts[1] if len(starts) > 1 else len(seg)
    return seg[starts[0]:end]


def parse_top_article(html: str) -> dict:
    slide = first_slide(html)

    m = TITLE_RE.search(slide)
    if not m:
        raise ValueError("대표기사 제목을 찾지 못했습니다.")
    url = absolute(m.group(1))
    title = strip_tags(m.group(2))
    if not title:
        raise ValueError("대표기사 제목이 비어 있습니다.")

    sub_m = SUB_RE.search(slide)
    summary = strip_tags(sub_m.group(1)) if sub_m else ""

    img_m = IMG_RE.search(slide)
    image = absolute(img_m.group(1)) if img_m else ""

    date = ""
    d_m = ARTICLE_DATE_RE.search(url)
    if d_m:
        date = "-".join(d_m.groups())

    return {
        "title": title,
        "summary": summary,
        "url": url,
        "image": image,
        "date": date,
    }


def main() -> int:
    try:
        r = requests.get(HOME_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        r.encoding = "utf-8"
        article = parse_top_article(r.text)
    except Exception as e:
        print("catholictimes fetch/parse failed:", e, file=sys.stderr)
        return 1

    data = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "source": HOME_URL,
        **article,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("saved:", OUT)
    print("  ", data["date"], data["title"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
