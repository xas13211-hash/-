# backend/strategy_agent.py
import pandas as pd
import pandas_ta as ta
import json
import os
import threading
import datetime
import rest_client
import db_handler 
from backtester import BacktestAgent
from strategies import NoStrategy, RsiStrategy, SmaCrossStrategy, STRATEGY_MAP

STATE_FILE = "strategy_state.json"

class StrategyAgent:
    def __init__(self, instId="BTC-USDT-SWAP", connection_manager=None):
        print("[AGENT] 🧠 전략 에이전트 초기화 시작...")
        self.instId = instId
        self.df_30m = pd.DataFrame()
        self.connection_manager = connection_manager
        
        self.active_strategy = NoStrategy()
        self.leverage = 3        
        self.risk_percent = 10.0 
        self.current_position = 0.0 
        self.entry_price = 0.0
        self.chart_markers = []
        
        # 전략 라이브러리 & 백테스트 에이전트
        self.strategy_map = STRATEGY_MAP
        self.backtester = BacktestAgent(initial_equity=10000.0)
        
        # [NEW] 마지막 분석 실행 시간 추적 (중복 방지용 초기화)
        self.last_analyzed_candle = None

        # 초기화
        self.load_state()
        self.analysis_callback = None 
        
        # [핵심] 데이터 로드 및 계산 시도
        self.initialize_data_from_db()
        
        # [추가됨] DB 로드 후 마지막 캔들 시간을 '이미 분석함'으로 설정
        # 이렇게 해야 서버 켜지자마자 "마감 감지"라며 분석을 돌리는 것을 방지함
        if not self.df_30m.empty:
            # iloc[-1]['ts']가 Timestamp 객체일 수도 있고 int일 수도 있으니 확인 필요
            # 보통 로드 직후엔 datetime 객체로 변환되어 있을 가능성이 높음
            self.last_analyzed_candle = self.df_30m.iloc[-1]['ts']
            print(f"[AGENT] 🕒 초기 기준 시간 설정: {self.last_analyzed_candle}")

        # 시작 마커
        self._add_chart_marker(pd.Timestamp.now(), "belowBar", "circle", "#FFFFFF", "System Start")
        self.save_state()
        
        print(f"[AGENT] 🧠 에이전트 준비 완료. (현재 전략: {self.active_strategy.name})")
        
    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                self.current_position = state.get("current_position", 0.0)
                self.entry_price = state.get("entry_price", 0.0)
                self.leverage = state.get("leverage", 3)
                self.chart_markers = [] # 마커 초기화
                print("[AGENT] 💾 상태 복구 완료.")
            except Exception as e:
                print(f"[AGENT] ⚠️ 상태 로드 실패: {e}")
                self._reset_state()
        else:
            self._reset_state()

    def _reset_state(self):
        self.current_position = 0.0
        self.entry_price = 0.0
        self.chart_markers = []
        self.save_state()

    def save_state(self):
        state = {
            "current_position": self.current_position,
            "entry_price": self.entry_price,
            "leverage": self.leverage,
            "chart_markers": self.chart_markers[-100:]
        }
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f, indent=4)
        except: pass

    def initialize_data_from_db(self):
        print("[AGENT] 📊 DB에서 30분봉 데이터 로드 시도...")
        try:
            df = db_handler.load_all_candles_as_df()
            if not df.empty:
                self.df_30m = df
                print(f"[AGENT] ✅ DB 로드 성공: {len(self.df_30m)}개 캔들.")
                
                # [중요] 데이터 로드 직후 지표 계산 시도
                self._calculate_indicators()
                
                # 계산 결과 확인 (로그 출력)
                last_row = self.df_30m.iloc[-1]
                rsi = last_row.get('rsi2_base', 'N/A')
                print(f"[AGENT] 🧪 지표 계산 테스트: RSI={rsi}")
                
            else:
                print(f"[AGENT] ⚠️ DB가 비어있습니다. 동기화가 필요합니다.")
        except Exception as e:
            print(f"[AGENT] 🔴 데이터 로드 중 치명적 오류: {e}")

    # --- 기능 ---
    def switch_strategy(self, strategy_obj):
        print(f"[AGENT] 🔄 전략 변경: {strategy_obj.name}")
        self.active_strategy = strategy_obj
        self._add_chart_marker(pd.Timestamp.now(), "belowBar", "circle", "#FFFFFF", f"Start: {strategy_obj.name}")
        self.save_state()

    def update_settings(self, leverage=None, risk=None):
        msg = []
        # [수정] 챗봇이 물어볼 때마다 지표를 강제로 최신화 (계산 누락 방지)
        self._calculate_indicators()
        
        # 가장 최신 행 가져오기
        last = self.df_30m.iloc[-1]
        
        # 안전한 값 추출 헬퍼 함수
        def get_val(col):
            val = last.get(col)
            # 값이 NaN이면 바로 전 캔들 확인 (최신 캔들 계산 딜레이 대비)
            if pd.isna(val) and len(self.df_30m) > 1:
                val = self.df_30m.iloc[-2].get(col)
            
            # 그래도 NaN이면 0.0 반환
            if pd.isna(val): return 0.0
            return round(float(val), 2)

        rsi = get_val('rsi2_base')
        ma5 = get_val('ma5')
        ma20 = get_val('ma20')
        
        # [수정] 불필요한 에러 메시지 제거
        # RSI가 0.0일 수도 있으므로 (극단적 상황), 0이라고 해서 무조건 에러로 취급하지 않음
        # 대신 데이터 개수와 함께 정보를 줍니다.
        
        trend = "상승세" if ma5 > ma20 else "하락세"
        
        rsi_status = "중립"
        if rsi > 70: rsi_status = "과매수(High)"
        elif rsi < 30: rsi_status = "과매도(Low)"
        
        # AI가 읽기 편한 자연어 문장으로 반환
        return f"현재 {len(self.df_30m)}개의 캔들 분석 중. RSI 지표는 {rsi} ({rsi_status}) 상태이며, 이동평균선은 {trend} (MA5: {ma5}, MA20: {ma20}) 입니다."

    def panic_sell_all(self):
        print("[AGENT] 🚨 긴급 청산!")
        try:
            if self.current_position != 0:
                side = "sell" if self.current_position > 0 else "buy" 
                res = rest_client.place_order(self.instId, "cross", side, "market", "0.01", "long")
                if res and res.get('code') == '0':
                    self.current_position = 0
                    self.entry_price = 0
                    self._add_chart_marker(pd.Timestamp.now(), "aboveBar", "arrowDown", "#FF0000", "PANIC SELL")
                    self.save_state()
                    return "✅ 긴급 청산 성공"
                return f"❌ 청산 실패: {res.get('msg')}"
            return "ℹ️ 포지션 없음"
        except Exception as e:
            return f"❌ 에러: {e}"

    def set_analysis_callback(self, callback):
        """
        30분봉 마감 시 호출할 콜백 함수 등록
        """
        self.analysis_callback = callback
        print("[AGENT] 🔗 자동 분석 콜백 등록 완료")

    def on_new_price(self, price, timestamp_ms):
        if self.df_30m.empty: return 
        price = float(price)
        current_time = pd.to_datetime(timestamp_ms, unit='ms')
        last_candle_time = self.df_30m.iloc[-1]['ts']
        current_candle_bucket = current_time.floor('30min')

        # 30분봉 마감 체크 (새로운 30분봉 시작 시)
        if current_candle_bucket > last_candle_time:
            # [NEW] 중복 실행 방지: 이미 분석한 캔들이면 스킵
            if self.last_analyzed_candle == last_candle_time:
                return
            
            print(f"[AGENT] 🕒 30분봉 마감 감지! ({last_candle_time} -> {current_candle_bucket})")
            
            # [중요] 마지막 분석 시간 기록
            self.last_analyzed_candle = last_candle_time
            
            # [중요] 데이터 갱신 (DB에서 최신 캔들 로드)
            try:
                new_df = db_handler.load_all_candles_as_df()
                if not new_df.empty:
                    self.df_30m = new_df
                    self._calculate_indicators()
                    print(f"[AGENT] 📊 데이터 갱신 완료: {len(self.df_30m)}개 캔들")
            except Exception as e:
                print(f"[AGENT] ⚠️ 데이터 갱신 실패: {e}")

            # 1. 전략 실행 (매수/매도)
            self._check_strategy_on_bar_close()
            
            # 2. [NEW] 자동 분석 트리거 (콜백 호출)
            if self.analysis_callback:
                print("[AGENT] 🤖 자동 시장 분석 실행 중...")
                # 별도 스레드에서 실행하여 메인 로직 차단 방지
                threading.Thread(target=self.analysis_callback).start()

        if self.connection_manager:
            data = {"price": price, "time": timestamp_ms}
            # threading.Thread(target=self.connection_manager.broadcast_json_sync, args=({"type": "ticker", "data": data},)).start()

    # 🛑 [핵심 수정] 에러 숨기지 않고 출력
    def _calculate_indicators(self):
        if self.df_30m.empty: return
        try:
            # 원본 보존을 위해 copy
            df = self.df_30m.copy()
            
            # 지표 계산
            rsi = ta.rsi(df['close'], length=14)
            ma5 = ta.sma(df['close'], length=5)
            ma20 = ta.sma(df['close'], length=20)
            ma60 = ta.sma(df['close'], length=60)
            
            # 계산된 시리즈를 원본 DF에 할당
            self.df_30m['rsi2_base'] = rsi
            self.df_30m['ma5'] = ma5
            self.df_30m['ma20'] = ma20
            self.df_30m['ma60'] = ma60
            
        except Exception as e:
            # 🛑 에러 발생 시 여기서 빨간 로그가 뜹니다!
            print(f"[AGENT] ⚠️ 지표 계산 중 에러 발생: {e}")

    def _check_strategy_on_bar_close(self):
        if isinstance(self.active_strategy, NoStrategy) or len(self.df_30m) < 50: return
        
        try:
            df_calc = self.active_strategy.calculate_signals(self.df_30m.copy())
            last_signal = df_calc.iloc[-1].get('signal', 0)
            price = self.df_30m.iloc[-1]['close']
            time = self.df_30m.iloc[-1]['ts']

            if last_signal == 1 and self.current_position == 0:
                self._execute_order("buy", price, time, f"{self.active_strategy.name} Long")
            elif last_signal == -1 and self.current_position > 0:
                self._execute_order("sell", price, time, f"{self.active_strategy.name} Exit")
        except Exception as e:
            print(f"[AGENT] ⚠️ 전략 실행 중 에러: {e}")

    def _execute_order(self, side, price, time, text):
        print(f"[AGENT] ⚡ 신호: {side} @ {price}")
        qty = "0.01"
        self._add_chart_marker(
            time,
            "belowBar" if side == "buy" else "aboveBar",
            "arrowUp" if side == "buy" else "arrowDown",
            "#2ebd85" if side == "buy" else "#f6465d",
            text,
        )

        try:
            res = rest_client.place_order(self.instId, "cross", "buy" if side=="buy" else "sell", "market", qty, "long")
            if res and res.get('code') == '0':
                print(f"[AGENT] ✅ 주문 완료")
                self.current_position = 1 if side == "buy" else 0
                self.save_state()
            else:
                print(f"[AGENT] ❌ 주문 실패: {res}")
        except Exception as e:
            print(f"[AGENT] 🚨 에러: {e}")

    def _add_chart_marker(self, time, position, shape, color, text):
        ts = int(time.timestamp())
        marker = {"time": ts, "position": position, "shape": shape, "color": color, "text": text}
        self.chart_markers.append(marker)
        if self.connection_manager:
            threading.Thread(target=self.connection_manager.broadcast_json_sync, args=({"type": "marker", "data": marker},)).start()