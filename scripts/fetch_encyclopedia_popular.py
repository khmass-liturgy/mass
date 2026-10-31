# -*- coding: utf-8 -*-
"""
한국가톨릭대사전(encyclopedia.catholic.or.kr) 첫 화면의 '주간 인기'·'월간 인기'
표제어를 모아 data/encyclopedia_popular.json 으로 저장한다.

카드(index.html '가톨릭대사전')는 이 목록을 날짜에 따라 하루 한 개씩 돌려 가며
그 표제어 화면으로 바로 연결한다.

첫 화면 구조 (서버에서 그려 내려오는 HTML)
------------------------------------------
  <span ...>주간 인기</span> ... <span ...>11월 1주차 기준</span></div>
  <ol>
    <li><a href="/entry/3955" class="popular-item">
          <span>1</span><span class="popular-keyword">표제어</span></a></li>
    ...
  </ol>
  <span ...>월간 인기</span> ... (같은 모양)

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

BASE = "https://encyclopedia.catholic.or.kr"

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "encyclopedia_popular.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 제목 뒤 첫 <ol>...</ol> 이 그 목록이다. 기준 문구('11월 1주차 기준')도 함께 읽는다.
SECTION_RE = r'>{name}</span>.*?>([^<>]*기준)</span>.*?<ol[^>]*>(.*?)</ol>'
ITEM_RE = re.compile(
    r'<a href="(/entry/\d+)"[^>]*class="popular-item".*?'
    r'class="popular-keyword"[^>]*>(.*?)</span>', re.S)


def clean(raw_html: str) -> str:
    """태그를 걷어내고 엔티티를 되돌린 뒤 공백을 정리한다. 끝의 ' -' 같은 꼬리도 뗀다."""
    text = html.unescape(re.sub(r"<[^>]+>", "", raw_html))
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s*-\s*$", "", text)


def parse_section(page: str, name: str) -> dict:
    m = re.search(SECTION_RE.format(name=name), page, re.S)
    if not m:
        raise ValueError(f"'{name}' 목록을 찾지 못했습니다.")
    items = []
    for href, kw in ITEM_RE.findall(m.group(2)):
        title = clean(kw)
        if title:
            items.append({"title": title, "url": urljoin(BASE + "/", href)})
    if not items:
        raise ValueError(f"'{name}' 목록에 표제어가 없습니다.")
    return {"basis": clean(m.group(1)), "items": items}


def main() -> int:
    try:
        r = requests.get(BASE + "/", headers=HEADERS, timeout=30)
        r.raise_for_status()
        r.encoding = "utf-8"
        weekly = parse_section(r.text, "주간 인기")
        monthly = parse_section(r.text, "월간 인기")
    except Exception as e:
        print("encyclopedia popular fetch/parse failed:", e, file=sys.stderr)
        return 1

    data = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "source": BASE + "/",
        "weekly": weekly,
        "monthly": monthly,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("saved:", OUT)
    for key in ("weekly", "monthly"):
        print(" ", key, data[key]["basis"], [it["title"] for it in data[key]["items"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
