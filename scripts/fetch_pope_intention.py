# -*- coding: utf-8 -*-
"""
교황님의 기도지향(이달의 기도지향)을 The Pope Video 공식 사이트(thepopevideo.org,
교황기도네트워크Pope's Worldwide Prayer Network 공식 프로젝트, 바티칸 미디어 협력)의
한국어판에서 가져와 data/pope_intention.json 으로 저장한다.

동작 방식:
1. https://thepopevideo.org/videos-{year}/?lang=ko 에서 그 해 각 달의 링크 목록을 가져온다.
2. 그중 이번 달에 해당하는 링크를 찾는다.
3. 그 상세 페이지에서 제목과 공식 한 줄 기도지향 문장(og:description)을 가져온다.
   (전체 기도문 원문은 페이지 구조가 자주 바뀔 수 있어 안정적으로 뽑기 어려워
   가장 핵심적인 공식 한 줄 지향 문장만 가져온다. 전체 내용은 원문 링크로 연결한다.)

GitHub Actions에서 매일 실행하되, 내용이 실제로 바뀔 때만 커밋된다(이번 달 항목이
아직 사이트에 올라오지 않았으면 지난 값을 그대로 유지한다).
"""

import json
import re
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
OUT = Path(__file__).resolve().parent.parent / "data" / "pope_intention.json"

SESSION = requests.Session()


def get(url):
    r = SESSION.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def find_month_link(year, month):
    """videos-{year} 아카이브 페이지에서 이번 달 항목의 상세페이지 링크를 찾는다."""
    url = f"https://thepopevideo.org/videos-{year}/?lang=ko"
    html = get(url)
    print(f"[진단] 아카이브 페이지 응답 길이: {len(html)}자", file=sys.stderr)
    soup = BeautifulSoup(html, "html.parser")

    # 'N월 | 제목' 형태의 헤딩을 찾고, 그 근처의 링크를 매칭한다.
    target_prefix = f"{month}월"
    for heading in soup.find_all(["h2", "h3", "h4"]):
        text = heading.get_text(strip=True)
        if text.startswith(target_prefix + " ") or text.startswith(target_prefix + "|") or text.startswith(target_prefix):
            # 이 헤딩 바로 다음에 나오는 링크를 찾는다 (같은 블록 내 "Watch Video" 등)
            a = heading.find_next("a", href=True)
            if a:
                print(f"[진단] {month}월 헤딩 매칭: '{text}' -> {a['href']}", file=sys.stderr)
                return a["href"], text
    print(f"[진단] {month}월에 해당하는 헤딩을 찾지 못함", file=sys.stderr)
    return None, None


def fetch_intention(detail_url):
    html = get(detail_url)
    print(f"[진단] 상세페이지 응답 길이: {len(html)}자", file=sys.stderr)
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


def main():
    now = datetime.now(KST)
    year, month = now.year, now.month

    print(f"[진단] 대상: {year}년 {month}월", file=sys.stderr)

    try:
        detail_url, heading_text = find_month_link(year, month)
    except Exception as e:
        print("아카이브 페이지 조회 실패:", repr(e), file=sys.stderr)
        detail_url, heading_text = None, None

    if not detail_url:
        print("이번 달 항목을 찾지 못해 종료합니다 (기존 데이터 유지).", file=sys.stderr)
        return

    # 상대경로일 경우 보정
    if detail_url.startswith("/"):
        detail_url = "https://thepopevideo.org" + detail_url

    try:
        title, intention = fetch_intention(detail_url)
    except Exception as e:
        print("상세페이지 조회 실패:", repr(e), file=sys.stderr)
        return

    if not intention:
        print("기도지향 문장을 추출하지 못해 종료합니다 (기존 데이터 유지).", file=sys.stderr)
        return

    # 헤딩 텍스트에서 'N월 | 제목' 중 제목 부분만 추출 (더 깔끔한 경우가 많아 우선 사용)
    clean_title = title
    if heading_text and "|" in heading_text:
        clean_title = heading_text.split("|", 1)[1].strip()

    out = {
        "year": year,
        "month": month,
        "title": clean_title or title,
        "intention": intention,
        "source_url": detail_url,
        "updated": now.strftime("%Y-%m-%d %H:%M"),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"완료: {year}년 {month}월 '{out['title']}' 저장 -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
