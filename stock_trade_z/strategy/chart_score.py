"""K-line chart scoring (four weighted dimensions)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from stock_trade_z.core.parallel_utils import parallel_select_helper

# Weights aligned with the former chart-scoring rubric (trend/position/volume/abnormal)
W_TREND = 0.20
W_POSITION = 0.20
W_VOLUME = 0.30
W_ABNORMAL = 0.30

PASS_MIN = 4.0
WATCH_MIN = 3.2
DEFAULT_PASS_THRESHOLD = PASS_MIN


@dataclass
class ChartScoreResult:
    code: str
    trend_structure: float
    price_position: float
    volume_behavior: float
    previous_abnormal_move: float
    total_score: float
    verdict: str
    signal_type: str
    comment: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ma_slope(series: pd.Series, days: int = 5) -> float:
    s = series.dropna()
    if len(s) < days + 1:
        return 0.0
    base = float(s.iloc[-days - 1])
    if base <= 0:
        return 0.0
    return float((s.iloc[-1] - s.iloc[-days - 1]) / base)


class ChartScoreSelector:
    """Score a stock chart on four dimensions (1–5) from daily OHLCV."""

    def __init__(
        self,
        *,
        min_bars: int = 60,
        lookback: int = 120,
        swing_lookback: int = 40,
        pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    ) -> None:
        self.min_bars = int(min_bars)
        self.lookback = int(lookback)
        self.swing_lookback = int(swing_lookback)
        self.pass_threshold = float(pass_threshold)

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        result = self.score("_", hist)
        return result is not None and result.total_score >= self.pass_threshold

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tail = max(self.min_bars, self.lookback) + 5
        tasks = [
            (code, df[df["date"] <= date].tail(tail))
            for code, df in data.items()
            if not df[df["date"] <= date].empty
        ]
        return parallel_select_helper(self, tasks)

    def score(self, code: str, hist: pd.DataFrame) -> ChartScoreResult | None:
        df = self._prepare(hist)
        if df is None or len(df) < self.min_bars:
            return None

        trend = self._score_trend(df)
        position = self._score_position(df)
        volume = self._score_volume(df)
        abnormal = self._score_abnormal_move(df)

        if volume <= 1.0:
            total = 1.0
            verdict = "FAIL"
        else:
            total = round(
                W_TREND * trend + W_POSITION * position + W_VOLUME * volume + W_ABNORMAL * abnormal,
                1,
            )
            if total >= self.pass_threshold:
                verdict = "PASS"
            elif total >= WATCH_MIN:
                verdict = "WATCH"
            else:
                verdict = "FAIL"

        signal = self._signal_type(trend, position, volume, abnormal, verdict)
        comment = self._build_comment(trend, position, volume, abnormal, signal)

        return ChartScoreResult(
            code=code,
            trend_structure=trend,
            price_position=position,
            volume_behavior=volume,
            previous_abnormal_move=abnormal,
            total_score=total,
            verdict=verdict,
            signal_type=signal,
            comment=comment,
        )

    @staticmethod
    def _prepare(hist: pd.DataFrame) -> pd.DataFrame | None:
        if hist is None or hist.empty:
            return None
        df = hist.copy()
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                return None
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["close", "volume"])
        if df.empty:
            return None
        return df.reset_index(drop=True)

    def _score_trend(self, df: pd.DataFrame) -> float:
        close = df["close"]
        ma5 = close.rolling(5, min_periods=5).mean()
        ma10 = close.rolling(10, min_periods=10).mean()
        ma20 = close.rolling(20, min_periods=20).mean()
        ma60 = close.rolling(60, min_periods=60).mean()

        c = float(close.iloc[-1])
        m5, m10, m20 = float(ma5.iloc[-1]), float(ma10.iloc[-1]), float(ma20.iloc[-1])
        m60 = float(ma60.iloc[-1]) if pd.notna(ma60.iloc[-1]) else m20

        s5, s10, s20 = _ma_slope(ma5), _ma_slope(ma10), _ma_slope(ma20)

        if m5 > m10 > m20 and c > m20 and s5 > 0 and s10 > 0:
            if s20 > 0 and m20 >= m60:
                return 5.0
            return 4.0
        if m5 > m10 and c > m10 and s10 >= 0:
            return 3.0
        if abs(m5 - m10) / max(m10, 1e-9) < 0.02 or abs(m10 - m20) / max(m20, 1e-9) < 0.02:
            return 2.0
        if m5 < m10 < m20 or s10 < 0 or s20 < 0:
            return 1.0
        return 2.0

    def _score_position(self, df: pd.DataFrame) -> float:
        win = df.tail(self.lookback)
        close = win["close"]
        c = float(close.iloc[-1])
        hi = float(close.max())
        lo = float(close.min())
        if hi <= lo:
            return 3.0

        pos = (c - lo) / (hi - lo)
        ma20 = float(close.rolling(20, min_periods=20).mean().iloc[-1])
        dist_ma = (c / ma20 - 1.0) if ma20 > 0 else 0.0

        recent_high = float(close.tail(20).max())
        dist_high = (recent_high - c) / recent_high if recent_high > 0 else 0.0

        if pos <= 0.45 and dist_ma < 0.08 and c >= recent_high * 0.98:
            return 5.0
        if 0.35 <= pos <= 0.65 and dist_ma < 0.15:
            return 4.0
        if dist_high <= 0.05:
            return 3.0
        if pos >= 0.75 or dist_ma > 0.25:
            return 2.0
        if pos >= 0.88 or dist_ma > 0.35:
            return 1.0
        return 3.0

    def _score_volume(self, df: pd.DataFrame) -> float:
        win = df.tail(self.swing_lookback)
        if len(win) < 10:
            return 3.0

        close = win["close"].to_numpy(dtype=float)
        vol = win["volume"].to_numpy(dtype=float)
        open_ = win["open"].to_numpy(dtype=float)

        min_i = int(np.argmin(close))
        if min_i >= len(close) - 4:
            return 3.0

        peak_i = int(np.argmax(close[min_i:])) + min_i
        if peak_i <= min_i:
            return 3.0

        up_slice = slice(min_i, peak_i + 1)
        down_slice = slice(peak_i, len(close))

        up_vol = float(np.mean(vol[up_slice])) if peak_i > min_i else 0.0
        down_vol = float(np.mean(vol[down_slice])) if peak_i < len(close) - 1 else up_vol
        base_vol = float(np.mean(vol[max(0, min_i - 10) : min_i])) or up_vol or 1.0

        max_vol_i = int(np.argmax(vol))
        max_on_down = max_vol_i >= peak_i and close[max_vol_i] < open_[max_vol_i]

        first_red = None
        for i in range(peak_i + 1, len(close)):
            if close[i] < open_[i]:
                first_red = i
                break

        shrink_ok = False
        if first_red is not None and peak_i < first_red:
            up_bar_vol = float(vol[peak_i])
            red_vol = float(vol[first_red])
            shrink_ok = red_vol <= up_bar_vol * 0.55

        if up_vol > base_vol * 1.3 and shrink_ok and not max_on_down:
            return 5.0
        if up_vol > down_vol * 1.1 and not max_on_down:
            return 4.0
        if abs(up_vol - down_vol) / max(up_vol, 1e-9) < 0.15:
            return 3.0
        if down_vol > up_vol * 1.05 or max_on_down:
            return 2.0
        if max_on_down and down_vol > up_vol * 1.3:
            return 1.0
        return 2.0

    def _score_abnormal_move(self, df: pd.DataFrame) -> float:
        win = df.tail(self.lookback)
        if len(win) < 30:
            return 2.0

        close = win["close"]
        vol = win["volume"]
        open_ = win["open"]
        avg_vol = vol.rolling(20, min_periods=10).mean()

        pct = close.pct_change()
        yang = (close > open_) & (pct > 0.03)
        vol_spike = vol > avg_vol * 2.0
        signals = yang & vol_spike
        rally_from_start = (
            float((close.iloc[-1] / close.iloc[0] - 1) * 100) if close.iloc[0] > 0 else 0.0
        )

        sig_positions = np.where(signals.to_numpy())[0]
        if len(sig_positions) == 0:
            if rally_from_start > 100:
                return 1.0
            if rally_from_start > 50:
                return 2.0
            return 2.0
        pos = int(sig_positions[-1])
        start_price = float(close.iloc[max(0, pos - 5)])
        end_price = float(close.iloc[-1])
        rally_pct = (end_price / start_price - 1) * 100 if start_price > 0 else 0

        av = (
            float(avg_vol.iloc[pos])
            if pd.notna(avg_vol.iloc[pos]) and avg_vol.iloc[pos] > 0
            else 1.0
        )
        vol_ratio = float(vol.iloc[pos] / av)

        prior_high = float(close.iloc[: pos + 1].max())
        broke = float(close.iloc[pos]) >= prior_high * 0.995

        max_vol_pos = int(np.argmax(vol.to_numpy()))
        max_vol_bear = float(close.iloc[max_vol_pos]) < float(open_.iloc[max_vol_pos])

        if rally_pct > 100 or (max_vol_bear and rally_pct > 50):
            return 1.0
        if vol_ratio >= 2.5 and broke and rally_pct < 50:
            return 5.0
        if vol_ratio >= 2.0 and rally_pct < 50:
            return 4.0
        if vol_ratio >= 1.5 and rally_pct < 50:
            return 3.0
        return 2.0

    @staticmethod
    def _signal_type(
        trend: float,
        position: float,
        volume: float,
        abnormal: float,
        verdict: str,
    ) -> str:
        if volume <= 2.0 or (trend <= 2.0 and position <= 2.5):
            return "distribution_risk"
        if trend >= 4.0 and volume >= 3.5 and abnormal >= 3.0 and verdict != "FAIL":
            return "trend_start"
        return "rebound"

    @staticmethod
    def _build_comment(
        trend: float,
        position: float,
        volume: float,
        abnormal: float,
        signal: str,
    ) -> str:
        trend_txt = "均线多头改善" if trend >= 4 else "趋势偏弱或空头" if trend <= 2 else "趋势震荡"
        vol_txt = "上涨放量回调缩量" if volume >= 4 else "量价偏弱" if volume <= 2 else "量价中性"
        ab_txt = (
            "前期有放量异动"
            if abnormal >= 4
            else "异动不明显"
            if abnormal <= 2
            else "存在一定放量上涨"
        )
        pos_txt = (
            "上方仍有空间" if position >= 4 else "接近高位压力" if position <= 2 else "位置中性"
        )
        risk = (
            "波段启动观察"
            if signal == "trend_start"
            else "超跌反弹观察"
            if signal == "rebound"
            else "注意出货风险"
        )
        return f"{trend_txt}，{vol_txt}，{ab_txt}，{pos_txt}，{risk}。"

    def build_suggestion(
        self,
        results: list[ChartScoreResult],
        *,
        pick_date: str,
        min_score: float | None = None,
    ) -> dict[str, Any]:
        threshold = self.pass_threshold if min_score is None else float(min_score)
        passed = [r for r in results if r.total_score >= threshold]
        passed.sort(key=lambda r: r.total_score, reverse=True)
        excluded = [r.code for r in results if r.total_score < threshold]

        recommendations = [
            {
                "rank": i + 1,
                "code": r.code,
                "verdict": r.verdict,
                "total_score": r.total_score,
                "signal_type": r.signal_type,
                "comment": r.comment,
                "trend_structure": r.trend_structure,
                "price_position": r.price_position,
                "volume_behavior": r.volume_behavior,
                "previous_abnormal_move": r.previous_abnormal_move,
            }
            for i, r in enumerate(passed)
        ]

        return {
            "date": pick_date,
            "min_score_threshold": threshold,
            "total_reviewed": len(results),
            "recommendations": recommendations,
            "excluded": excluded,
        }
