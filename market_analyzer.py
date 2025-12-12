import pandas as pd
import numpy as np

class MarketAnalyzer:
    """
    시장 분석기
    - 최근 N일 데이터 분석
    - 전략별 백테스트 실행
    - ROI / MDD / 승률 등의 순위 계산
    """
    def __init__(self, df_candles, strategy_map, backtester):
        self.df_candles = df_candles.copy()
        self.strategy_map = strategy_map
        self.backtester = backtester

        #  초기 로딩 시 timestamp 정규화
        self._normalize_ts()

    # --------------------------------------------------------
    #  timestamp 정규화 함수 (Analyzer 핵심 버그 해결)
    # --------------------------------------------------------
    def _normalize_ts(self):
        """
        ts를 pandas datetime → Unix timestamp(int)로 변환하여
        Backtester 및 Analyzer에서 동일한 시간 포맷을 사용하도록 한다.
        """
        try:
            # datetime 강제 변환
            self.df_candles['ts'] = pd.to_datetime(self.df_candles['ts'], errors='coerce')

            # 변환 실패 제거
            self.df_candles.dropna(subset=['ts'], inplace=True)

            # int timestamp(s)로 변환
            self.df_candles['ts'] = self.df_candles['ts'].astype('int64') // 10**9

        except Exception as e:
            print(f"[ANALYZER] ⚠️ timestamp 정규화 중 오류: {e}")

    # --------------------------------------------------------
    #  최근 N일 데이터 필터링
    # --------------------------------------------------------
    def _get_recent(self, days: int):
        # 1일 = 86400초
        cutoff = self.df_candles['ts'].max() - days * 86400
        return self.df_candles[self.df_candles['ts'] >= cutoff].copy()

    # --------------------------------------------------------
    #  MDD 계산 함수
    # --------------------------------------------------------
    def _calculate_mdd(self, equity_curve):
        if not equity_curve:
            return 0

        values = [p['value'] for p in equity_curve]

        peak = values[0]
        mdd = 0

        for v in values:
            peak = max(peak, v)
            dd = (peak - v) / peak
            mdd = max(mdd, dd)

        return round(mdd * 100, 2)

    # --------------------------------------------------------
    #  시장 분석 실행 (핵심 함수)
    # --------------------------------------------------------
    def run_analysis(self, period_days=30):
        print(f"[ANALYZER] 🔍 최근 {period_days}일 데이터로 시장 분석 시작...")

    # timestamp 정규화
        self._normalize_ts()

    # 최근 데이터 잘라서 가져오기
        df_recent = self._get_recent(period_days)

        if df_recent.empty:
            print("[ANALYZER] ⚠️ 최근 데이터가 없습니다.")
            return []

        results = []

    # 모든 전략 반복
        for strat_id, strat_obj in self.strategy_map.items():
            try:
                backtest = self.backtester.run_single_strategy(df_recent, strat_obj)

                final_equity = backtest.get("final_equity", 0)
                equity_curve = backtest.get("equity_curve", [])
                trade_markers = backtest.get("trade_markers", [])

                roi = round(((final_equity - self.backtester.initial_equity) /
                         self.backtester.initial_equity) * 100, 2)

                mdd = self._calculate_mdd(equity_curve)

                results.append({
                    "strategy_id": strat_id,
                    "strategy_name": strat_obj.name,
                    "roi": roi,
                    "mdd": mdd,
                    "trades": len(trade_markers) // 2,
                    "final_equity": final_equity,
                })

            except Exception as e:
                print(f"[ANALYZER] ⚠️ 전략 {strat_obj.name} 분석 중 에러: {e}")

        print(f"[ANALYZER] ✅ 분석 완료. 총 {len(results)}개 전략 테스트됨.")
        return results


    def get_best_strategy(self, period_days=30):
        results = self.run_analysis(period_days)
        if not results:
            return None

        return sorted(results, key=lambda x: x["roi"], reverse=True)[0]
    
    def get_market_trend(self, period_days=30):
        self._normalize_ts()

        df_recent = self._get_recent(period_days)
        if df_recent.empty or 'close' not in df_recent.columns:
            return "데이터 부족"

        try:
            first_close = float(df_recent.iloc[0]['close'])
            last_close = float(df_recent.iloc[-1]['close'])
        except Exception:
            return "중립"

        if first_close == 0:
            return "중립"

        change_pct = (last_close - first_close) / first_close * 100

        if change_pct > 5:
            return "상승 추세"
        elif change_pct < -5:
            return "하락 추세"
        else:
            return "횡보 구간"
