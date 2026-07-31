# -*- coding: utf-8 -*-
"""
한국천주교주교회의(CBCK) 공식 "한국 천주교 주소록"(directory.cbck.or.kr)에서
전국 16개 교구의 본당(성당) 정보(이름·주소·전화번호·홈페이지)를 가져와,
카카오 로컬 API로 주소를 위도/경도로 변환(지오코딩)한 뒤
data/parishes.json 으로 저장한다.

전국 성당 수가 많아(약 1,700여 개) 실행에 시간이 걸린다(대략 15~25분).
GitHub Actions에서 주(週) 단위로 실행하도록 설계되었다 — 본당 주소는 자주 바뀌지 않는다.

※ 저작권/출처: 본당 이름·주소·전화번호는 한국천주교주교회의가 공개 제공하는
   공식 온라인 주소록의 사실 정보(성당명, 주소, 전화번호)만 가져오며,
   페이지의 다른 서술형 소개文 등은 가져오지 않는다.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
from datetime import datetime

import requests
from bs4 import BeautifulSoup

BASE = "https://directory.cbck.or.kr/OnlineAddress/Catholic"
KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "parishes.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 남북분단 이전 교구(평양·함흥·덕원자치수도원구)는 현재 남한 내 실제 본당이 없어 제외.
DIOCESES = {
    "201000011": "서울대교구",
    "201000013": "춘천교구",
    "201000016": "대전교구",
    "201000017": "인천교구",
    "201000018": "수원교구",
    "201000019": "원주교구",
    "201000020": "의정부교구",
    "201000021": "대구대교구",
    "201000022": "부산교구",
    "201000023": "청주교구",
    "201000024": "마산교구",
    "201000025": "안동교구",
    "201000026": "광주대교구",
    "201000027": "전주교구",
    "201000028": "제주교구",
    "201000029": "군종교구",
}

KAKAO_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "").strip()
REQUEST_DELAY = 0.25  # 대상 서버에 부담을 주지 않도록 매 요청 사이 간격


def resolve_href(soup, page_url, href):
    """페이지에 <base> 태그가 있으면 그 기준으로, 없으면 페이지 자체 URL 기준으로 링크를 절대경로화."""
    base_tag = soup.find("base", href=True)
    effective_base = urljoin(page_url, base_tag["href"]) if base_tag else page_url
    return urljoin(effective_base, href)


SESSION = requests.Session()


def get(url, params=None):
    r = SESSION.get(url, headers=HEADERS, params=params, timeout=20)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def get_field(soup, label):
    """'대표주소' 같은 라벨 셀 옆의 값 셀 텍스트를 찾아 반환한다."""
    for cell in soup.find_all(["td", "th"]):
        if cell.get_text(strip=True) == label:
            nxt = cell.find_next_sibling(["td", "th"])
            if nxt:
                return nxt.get_text(strip=True)
    return ""


def list_parish_links(diocese_code):
    """교구 코드로 해당 교구의 본당 목록 페이지를 찾아 (이름, 상세페이지코드) 목록을 반환."""
    html = get(f"{BASE}/Diocese.aspx", params={"cgubn": "c", "gyogu": diocese_code, "char": "all"})
    print(f"    [진단] Diocese.aspx 응답 길이: {len(html)}자, 'Church.aspx' 포함 여부: {'Church.aspx' in html}", file=sys.stderr)
    soup = BeautifulSoup(html, "html.parser")

    church_link = None
    for a in soup.find_all("a", href=True):
        if "Church.aspx" in a["href"] and f"gyogu={diocese_code}" in a["href"]:
            church_link = a["href"]
            break
    if not church_link:
        print(f"    [진단] 본당 목록 링크(Church.aspx)를 찾지 못함", file=sys.stderr)
        return []

    base_tag = soup.find("base", href=True)
    print(f"    [진단] 원본 church_link href: {church_link!r} / <base> 태그: {base_tag['href'] if base_tag else '없음'}", file=sys.stderr)

    diocese_page_url = f"{BASE}/Diocese.aspx"
    church_url = resolve_href(soup, diocese_page_url, church_link)

    # 안전장치: 어떤 경로 조합 방식이든 'OnlineAddress/Catholic'이 중복되면 강제로 한 번만 남긴다.
    church_url = re.sub(r"(OnlineAddress/Catholic/)(?:OnlineAddress/Catholic/)+", r"\1", church_url)

    print(f"    [진단] 본당 목록 URL: {church_url}", file=sys.stderr)
    html2 = get(church_url)
    print(f"    [진단] Church.aspx 응답 길이: {len(html2)}자, 'DetailInfo.aspx' 포함 여부: {'DetailInfo.aspx' in html2}", file=sys.stderr)
    soup2 = BeautifulSoup(html2, "html.parser")

    results = []
    seen_codes = set()
    for a in soup2.find_all("a", href=True):
        href = a["href"]
        if "DetailInfo.aspx" in href and "cgubn=c" in href:
            m = re.search(r"code=(\d+)", href)
            if not m:
                continue
            code = m.group(1)
            if code in seen_codes:
                continue
            seen_codes.add(code)
            name = a.get_text(strip=True)
            if name:
                results.append((name, code))
    return results


def fetch_parish_detail(diocese_code, code):
    html = get(f"{BASE}/DetailInfo.aspx", params={
        "cgubn": "c", "gubn": "4", "gyogu": diocese_code, "code": code, "gubn2": "all", "char": "all",
    })
    soup = BeautifulSoup(html, "html.parser")

    name = get_field(soup, "한글명칭")
    address = get_field(soup, "대표주소")
    phone = get_field(soup, "대표 전화 번호")
    homepage = get_field(soup, "홈페이지 주소")

    # 주소 앞의 우편번호(5자리 숫자)는 지오코딩에 방해가 될 수 있어 제거
    address_clean = re.sub(r"^\d{5}\s*", "", address).strip()

    return {
        "name": name,
        "address": address_clean,
        "phone": phone,
        "homepage": homepage,
    }


def geocode_kakao(address):
    """카카오 로컬 API로 주소를 위도/경도로 변환. 실패 시 (None, None)."""
    if not KAKAO_API_KEY or not address:
        return None, None
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    try:
        r = requests.get(
            "https://dapi.kakao.com/v2/local/search/address.json",
            headers=headers, params={"query": address}, timeout=10,
        )
        if r.status_code == 200:
            docs = r.json().get("documents", [])
            if docs:
                return float(docs[0]["y"]), float(docs[0]["x"])  # y=위도, x=경도
        else:
            print(f"    [진단] 주소 지오코딩 실패 status={r.status_code} body={r.text[:200]}", file=sys.stderr)
    except Exception as e:
        print("address geocode failed:", address, e, file=sys.stderr)

    # 도로명주소 검색이 실패하면 키워드 검색으로 재시도
    try:
        r = requests.get(
            "https://dapi.kakao.com/v2/local/search/keyword.json",
            headers=headers, params={"query": address}, timeout=10,
        )
        if r.status_code == 200:
            docs = r.json().get("documents", [])
            if docs:
                return float(docs[0]["y"]), float(docs[0]["x"])
        else:
            print(f"    [진단] 키워드 지오코딩 실패 status={r.status_code} body={r.text[:200]}", file=sys.stderr)
    except Exception as e:
        print("keyword geocode failed:", address, e, file=sys.stderr)

    return None, None


def main():
    if not KAKAO_API_KEY:
        print("경고: KAKAO_REST_API_KEY가 설정되어 있지 않습니다. 좌표 없이는 결과가 비어 있게 됩니다.",
              file=sys.stderr)
    else:
        masked = KAKAO_API_KEY[:4] + "..." + KAKAO_API_KEY[-4:] if len(KAKAO_API_KEY) > 8 else "***"
        print(f"[진단] KAKAO_REST_API_KEY 감지됨 (길이 {len(KAKAO_API_KEY)}자, {masked})", file=sys.stderr)

    all_parishes = []

    for code, diocese_name in DIOCESES.items():
        print(f"[{diocese_name}] 본당 목록 조회 중...", file=sys.stderr)
        try:
            links = list_parish_links(code)
        except Exception as e:
            print(f"[{diocese_name}] 목록 조회 실패:", repr(e), file=sys.stderr)
            continue
        time.sleep(REQUEST_DELAY)

        print(f"[{diocese_name}] 본당 {len(links)}곳 발견", file=sys.stderr)

        diocese_ok = 0
        for list_name, parish_code in links:
            try:
                detail = fetch_parish_detail(code, parish_code)
            except Exception as e:
                print(f"  상세 조회 실패 ({list_name}):", repr(e), file=sys.stderr)
                time.sleep(REQUEST_DELAY)
                continue
            time.sleep(REQUEST_DELAY)

            name = detail["name"] or list_name
            address = detail["address"]
            if not address:
                print(f"  주소 없음, 제외: {name}", file=sys.stderr)
                continue

            lat, lng = geocode_kakao(address)
            time.sleep(REQUEST_DELAY)

            if lat is None or lng is None:
                print(f"  지오코딩 실패, 제외: {name} ({address})", file=sys.stderr)
                continue

            diocese_ok += 1
            all_parishes.append({
                "name": name,
                "diocese": diocese_name,
                "address": address,
                "phone": detail["phone"],
                "homepage": detail["homepage"],
                "lat": lat,
                "lng": lng,
            })
        print(f"[{diocese_name}] 완료: {diocese_ok}/{len(links)}곳 저장됨", file=sys.stderr)

    out = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "count": len(all_parishes),
        "source": "한국천주교주교회의 한국 천주교 주소록 (directory.cbck.or.kr)",
        "parishes": all_parishes,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"완료: 총 {len(all_parishes)}곳 저장 -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
