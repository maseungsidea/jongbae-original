"""
CLI 진입점 (run.py)

커맨드라인에서 직접 스크리너, 단일 종목 분석, 스케줄러를 실행할 수 있는
편의 인터페이스를 제공합니다.

사용법:
  python run.py screener                      # 전체 마켓 스크리닝
  python run.py analyze --code 005930         # 단일 종목 분석 (삼성전자)
  python run.py schedule                      # 스케줄러 시작
  python run.py market-gate                   # 마켓 게이트 분석

옵션:
  --capital      투자 자산 (기본: 50,000,000원)
  --markets      마켓 목록 (기본: KOSPI KOSDAQ)
  --top-n        시장별 상위 N개 (기본: 30)
"""

import argparse
import asyncio
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def cmd_screener(args) -> None:
    """전체 마켓 스크리닝 실행"""
    from engine.generator import run_screener, save_result_to_json
    logger.info(f"스크리닝 시작: {args.markets}, 자산={args.capital:,}원, top_n={args.top_n}")
    result = asyncio.run(run_screener(
        capital=args.capital,
        markets=args.markets,
        top_n=args.top_n,
    ))
    save_result_to_json(result)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


def cmd_analyze(args) -> None:
    """단일 종목 분석"""
    if not args.code:
        logger.error("--code 옵션이 필요합니다.")
        sys.exit(1)

    from engine.generator import analyze_single_stock_by_code
    signal = asyncio.run(analyze_single_stock_by_code(args.code, capital=args.capital))

    if signal is None:
        logger.warning(f"{args.code}: 시그널 없음 (Grade C 또는 데이터 없음)")
        return

    print(json.dumps(signal.to_dict(), ensure_ascii=False, indent=2))


def cmd_schedule(args) -> None:
    """스케줄러 시작"""
    from scheduler import main
    main()


def cmd_market_gate(args) -> None:
    """마켓 게이트 실행"""
    from market_gate import run_kr_market_gate
    result = run_kr_market_gate()
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="종가배팅 CLI")
    parser.add_argument("--capital", type=float, default=50_000_000, help="투자 자산 (원)")
    parser.add_argument("--markets", nargs="+", default=["KOSPI", "KOSDAQ"])
    parser.add_argument("--top-n", type=int, default=30, dest="top_n")
    parser.add_argument("--code", type=str, help="종목코드 (analyze 명령 시 필요)")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("screener", help="전체 마켓 스크리닝")
    subparsers.add_parser("analyze", help="단일 종목 분석")
    subparsers.add_parser("schedule", help="스케줄러 시작")
    subparsers.add_parser("market-gate", help="마켓 게이트 분석")

    args = parser.parse_args()

    cmd_map = {
        "screener": cmd_screener,
        "analyze": cmd_analyze,
        "schedule": cmd_schedule,
        "market-gate": cmd_market_gate,
    }

    if args.command not in cmd_map:
        parser.print_help()
        sys.exit(0)

    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
