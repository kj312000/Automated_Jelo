"""
Aggregates historical performance metrics and provides analytics data.
"""
from typing import Any
import structlog

log = structlog.get_logger(__name__)


class AnalyticsService:
    def compute_metrics(self, trades: list[dict]) -> dict:
        closed = [t for t in trades if t.get("status") == "CLOSED"]
        if not closed:
            return self._empty_metrics()

        winners = [t for t in closed if t.get("pnl", 0) > 0]
        losers = [t for t in closed if t.get("pnl", 0) <= 0]
        pnls = [t.get("pnl", 0) for t in closed]
        holds = [t.get("duration_seconds", 0) for t in closed]
        slippages = [t.get("slippage", 0) for t in closed]
        mfes = [t.get("mfe", 0) for t in closed]
        maes = [t.get("mae", 0) for t in closed]

        total_pnl = sum(pnls)
        win_rate = len(winners) / len(closed) if closed else 0.0
        avg_win = sum(t.get("pnl", 0) for t in winners) / len(winners) if winners else 0.0
        avg_loss = sum(t.get("pnl", 0) for t in losers) / len(losers) if losers else 0.0
        profit_factor = (
            abs(avg_win * len(winners)) / abs(avg_loss * len(losers))
            if losers and avg_loss != 0 else float("inf")
        )

        # By exit reason
        exit_reasons: dict[str, int] = {}
        for t in closed:
            r = t.get("exit_reason", "UNKNOWN")
            exit_reasons[r] = exit_reasons.get(r, 0) + 1

        # Equity curve: cumulative pnl
        equity_curve = []
        running = 0.0
        for t in sorted(closed, key=lambda x: x.get("closed_at", 0)):
            running += t.get("pnl", 0)
            equity_curve.append({"t": t.get("closed_at", 0), "pnl": running})

        # Max drawdown
        peak = 0.0
        max_dd = 0.0
        for point in equity_curve:
            if point["pnl"] > peak:
                peak = point["pnl"]
            dd = peak - point["pnl"]
            if dd > max_dd:
                max_dd = dd

        return {
            "total_trades": len(closed),
            "winning": len(winners),
            "losing": len(losers),
            "win_rate": win_rate,
            "avg_pnl": total_pnl / len(closed),
            "total_pnl": total_pnl,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "avg_hold_seconds": sum(holds) / len(holds) if holds else 0.0,
            "avg_slippage": sum(slippages) / len(slippages) if slippages else 0.0,
            "avg_mfe": sum(mfes) / len(mfes) if mfes else 0.0,
            "avg_mae": sum(maes) / len(maes) if maes else 0.0,
            "max_drawdown": max_dd,
            "exit_reasons": exit_reasons,
            "equity_curve": equity_curve[-100:],  # last 100 points
            "pnl_distribution": self._pnl_distribution(pnls),
        }

    def _pnl_distribution(self, pnls: list[float]) -> list[dict]:
        if not pnls:
            return []
        mn = min(pnls)
        mx = max(pnls)
        if mn == mx:
            return [{"bucket": mn, "count": len(pnls)}]

        bucket_size = (mx - mn) / 10
        buckets: dict[float, int] = {}
        for p in pnls:
            b = round(mn + int((p - mn) / bucket_size) * bucket_size, 4)
            buckets[b] = buckets.get(b, 0) + 1

        return [{"bucket": k, "count": v} for k, v in sorted(buckets.items())]

    def _empty_metrics(self) -> dict:
        return {
            "total_trades": 0,
            "winning": 0,
            "losing": 0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "total_pnl": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "avg_hold_seconds": 0.0,
            "avg_slippage": 0.0,
            "avg_mfe": 0.0,
            "avg_mae": 0.0,
            "max_drawdown": 0.0,
            "exit_reasons": {},
            "equity_curve": [],
            "pnl_distribution": [],
        }


analytics_service = AnalyticsService()
