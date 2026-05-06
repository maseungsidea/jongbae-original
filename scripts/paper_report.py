"""페이퍼 트래킹 결과 vs 백테 기대치 비교.

signals_log.csv 의 exited 트레이드를 sw_pe_t8 기대치
(EV +1.656%, WR 55.9%, RR 1.26) 와 비교한다.

사용:
    python3 scripts/paper_report.py
    python3 scripts/paper_report.py --since 2026-05-06
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "data" / "signals_log.csv"

# sw_pe_t8 (현 운영 default) 백테 기대치
EXPECTED = {"label": "sw_pe_t8", "ev_pct": 1.656, "wr": 0.559, "rr": 1.26}
FEE_RT = 0.21  # round-trip 수수료/세금 %


def status_breakdown(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    return df["status"].value_counts().to_dict()


def reason_breakdown(df: pd.DataFrame) -> dict:
    closed = df[df["status"] == "exited"]
    if closed.empty:
        return {}
    return closed["exit_reason"].value_counts().to_dict()


def stats(df: pd.DataFrame) -> dict | None:
    """exited 행만으로 WR/EV/RR 계산. 백테와 동일하게 round-trip fee 차감."""
    closed = df[df["status"] == "exited"].copy()
    if closed.empty:
        return None
    closed["return_pct"] = closed["return_pct"].astype(float)
    # signal_tracker 의 return_pct 는 gross. 백테 기대치는 net 이므로 fee 차감.
    closed["net_pct"] = closed["return_pct"] - FEE_RT
    wins = closed[closed["net_pct"] > 0]
    losses = closed[closed["net_pct"] <= 0]
    n = len(closed)
    wr = len(wins) / n if n else 0.0
    avg_win = wins["net_pct"].mean() if len(wins) else 0.0
    avg_loss = losses["net_pct"].mean() if len(losses) else 0.0
    ev = closed["net_pct"].mean()
    rr = abs(avg_win / avg_loss) if avg_loss else 0.0
    return {
        "n": n, "wr": wr, "ev_pct": ev, "rr": rr,
        "avg_win": avg_win, "avg_loss": avg_loss,
        "best": closed["net_pct"].max(), "worst": closed["net_pct"].min(),
    }


def format_report(df: pd.DataFrame, since: str | None) -> str:
    out: list[str] = []
    out.append(f"[paper_report] signals_log.csv ({len(df)} rows)")
    if since:
        out.append(f"  since: {since}")
    if df.empty:
        out.append("  (no signals yet)")
        return "\n".join(out)

    sb = status_breakdown(df)
    out.append(f"  status: {sb}")
    rb = reason_breakdown(df)
    if rb:
        out.append(f"  exit_reason: {rb}")

    s = stats(df)
    if s is None:
        out.append("  (no exited trades)")
        return "\n".join(out)

    out.append("")
    out.append("─ 실거래 (net, fee 0.21% 차감) ─")
    out.append(f"  trades n = {s['n']}  WR = {s['wr']*100:.1f}%  EV = {s['ev_pct']:+.3f}%  RR = {s['rr']:.2f}")
    out.append(f"  avgWin = {s['avg_win']:+.2f}%  avgLoss = {s['avg_loss']:+.2f}%")
    out.append(f"  best = {s['best']:+.1f}%  worst = {s['worst']:+.1f}%")

    out.append("")
    out.append(f"─ 백테 기대치 ({EXPECTED['label']}) ─")
    out.append(
        f"  WR = {EXPECTED['wr']*100:.1f}%  EV = {EXPECTED['ev_pct']:+.3f}%  RR = {EXPECTED['rr']:.2f}"
    )

    out.append("")
    out.append("─ 갭 (실거래 − 백테) ─")
    ev_gap = s["ev_pct"] - EXPECTED["ev_pct"]
    wr_gap = (s["wr"] - EXPECTED["wr"]) * 100
    rr_gap = s["rr"] - EXPECTED["rr"]
    out.append(f"  ΔEV = {ev_gap:+.3f}%pt  ΔWR = {wr_gap:+.1f}%pt  ΔRR = {rr_gap:+.2f}")
    if s["n"] < 30:
        out.append(f"  ⚠ n={s['n']} < 30 → 통계적 confidence 부족, 참고용")
    return "\n".join(out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--since", help="YYYY-MM-DD 이후 signal_date 만 필터")
    args = p.parse_args()

    if not LOG_PATH.exists():
        print(f"[paper_report] {LOG_PATH} 없음 → scheduler 가 아직 1번도 안 돌았음")
        return
    df = pd.read_csv(LOG_PATH, dtype={"ticker": str})
    if args.since:
        df = df[df["signal_date"] >= args.since].copy()
    print(format_report(df, args.since))


if __name__ == "__main__":
    main()
