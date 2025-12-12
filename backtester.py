# backtester.py
import pandas as pd
import json
import os
import numpy as np  # 안전장치용 (필수는 아님)

SAVE_DIR = "backtest_results"
os.makedirs(SAVE_DIR, exist_ok=True)


class BacktestAgent:
    def __init__(self, initial_equity=10000.0):
        self.initial_equity = initial_equity

    def _to_unix_ms(self, ts_val):
        if isinstance(ts_val, pd.Timestamp):
            return int(ts_val.timestamp() * 1000)
        if str(type(ts_val)).endswith("datetime64"):
            return int(pd.Timestamp(ts_val).timestamp() * 1000)
        if isinstance(ts_val, (int, float)):
            if ts_val > 10**12:
                return int(ts_val)
            elif ts_val > 10**9:
                return int(ts_val * 1000)
            else:
                return int(ts_val * 1000)
        return int(pd.to_datetime(ts_val).timestamp() * 1000)

    def run_single_strategy(self, df_candles: pd.DataFrame, strategy_obj, strategy_id=None):
        df = df_candles.copy()
        df.columns = [c.lower() for c in df.columns]

        cols = df.columns.tolist()
        if len(cols) >= 5:
            df.rename(columns={
                cols[0]: 'ts', cols[1]: 'open', cols[2]: 'high',
                cols[3]: 'low', cols[4]: 'close'
            }, inplace=True)

        df = strategy_obj.calculate_signals(df)

        leverage = getattr(strategy_obj, 'leverage', 1.0)
        risk_pct = getattr(strategy_obj, 'risk_percent', 100.0) / 100.0

        print(f"[BACKTEST] 설정: Lev {leverage}x, Risk {risk_pct*100:.1f}%")

        equity = self.initial_equity          # ← 실제 자본 (청산할 때만 바뀜)
        equity_curve = []
        trade_markers = []
        equity_over_trades = []
        trade_num = 0

        position = 0
        entry_price = 0.0
        coin_qty = 0.0
        trade_highest = 0.0
        trade_lowest = 0.0

        start_ts = self._to_unix_ms(df.iloc[0]['ts'])
        equity_curve.append({"time": start_ts, "value": equity, "mfe": 0, "mae": 0})

        for i in range(1, len(df)):
            row = df.iloc[i]
            ts = self._to_unix_ms(row['ts'])
            price = float(row['close'])
            curr_high = float(row['high'])
            curr_low = float(row['low'])
            signal = row.get('signal', 0)

            # ★★★★★ 핵심 수정 1: 현재 평가금액은 equity에서 시작 ★★★★★
            current_equity = equity  # ← 실제 자본에서 시작!

            # 포지션 보유 중 → 평가손익만 계산 (equity는 그대로!)
            if position == 1:
                unrealized_pnl = (price - entry_price) * coin_qty
                current_equity += unrealized_pnl

                trade_highest = max(trade_highest, curr_high)
                trade_lowest = min(trade_lowest, curr_low)

            # -----------------------------
            # BUY (매수)
            # -----------------------------
            if position == 0 and signal == 1:
                position = 1
                entry_price = price
                trade_highest = price
                trade_lowest = price

                # ★★★★★ 핵심 수정 2: 실제 자본(equity) 기준으로 투자금 계산 ★★★★★
                invest_money = equity * risk_pct          # ← current_equity 아님! equity!
                coin_qty = (invest_money * leverage) / price

                trade_markers.append({
                    "time": ts, "position": "belowBar",
                    "shape": "arrowUp", "color": "#2ebd85",
                    "text": f"Buy x{leverage}"
                })

                trade_num += 1
                equity_over_trades.append({"trade_num": trade_num, "value": current_equity})

            # -----------------------------
            # SELL (매도)
            # -----------------------------
            elif position == 1 and signal == -1:
                realized_pnl = (price - entry_price) * coin_qty
                equity += realized_pnl                              # ← 여기서만 equity 바뀜!

                mfe = (trade_highest - entry_price) * coin_qty
                mae = (trade_lowest - entry_price) * coin_qty

                trade_markers.append({
                    "time": ts, "position": "aboveBar",
                    "shape": "arrowDown", "color": "#f6465d",
                    "text": "Sell"
                })

                equity_curve.append({
                    "time": ts,
                    "value": equity,
                    "mfe": mfe,
                    "mae": mae
                })

                trade_num += 1
                equity_over_trades.append({"trade_num": trade_num, "value": equity})

                position = 0
                coin_qty = 0.0
                continue

            # 파산 방지
            if equity <= 0:
                equity = 0
                equity_curve.append({"time": ts, "value": 0, "mfe": 0, "mae": 0})
                break

            # equity_curve에 현재 평가금액 기록
            equity_curve.append({
                "time": ts,
                "value": current_equity,
                "mfe": 0,
                "mae": 0
            })

        # 최종 결과
        final_roi = round((equity / self.initial_equity - 1) * 100, 2)

        summary = {
            "final_equity": equity,
            "trade_count": trade_num,
            "roi": final_roi,
            "mdd": 0,
        }

        result = {
            "summary": summary,
            "final_equity": equity,
            "equity_curve": equity_curve,
            "trade_markers": trade_markers,
            "equity_over_trades": equity_over_trades
        }

        if strategy_id is not None:
            print(f"[BACKTEST] 완료 → ROI {final_roi:+.1f}% | 거래 {trade_num}회 | 최종 자산 ${equity:,.0f}")

        return result