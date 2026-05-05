"""네이버 금융 외인/기관 일별 순매매 크롤러.

KRX pykrx 수급 API 가 차단된 동안 백테/운영용 supply 데이터 수집을 대체한다.
URL : https://finance.naver.com/item/frgn.naver?code=<6자리>&page=<N>
페이지당 약 20거래일치 행, 컬럼: 날짜 / 종가 / 전일비 / 등락률 / 거래량 /
                                  기관 순매매량 / 외국인 순매매량 / 외국인 보유주수 / 보유율

저장: data/naver_supply.csv  (date, ticker, inst_net, foreign_net)

사용:
    python3 scripts/fetch_naver_supply.py --tickers 005930,000660 \
        --start 2026-04-01 --end 2026-05-04
    python3 scripts/fetch_naver_supply.py --from-trades data/backtests/sw_pe_t8.json \
        --start 2024-08-01 --end 2026-04-30
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "naver_supply.csv"
HEADERS = {"User-Agent": "Mozilla/5.0"}
SLEEP_SEC = 0.30
TABLE_RE = re.compile(r'<table summary="외국인.*?</table>', re.DOTALL)
ROW_RE = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
CELL_RE = re.compile(r'<t[hd][^>]*>(.*?)</t[hd]>', re.DOTALL)
DATE_RE = re.compile(r'\d{4}\.\d{2}\.\d{2}')


def _parse_int(s: str) -> int:
    s = s.replace(",", "").replace("+", "").strip()
    if not s or s == "-":
        return 0
    return int(s)


def fetch_page(ticker: str, page: int) -> list[dict]:
    """단일 페이지 파싱. 비어있거나 표 미발견 시 [] 반환."""
    url = f"https://finance.naver.com/item/frgn.naver?code={ticker}&page={page}"
    req = urllib.request.Request(url, headers=HEADERS)
    html = urllib.request.urlopen(req, timeout=15).read().decode("euc-kr", errors="ignore")
    m = TABLE_RE.search(html)
    if not m:
        return []
    out: list[dict] = []
    for r in ROW_RE.findall(m.group(0)):
        cells = [re.sub(r'<[^>]*>|&nbsp;', '', c).strip() for c in CELL_RE.findall(r)]
        cells = [c for c in cells if c]
        if len(cells) < 9 or not DATE_RE.match(cells[0]):
            continue
        d = datetime.strptime(cells[0], "%Y.%m.%d").date()
        out.append({
            "date": d,
            "ticker": ticker,
            "inst_net": _parse_int(cells[5]),
            "foreign_net": _parse_int(cells[6]),
        })
    return out


def fetch_ticker(
    ticker: str,
    start: date,
    end: date,
    max_pages: int = 30,
) -> list[dict]:
    """페이지를 1부터 증가시키며 start 이전 데이터까지 수집."""
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        try:
            page_rows = fetch_page(ticker, page)
        except Exception as e:
            print(f"  [ERR] {ticker} page={page}: {e}", file=sys.stderr)
            break
        if not page_rows:
            break
        any_in_range = False
        for r in page_rows:
            if r["date"] < start:
                continue
            if r["date"] > end:
                continue
            rows.append(r)
            any_in_range = True
        # 페이지의 가장 오래된 row 가 start 보다 이전이면 종료
        if page_rows[-1]["date"] < start:
            break
        time.sleep(SLEEP_SEC)
    return rows


def merge_into_parquet(new_rows: list[dict]) -> int:
    """기존 parquet 와 합치고 (date,ticker) 중복 제거. 새로 추가된 행 수 반환."""
    if not new_rows:
        return 0
    df_new = pd.DataFrame(new_rows)
    df_new["date"] = pd.to_datetime(df_new["date"])
    if DATA_PATH.exists():
        df_old = pd.read_csv(DATA_PATH, dtype={"ticker": str}, parse_dates=["date"])
        before = len(df_old)
        df = pd.concat([df_old, df_new], ignore_index=True)
        df = df.drop_duplicates(subset=["date", "ticker"], keep="last")
        added = len(df) - before
    else:
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        df = df_new.drop_duplicates(subset=["date", "ticker"], keep="last")
        added = len(df)
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    df.to_csv(DATA_PATH, index=False)
    return added


def tickers_from_trades(json_path: Path) -> list[str]:
    blob = json.loads(json_path.read_text())
    seen: list[str] = []
    for t in blob.get("trades", []):
        code = str(t.get("ticker", "")).zfill(6)
        if code and code not in seen:
            seen.append(code)
    return seen


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tickers", help="콤마구분 6자리 코드 리스트")
    p.add_argument("--from-trades", help="백테 결과 JSON 에서 unique ticker 추출")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--max-pages", type=int, default=30)
    args = p.parse_args()

    if args.tickers:
        tickers = [t.strip().zfill(6) for t in args.tickers.split(",") if t.strip()]
    elif args.from_trades:
        tickers = tickers_from_trades(Path(args.from_trades))
    else:
        sys.exit("--tickers 또는 --from-trades 중 하나 필요")

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()

    print(f"[fetch] {len(tickers)} tickers, {start}~{end}")
    total_added = 0
    for i, t in enumerate(tickers, 1):
        rows = fetch_ticker(t, start, end, max_pages=args.max_pages)
        added = merge_into_parquet(rows)
        total_added += added
        print(f"  [{i}/{len(tickers)}] {t}: {len(rows)} rows ({added} new)")
    print(f"[done] +{total_added} rows → {DATA_PATH}")


if __name__ == "__main__":
    main()
