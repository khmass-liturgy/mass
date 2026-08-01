# -*- coding: utf-8 -*-
"""
data/pope_intentions.json 을 채우고 갱신한다.
- The Pope Video 공식 사이트(thepopevideo.org, 교황기도네트워크·바티칸 미디어 협력)
  한국어판에서, 아직 데이터가 없는 (연도, 월) 조합을 찾아 채운다.
- 이미 채워진 항목은 절대 덮어쓰지 않는다 (수동으로 다듬은 값이 있어도 안전).
- CBCK 공식 사이트(cbck.or.kr)는 로봇 접근을 막아두고 있어 사용하지 않는다.

매일 실행되도록 설계되어, 사이트에 다음 해 자료가 언제 올라오든(한 번에 12개월이
공개되든, 월별로 순차 공개되든) 하루 안에 자동으로 반영된다.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "pope_intentions.json"

SESSION = requests.Session()


def get(url):
    r = SESSION.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def load_existing():
    if OUT.exists():
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    return {}


def find_month_link(archive_html, month):
    soup = BeautifulSoup(archive_html, "html.parser")
    target_prefix = f"{month}월"
    for heading in soup.find_all(["h2", "h3", "h4"]):
        text = heading.get_text(strip=True)
        if text.startswith(target_prefix + " ") or text.startswith(target_prefix + "|") or text.startswith(target_prefix):
            a = heading.find_next("a", href=True)
            if a:
                return a["href"], text
    return None, None


def fetch_intention(detail_url):
    html = get(detail_url)
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            title = og_title["content"]

    intention = ""
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if og_desc and og_desc.get("content"):
        intention = og_desc["content"].strip()
    if not intention:
        desc = soup.find("meta", attrs={"name": "description"})
        if desc and desc.get("content"):
            intention = desc["content"].strip()

    return title, intention


def try_fill_year(data, year):
    """해당 연도의 archive 페이지를 한 번만 불러와, 비어 있는 달들을 채운다."""
    year_key = str(year)
    year_data = data.setdefault(year_key, {})

    missing_months = [m for m in range(1, 13) if str(m) not in year_data]
    if not missing_months:
        print(f"[{year}] 이미 12개월 모두 채워져 있어 건너뜀", file=sys.stderr)
        return False

    archive_url = f"https://thepopevideo.org/videos-{year}/?lang=ko"
    try:
        archive_html = get(archive_url)
    except Exception as e:
        print(f"[{year}] archive 페이지 조회 실패:", repr(e), file=sys.stderr)
        return False

    print(f"[{year}] archive 응답 길이: {len(archive_html)}자, 빈 달: {missing_months}", file=sys.stderr)

    changed = False
    for month in missing_months:
        try:
            detail_href, heading_text = find_month_link(archive_html, month)
        except Exception as e:
            print(f"  [{year}-{month}] 헤딩 검색 실패:", repr(e), file=sys.stderr)
            continue

        if not detail_href:
            print(f"  [{year}-{month}] 아직 게시되지 않음 (건너뜀)", file=sys.stderr)
            continue

        if detail_href.startswith("/"):
            detail_href = "https://thepopevideo.org" + detail_href

        try:
            title, intention = fetch_intention(detail_href)
        except Exception as e:
            print(f"  [{year}-{month}] 상세페이지 조회 실패:", repr(e), file=sys.stderr)
            continue

        if not intention:
            print(f"  [{year}-{month}] 기도지향 문장 추출 실패 (건너뜀)", file=sys.stderr)
            continue

        clean_title = title
        if heading_text and "|" in heading_text:
            clean_title = heading_text.split("|", 1)[1].strip()

        year_data[str(month)] = {"title": clean_title or title, "body": intention}
        print(f"  [{year}-{month}] 저장됨: {clean_title or title}", file=sys.stderr)
        changed = True

    return changed


def main():
    now = datetime.now(KST)
    data = load_existing()

    changed = False
    # 올해와 내년 모두 확인 — 다음 해 자료가 언제 올라오든 자동으로 채워진다.
    for year in (now.year, now.year + 1):
        if try_fill_year(data, year):
            changed = True

    if not changed:
        print("변경 사항 없음.", file=sys.stderr)
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"저장 완료 -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
