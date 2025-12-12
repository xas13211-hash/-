# backend/optimizer.py
import pandas as pd
import copy
from backtester import BacktestAgent
from strategies import STRATEGY_MAP

# [핵심 수정] 최적화 탐색 범위 (Grid Search)
# 1배부터 10배까지 1단위로 꼼꼼하게 다 검사합니다.
LEVERAGE_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
RISK_PERCENT_OPTIONS = [10, 20, 30, 50] 

# 하드 리밋 설정 (MDD가 -50%보다 더 떨어지면 그 설정은 탈락시킴)
# 즉, 수익률이 높아도 너무 위험하면(청산 위기) 추천하지 않습니다.
MAX_ALLOWED_MDD = -50.0 

def find_optimal_settings(df_candles, strategy_id):
    """
    주어진 전략 ID에 대해 최고의 레버리지와 비중을 찾는다.
    """
    
    base_strategy = STRATEGY_MAP.get(strategy_id)
    if not base_strategy:
        return None, None

    best_result = None
    best_config = None
    
    # 비교를 위한 초기값 (수익률 -무한대)
    max_ret = -999999.0
    
    agent = BacktestAgent(initial_equity=10000.0)
    
    # 그리드 서치 (모든 경우의 수 대입)
    for lev in LEVERAGE_OPTIONS:
        for risk in RISK_PERCENT_OPTIONS:
            # 전략 객체 복사 후 설정 주입
            test_strat = copy.deepcopy(base_strategy)
            test_strat.leverage = lev
            test_strat.risk_percent = risk
            
            try:
                # 백테스트 실행
                res = agent.run_single_strategy(df_candles, test_strat)
                
                # 1. 수익률(ROI) 추출
                ret = res['summary']['roi']
                
                # 2. MDD 직접 계산
                equity_curve = res.get('equity_curve', [])
                mdd = 0.0
                if equity_curve:
                    values = [p['value'] for p in equity_curve]
                    if values:
                        peak = values[0]
                        max_dd = 0
                        for v in values:
                            if v > peak: peak = v
                            dd = (peak - v) / peak
                            if dd > max_dd: max_dd = dd
                        # MDD를 음수로 표현 (예: -20.5)
                        mdd = max_dd * 100 * -1

                # 3. 하드 리밋 체크 (안전장치)
                if mdd < MAX_ALLOWED_MDD:
                    continue 
                
                # 4. 수익률 경쟁 (최고 수익 찾기)
                if ret > max_ret:
                    max_ret = ret
                    best_config = {
                        "leverage": lev,
                        "risk_percent": risk,
                        "total_return": ret,
                        "mdd": mdd
                    }
                    best_result = res
                    best_result['config'] = best_config
                    
            except Exception as e:
                continue

    # 찾은 게 있으면 반환
    if best_config:
        return best_config, best_result
    
    # 조건 만족하는 게 하나도 없으면 (예: 다 청산당함) None 반환
    return None, None