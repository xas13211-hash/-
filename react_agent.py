# react_agent.py
# -------------------------
# ReAct 기반 전략 추천/결정 에이전트
# StrategyAgent + MarketAnalyzer + BacktestAgent 연동 버전 (완성본)

from market_analyzer import MarketAnalyzer
from strategies import STRATEGY_MAP
import traceback


class ReActTrader:
    """
    ReAct 기반 자동 전략 분석 + 추천 에이전트
    Observation → Thought → Action 구조로 동작.
    """

    def __init__(self, strategy_agent):
        """
        strategy_agent: StrategyAgent 인스턴스
        """
        self.agent = strategy_agent
        self.analyzer = None
        self.analysis_results = []
        self.last_suggestion = None
        self.last_action_message = ""
        print("[ReActTrader] 에이전트 초기화 완료")

    # -----------------------------------------------------------
    # 내부 함수: 시장 관찰 (Observation)
    # -----------------------------------------------------------
    def _observe_market(self):
        """
        최근 캔들 데이터를 기반으로 시장을 분석합니다.
        """
        try:
            df = self.agent.df_30m
            if df.empty:
                return "데이터 부족"

            # MarketAnalyzer 구성
            self.analyzer = MarketAnalyzer(
                df_candles=df,
                strategy_map=self.agent.strategy_map,
                backtester=self.agent.backtester
            )

            # 최근 14일 기간으로 전략 비교
            self.analysis_results = self.analyzer.run_analysis(period_days=14)

            if not self.analysis_results:
                return "최근 14일 동안 분석할 데이터가 부족합니다."

            # 시장 추세 파악
            trend = self.analyzer.get_market_trend(period_days=14)
            return f"최근 14일 시장 추세는 '{trend}' 입니다."

        except Exception as e:
            traceback.print_exc()
            return f"시장 관찰 중 오류 발생: {e}"

    # -----------------------------------------------------------
    # 내부 함수: 사고 과정 (Thought)
    # -----------------------------------------------------------
    def _think(self):
        """
        여러 전략 성과를 비교하여 전략 교체 필요 여부를 판단합니다.
        """
        if not self.analysis_results:
            return "분석 결과 없음"

        # ROI 기준 상위 1위 전략
        sorted_results = sorted(
            self.analysis_results,
            key=lambda x: x["roi"],
            reverse=True
        )
        best = sorted_results[1]
        best_id = best["strategy_id"]
        best_roi = best["roi"]

        current_name = self.agent.active_strategy.name
        current_id = self._get_strategy_id(current_name)

        thought_msg = (
            f"현재 전략({current_name}) 대비 "
            f"가장 수익률이 좋은 전략은 '{STRATEGY_MAP[best_id].name}' 입니다. "
            f"(ROI {best_roi}%)"
        )

        return thought_msg

    # -----------------------------------------------------------
    # 내부 함수: 행동 결정 (Action)
    # -----------------------------------------------------------
    def _act(self):
        """
        현재 전략과 최적 전략을 비교하여 전략 유지/변경을 결정합니다.
        """
        if not self.analysis_results:
            return "전략 변경 불가 (분석 결과 없음)"

        # ROI 기준 상위 전략
        sorted_results = sorted(
            self.analysis_results,
            key=lambda x: x["roi"],
            reverse=True
        )
        best = sorted_results[1]  
        best_id = best["strategy_id"]
        best_strategy = STRATEGY_MAP[best_id]
        best_roi = best["roi"]

        current_strategy = self.agent.active_strategy
        current_id = self._get_strategy_id(current_strategy.name)

        if current_id == best_id:
            msg = f"현재 전략({current_strategy.name})이 이미 최적 전략입니다. 유지합니다."
            self.last_suggestion = None
            return msg

        roi_diff = best_roi - self._get_strategy_roi(current_id)
        if roi_diff < 3:
            msg = (
                f"최적 전략({best_strategy.name})과 ROI 차이({roi_diff:.2f}%)가 크지 않아 "
                f"전략을 유지합니다."
            )
            self.last_suggestion = None
            return msg

        suggestion_msg = (
            f"추천: 현재 전략 '{current_strategy.name}' 대신 "
            f"'{best_strategy.name}' 전략을 사용하는 것이 더 유리합니다. "
            f"(ROI 차이: {roi_diff:.2f}%)"
        )
        self.last_suggestion = best_id
        return suggestion_msg

    def run_react_loop(self):
        """
        StrategyAgent가 30분봉 마감 시 자동 실행하도록 연결됨.
        """
        print("[ReActTrader] 자동 분석 실행 시작")

        obs = self._observe_market()
        thought = self._think()
        action = self._act()

        result = (
            "📈 [ReAct 보고서]\n"
            f"- Observation: {obs}\n"
            f"- Thought: {thought}\n"
            f"- Action: {action}\n"
        )

        print(result)
        self.last_action_message = result
        return result

    def apply_suggested_strategy(self):
        """
        사용자가 전략 교체를 승인하면 실행됨.
        """
        if self.last_suggestion is None:
            return "현재 적용 가능한 제안이 없습니다."

        new_strategy = STRATEGY_MAP[self.last_suggestion]
        self.agent.switch_strategy(new_strategy)

        msg = f"✅ 전략이 '{new_strategy.name}' 로 성공적으로 변경되었습니다!"
        self.last_suggestion = None
        return msg

    def _get_strategy_id(self, name):
        """전략 이름으로 전략 ID 찾기"""
        for sid, s in STRATEGY_MAP.items():
            if s.name == name:
                return sid
        return 0

    def _get_strategy_roi(self, strategy_id):
        """analysis_results에서 특정 전략의 ROI 조회"""
        for r in self.analysis_results:
            if r["strategy_id"] == strategy_id:
                return r["roi"]
        return 0.0
