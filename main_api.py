# backend/main_api.py
import asyncio
import uvicorn
import os
import json
import time
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import json

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from strategy_agent import StrategyAgent
from react_agent import ReActTrader
from config import WS_PRIVATE_URL, WS_PUBLIC_URL, GEMINI_API_KEY
from websocket_manager import OKXWebSocketManager
import rest_client
from backtester import BacktestAgent
import data_sync

from db_handler import (
    init_db,
    run_batch_backtest,
    get_recommended_strategies,
    load_all_candles_as_df,
    get_all_strategies,
    save_backtest_result,
    load_backtest_result,
    get_strategy_perf,
    get_last_active_strategy_id,
    get_last_active_strategy_id,
)
from strategies import STRATEGY_MAP

# ============================================================
ai_model = None
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model_name = "gemini-2.5-flash"
    ai_model = genai.GenerativeModel(model_name)
    print(f"[System] ✨ Gemini AI 연결 성공! (Model: {model_name})")
except Exception as e:
    print(f"[System] ⚠️ Gemini API 연결 실패: {e}")


# ============================================================
# [WebSocket & Connection Manager]
# ============================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.loop = None  # asyncio 이벤트 루프 (lifespan에서 설정)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_json(self, data: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception:
                # 끊어진 소켓은 조용히 제거
                self.disconnect(connection)

    def broadcast_json_sync(self, data: dict):
        """스레드 안에서 호출할 수 있는 동기 브로드캐스트 래퍼"""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast_json(data), self.loop)


manager = ConnectionManager()
strategy_agent = StrategyAgent(instId="BTC-USDT-SWAP", connection_manager=manager)
react_trader = ReActTrader(strategy_agent)


# [NEW] 자동 분석 콜백 등록 (30분봉 마감 시 호출)
def run_analysis_callback():
    print("[API] 🤖 30분봉 마감 -> ReAct 자동 분석 시작")
    try:
        react_trader.run_react_loop()
    except Exception as e:
        print(f"[ReAct Error] {e}")


strategy_agent.set_analysis_callback(run_analysis_callback)


ws_public = OKXWebSocketManager(
    WS_PUBLIC_URL,
    channels_to_subscribe=[{"channel": "tickers", "instId": "BTC-USDT-SWAP"}],
    connection_manager=manager,
    strategy_agent=strategy_agent,
)

ws_private = OKXWebSocketManager(
    WS_PRIVATE_URL,
    channels_to_subscribe=[
        {"channel": "positions", "instType": "SWAP"},
        {"channel": "orders", "instType": "SWAP"},
    ],
    connection_manager=manager,
    strategy_agent=strategy_agent,
)


# ============================================================
# [Helper Functions]
# ============================================================
def _load_candles_safe():
    """DB에서 캔들 데이터를 안전하게 로드. 비어있으면 긴급 동기화."""
    try:
        df = load_all_candles_as_df()
        if df is None or df.empty:
            print("[System] DB가 비어있어 긴급 동기화를 시작합니다.")
            df = data_sync.sync_market_data(instId="BTC-USDT-SWAP", bar="30m")
        return df
    except Exception as e:
        print(f"[Data Load Error] {e}")
        return None


def get_current_context():
    """AI 프롬프트용 현재 시장/봇 상태 요약"""
    current_price = 0.0
    tech_info = "분석 대기 중"
    pos = "NONE"
    strat = "Unknown"
    lev = 1
    risk = 5.0

    # 1) 시세 조회
    try:
        ticker = rest_client.public_get("/api/v5/market/ticker?instId=BTC-USDT-SWAP")
        if ticker and "data" in ticker and len(ticker["data"]) > 0:
            current_price = float(ticker["data"][0]["last"])
    except Exception as e:
        print(f"[Context Error] 가격 조회 실패: {e}")

    # 2) 에이전트 상태
    try:
        if hasattr(strategy_agent, "get_technical_status"):
            tech_info = strategy_agent.get_technical_status()

        if hasattr(strategy_agent, "current_position"):
            pos = "LONG" if strategy_agent.current_position > 0 else "NONE"

        if hasattr(strategy_agent, "active_strategy"):
            strat = strategy_agent.active_strategy.name

        if hasattr(strategy_agent, "leverage"):
            lev = strategy_agent.leverage
        if hasattr(strategy_agent, "risk_percent"):
            risk = strategy_agent.risk_percent
    except Exception as e:
        print(f"[Context Error] 에이전트 상태 조회 실패: {e}")

    return f"""
    [시장 데이터]
    - 현재가: ${current_price:,.2f}
    - 기술적 분석 상태: {tech_info}
    
    [봇 상태]
    - 현재 전략: {strat}
    - 포지션: {pos}
    - 설정: 레버리지 {lev}배, 진입비중 {risk}%
    """


# ============================================================
# [App & Lifespan 설정]
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[System] 🚀 서버 시작 (Lifespan)...")
    manager.loop = asyncio.get_running_loop()

    # 1. DB 및 데이터 초기화
    init_db()
    data_sync.sync_market_data(instId="BTC-USDT-SWAP", bar="30m")
    
    # 2. 전체 데이터 로드
    df = _load_candles_safe()

    # 3. 전략 최적화 및 백테스트 (데이터가 있을 때만)
    # ---------------------------------------------------------
    try:
        if df is not None and len(df) > 1000:
            # [핵심 수정] 무조건 삭제하던 코드(DELETE)를 제거했습니다.
            # 대신 run_batch_backtest 함수 안에서 "데이터가 있는지 확인"하고
            # run_batch_backtest(df)  # ← 서버 재시작 시 최적화 스킵 (DB 데이터 사용)
            print(f"[System] 📊 전략 최적화 데이터 확인 중... (Skip)")
            pass
            
        else:
            print("[System] ⚠️ 데이터가 부족하여 최적화를 건너뜁니다.")

    except Exception as e:
        print(f"[System] 전략 최적화 실행 중 오류: {e}")
    # ---------------------------------------------------------

    # 4. 거래소 설정
    try:
        rest_client.set_position_mode_long_short()
    except Exception as e:
        print(f"[System] 포지션 모드 설정 실패: {e}")

    # 5. WebSocket 실행
    import threading
    def start_ws():
        try:
            ws_public.start_websocket_thread()
            ws_private.start_websocket_thread()
        except Exception as e:
            print("[WS ERROR]", e)

    threading.Thread(target=start_ws, daemon=True).start()

    yield

    print("[System] 👋 서버 종료 중...")
    ws_public.stop()
    ws_private.stop()

app = FastAPI(title="OKX AI Trading System", lifespan=lifespan)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "*",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# [API: 전략 상세 + 백테스트]
# ============================================================
# [backend/main_api.py]

@app.get("/api/v1/strategy/detail/{strategy_id}")
def get_strategy_detail(strategy_id: int):
    import db_handler

    if strategy_id not in STRATEGY_MAP:
        return JSONResponse({"error": "Strategy not found"}, 404)

    strat = STRATEGY_MAP[strategy_id]
    base_description = getattr(strat, "description", "전략 설명이 없습니다.")

    # 1. [핵심] 저장된 최적화 결과(Cache)가 있는지 먼저 확인
    saved_data = db_handler.load_backtest_result(strategy_id)
    
    # 2. 데이터가 있으면 -> 계산 없이 바로 사용 (매우 빠름 & 최적화된 데이터)
    if saved_data:
        print(f"[API] ⚡ 전략 {strategy_id} : 저장된 최적화 결과(Cache) 로드 성공")
        
        final_equity = saved_data.get("final_equity", 10000)
        # ROI 계산 (저장된 자산 기준)
        roi = round((final_equity - 10000) / 10000 * 100, 2)
        
        # MDD 계산 (저장된 커브 데이터 활용)
        curve = saved_data.get("equity_curve", [])
        mdd = 0.0
        if curve:
            peak = 10000
            max_dd = 0
            for p in curve:
                val = p["value"]
                if val > peak: peak = val
                dd = (peak - val) / peak
                if dd > max_dd: max_dd = dd
            mdd = max_dd * 100 * -1
            
        trade_count = len(saved_data.get("trade_markers", []))
        equity_curve = curve
        trade_markers = saved_data.get("trade_markers", [])
        equity_over_trades = saved_data.get("equity_over_trades", [])

    # 3. 데이터가 없으면 -> 어쩔 수 없이 실시간 계산 (Fallback)
    else:
        print(f"[API] ⚠️ 저장된 데이터 없음 -> 실시간 계산 실행 (느릴 수 있음)")
        
        df = _load_candles_safe()
        if df is None or df.empty:
            return JSONResponse({"error": "No candle data"}, 500)

        agent = BacktestAgent(initial_equity=10000)
        result = agent.run_single_strategy(df, strat, strategy_id=strategy_id)
        
        final_equity = result.get("final_equity", 10000)
        equity_curve = result.get("equity_curve", [])
        trade_markers = result.get("trade_markers", [])
        equity_over_trades = result.get("equity_over_trades", [])
        
        roi = round((final_equity - 10000) / 10000 * 100, 2)
        
        # 실시간 MDD 계산
        mdd = 0.0
        if equity_curve:
            peak = 10000
            max_dd = 0
            for p in equity_curve:
                v = p["value"]
                if v > peak: peak = v
                dd = (peak - v) / peak
                if dd > max_dd: max_dd = dd
            mdd = max_dd * 100 * -1
            
        trade_count = len(trade_markers)


    # ---------------------------
    #  Gemini 상세 설명 생성
    # ---------------------------
    detailed_text = base_description + "\n\n(⚠️상세 설명 생성 실패 — 기본 설명으로 대체됨)"

    if ai_model is not None:
        try:
            prompt = f"""
            당신은 '퀀트 트레이딩 전략 설명 전문가'입니다.
            아래 전략 설명과 백테스트 데이터를 참고하여 초보자도 이해할 수 있게 한국어로 설명해주세요.
            
            [기본 설명] {base_description}
            [성과] ROI: {roi}%, MDD: {mdd}%, 거래수: {trade_count}
            """
            resp = ai_model.generate_content(prompt)
            if resp and hasattr(resp, "text"):
                detailed_text = resp.text.strip()
        except Exception: pass

    # 최적화된 설정값(레버리지 등) 가져오기 (DB 조회)
    # 이미 saved_data가 있다면 그 안의 내용을 믿으면 되지만, 
    # 확실히 하기 위해 strategy_perf 테이블에서 파라미터는 따로 가져올 수도 있음.
    # 여기서는 간단히 DB 조회 로직 유지.
    row = get_strategy_perf(strategy_id)
    
    expected_roi = row[1] if row else roi
    expected_mdd = row[2] if row else mdd

    return {
        "id": strategy_id,
        "name": strat.name,
        "description": base_description,
        "detailed_description": detailed_text,
        "risk_level": strat.risk_level,
        "backtest": {
            "roi": roi,
            "mdd": round(mdd, 2),
            "final_equity": final_equity,
            "trade_count": trade_count,
            "equity_curve": equity_curve,
            "equity_over_trades": equity_over_trades
        },
        "optimizer": {
            "best_leverage": "Auto", # 최적화된 결과이므로 Auto로 표시하거나 DB에 저장된 값 표시
            "best_risk_percent": "Auto",
            "expected_return": expected_roi,
            "expected_mdd": expected_mdd
        }
    }


# ============================================================
# [API: 차트 마커 / 거래 내역 / 차트 데이터 / 백테스트 결과]
# ============================================================
@app.get("/api/v1/chart-markers")
def get_chart_markers():
    try:
        if os.path.exists("strategy_state.json"):
            with open("strategy_state.json", "r") as f:
                state = json.load(f)
            return state.get("chart_markers", [])
        return []
    except Exception:
        return []


@app.get("/api/v1/trade-history")
async def get_trade_history():
    result = rest_client.get_transaction_history_3months(
        instType="SWAP", limit="100"
    )
    if result and result.get("code") == "0":
        trades = result.get("data", [])
        processed = []
        for t in trades:
            price = float(t.get("fillPx") or t.get("px") or 0)
            size = float(t.get("fillSz") or t.get("sz") or 0)
            processed.append(
                {
                    "time": int(t.get("ts", 0)),
                    "symbol": t.get("instId", ""),
                    "side": t.get("side", ""),
                    "price": price,
                    "size": size,
                    "fee": float(t.get("fee", 0)),
                }
            )
        return {"count": len(processed), "trades": processed}
    return {"error": "조회 실패"}


@app.get("/api/v1/chart-data")
async def get_chart_data_api():
    df = _load_candles_safe()
    if df is None or df.empty:
        return JSONResponse(
            content={"error": "Data not available"}, status_code=500
        )

    df_recent = df.copy()
    df_recent["ma5"] = df_recent["close"].rolling(window=5).mean().fillna(0)
    df_recent["ma20"] = df_recent["close"].rolling(window=20).mean().fillna(0)
    df_recent["ma60"] = df_recent["close"].rolling(window=60).mean().fillna(0)

    # 차트 라이브러리 요구사항에 따라 time 단위(초/밀리초)는 프론트에서 맞추어 사용
    def row_to_candle(row):
        return {
            "time": int(row["ts"].timestamp()),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
        }

    candlestick_data = df_recent.apply(row_to_candle, axis=1).to_list()
    lines_data = {
        "ma5": df_recent.apply(
            lambda row: {
                "time": int(row["ts"].timestamp()),
                "value": row["ma5"],
            },
            axis=1,
        ).to_list(),
        "ma20": df_recent.apply(
            lambda row: {
                "time": int(row["ts"].timestamp()),
                "value": row["ma20"],
            },
            axis=1,
        ).to_list(),
        "ma60": df_recent.apply(
            lambda row: {
                "time": int(row["ts"].timestamp()),
                "value": row["ma60"],
            },
            axis=1,
        ).to_list(),
    }

    return {
        "candlesticks": candlestick_data,
        "lines": lines_data,
        "markers": strategy_agent.chart_markers,
    }


@app.get("/api/v1/backtest-results")
async def get_backtest_results():
    current_strat_name = strategy_agent.active_strategy.name
    current_strat_id = 0

    for s_id, s in STRATEGY_MAP.items():
        if s.name == current_strat_name:
            current_strat_id = s_id
            break

    saved_data = load_backtest_result(current_strat_id)
    if saved_data:
        print(
            f"[API] DB에서 전략 {current_strat_id} 백테스트 결과 로드 완료"
        )
        return saved_data

    df = _load_candles_safe()
    if df is not None and not df.empty:
        current_strat = strategy_agent.active_strategy

        if isinstance(current_strat, NoStrategy):
            initial_equity = 10000
            curve = [
                {
                    "time": int(df.iloc[0]["ts"].timestamp()),
                    "value": initial_equity,
                },
                {
                    "time": int(df.iloc[-1]["ts"].timestamp()),
                    "value": initial_equity,
                },
            ]
            return {"equity_curve": curve, "markers": []}

        try:
            agent = BacktestAgent(initial_equity=10000.0)
            res = agent.run_single_strategy(df, current_strat)
            return {
                "equity_curve": res.get("equity_curve", []),
                "markers": res.get("trade_markers", []),
            }
        except Exception as e:
            print(f"[API Error] 실시간 백테스트 실패: {e}")

    return {"equity_curve": [], "markers": []}


# ============================================================
# [보고서 생성 (캐싱)]
# ============================================================
class ReportRequest(BaseModel):
    period: str


REPORT_CACHE = {}
CACHE_DURATION = 3600  # 1시간


def _calculate_backtest_stats(equity_curve, markers):
    if not equity_curve:
        return None

    # 1. 기본 통계
    start_value = equity_curve[0]["value"]
    end_value = equity_curve[-1]["value"]
    total_net_profit = end_value - start_value
    total_net_profit_percent = (total_net_profit / start_value) * 100 if start_value > 0 else 0

    # 2. MDD
    peak = -float('inf')
    max_drawdown = 0
    max_drawdown_percent = 0
    for point in equity_curve:
        val = point["value"]
        if val > peak:
            peak = val
        dd = peak - val
        dd_percent = (dd / peak) * 100 if peak > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd
        if dd_percent > max_drawdown_percent:
            max_drawdown_percent = dd_percent

    # 3. 승률 (markers 분석)
    # markers에는 PnL 정보가 없을 수 있으므로 equity curve 변동으로 추정하거나
    # text 필드에 PnL이 있다면 파싱. 여기서는 equity curve의 변동 시점을 거래로 간주.
    # (간소화를 위해 markers 개수로 거래 횟수 추정)
    total_trades = len(markers)
    
    # 정확한 승률 계산을 위해선 trade list가 필요하지만, 
    # 여기서는 약식으로 equity curve가 상승한 구간을 winning trade로 간주하거나
    # 단순히 전체 수익 여부만 전달.
    # (상세 승률은 프론트엔드 계산값과 일치시키기 어려울 수 있으므로, AI에게는 '전체적인 성과' 위주로 전달)
    
    return {
        "net_profit": total_net_profit,
        "net_profit_percent": total_net_profit_percent,
        "mdd": max_drawdown,
        "mdd_percent": max_drawdown_percent,
        "total_trades": total_trades
    }

@app.post("/api/v1/generate-report")
async def generate_trading_report(req: ReportRequest):
    current_ts = time.time()
    period = req.period

    print(f"[Report] 📡 요청 수신: {period}")

    # 캐싱 확인
    if period in REPORT_CACHE:
        if current_ts - REPORT_CACHE[period]["timestamp"] < CACHE_DURATION:
            return {
                "report": REPORT_CACHE[period]["content"],
                "cached": True,
            }

    # 1. 현재 활성화된 전략의 백테스트 결과 로드
    current_strat_name = strategy_agent.active_strategy.name
    current_strat_id = 0
    for s_id, s in STRATEGY_MAP.items():
        if s.name == current_strat_name:
            current_strat_id = s_id
            break
    
    # [Fallback] 만약 현재 전략이 0(NoStrategy)이면, DB에서 가장 최근에 실행된 전략을 가져옴
    if current_strat_id == 0:
        try:
            last_id = get_last_active_strategy_id()
            if last_id > 0:
                current_strat_id = last_id
                # 에이전트 상태도 복구 (선택 사항)
                if last_id in STRATEGY_MAP:
                    strategy_agent.switch_strategy(STRATEGY_MAP[last_id])
                    current_strat_name = STRATEGY_MAP[last_id].name
                    print(f"[Report] 🔄 전략 상태 복구: {current_strat_name} (ID: {current_strat_id})")
        except Exception as e:
            print(f"[Report Error] Fallback logic failed: {e}")

    print(f"[Report Debug] Active Strategy: {current_strat_name} (ID: {current_strat_id})")

    backtest_data = load_backtest_result(current_strat_id)
    if not backtest_data:
        print(f"[Report Debug] No backtest data found for ID {current_strat_id}")
        # 데이터가 없으면 실시간 백테스트 시도 (fallback)
        # (여기서는 생략하고 빈 데이터 처리)
        backtest_data = {"equity_curve": [], "markers": []}
    else:
        print(f"[Report Debug] Loaded backtest data. Equity: {len(backtest_data.get('equity_curve', []))}, Markers: {len(backtest_data.get('markers', []))}")

    equity_curve = backtest_data.get("equity_curve", [])
    markers = backtest_data.get("markers", [])

    # 2. 기간 필터링 (프론트엔드 로직과 일치)
    # period가 'monthly'이면 전체 데이터 사용
    filtered_equity = equity_curve
    filtered_markers = markers

    if period == 'daily':
        cutoff = current_ts - (24 * 60 * 60)
        # 백테스트 데이터의 시간은 timestamp 정수형이라 가정
        filtered_equity = [d for d in equity_curve if d['time'] > cutoff]
        filtered_markers = [m for m in markers if m['time'] > cutoff]
    elif period == 'weekly':
        cutoff = current_ts - (7 * 24 * 60 * 60)
        filtered_equity = [d for d in equity_curve if d['time'] > cutoff]
        filtered_markers = [m for m in markers if m['time'] > cutoff]
    
    # 3. 통계 계산
    stats = _calculate_backtest_stats(filtered_equity, filtered_markers)
    
    stats_text = "데이터 부족"
    if stats:
        stats_text = (
            f"- 총 손익: {stats['net_profit']:.2f} USDT ({stats['net_profit_percent']:.2f}%)\n"
            f"- 최대 자본 감소(MDD): {stats['mdd_percent']:.2f}% (-{stats['mdd']:.2f} USDT)\n"
            f"- 총 거래 횟수: {stats['total_trades']}회"
        )

    # 4. 프롬프트 생성
    period_kr = {"daily": "일간", "weekly": "주간", "monthly": "전체(누적)"}.get(period, "전체")
    
    prompt = f"""
    당신은 '전문 AI 트레이딩 애널리스트'입니다. 
    아래 **백테스트 시뮬레이션 결과**를 바탕으로 '{period_kr} 트레이딩 성과 보고서'를 작성해주세요.
    
    [분석 대상 데이터 ({period_kr})]
    {stats_text}

    [작성 가이드]
    1. **요약**: 성과를 한 문단으로 요약하세요. (수익률과 MDD 언급 필수)
    2. **매매 분석**: 거래 빈도와 손익 추이를 바탕으로 전략의 성향(안정/공격)을 평가하세요.
    3. **제언**: 현재 성과를 바탕으로 유지, 보완, 또는 리스크 관리 조언을 한 줄로 덧붙이세요.
    4. 긍정적이면 격려를, 부정적이면 냉철한 분석을 제공하세요.
    5. **반드시 주어진 데이터 수치(수익률, MDD 등)와 일치하는 내용을 작성하세요.** (없는 수치를 지어내지 마세요)
    """

    try:
        resp = ai_model.generate_content(prompt)
        report_content = resp.text.strip()
        
        # 캐싱 저장
        REPORT_CACHE[period] = {
            "timestamp": current_ts,
            "content": report_content
        }
        
        return {"report": report_content}

    except Exception as e:
        print(f"[Report Error] {e}")
        return {"report": "AI 분석 중 오류가 발생했습니다."}




# ============================================================
# [AI 채팅 (전략 추천 포함)]
# ============================================================
class ChatRequest(BaseModel):
    message: str


CHAT_HISTORY = []


@app.get("/api/v1/chat/history")
def get_chat_history():
    return CHAT_HISTORY


@app.post("/api/v1/chat")
async def chat_endpoint(req: ChatRequest):
    """LLM + 태그 기반 전략 추천 + ReAct 분석"""
    user_msg = req.message.strip()
    if not ai_model:
        return {"reply": "⚠️ Gemini API 연결 안됨.", "recommendations": []}

    try:
        context_info = get_current_context()
        recent_history = CHAT_HISTORY[-6:]
        history_text = "\n".join(
            [f"- {m['sender']}: {m['text']}" for m in recent_history]
        )

        # 🔥 태그 강제 규칙 포함한 프롬프트
        prompt = f"""
당신은 'AI 트레이딩 비서'입니다.

[실시간 정보]
{context_info}

[이전 대화 요약]
{history_text}

[태그 규칙 - 절대 어기지 마세요]
- 사용자가 "공격", "공격적", "공격적인", "공격적으로", "공격형", "하이리스크" 등의 표현을 사용하면
  -> 응답 첫 줄에 반드시 [AGGRESSIVE] 태그를 출력합니다.

- 사용자가 "안정", "안정적", "안정적인", "안전하게", "저위험", "보수적" 등의 표현을 사용하면
  -> 응답 첫 줄에 반드시 [STABLE] 태그를 출력합니다.

- 태그는 반드시 응답의 "첫 줄 맨 앞"에 위치해야 하며,
  그 아래 줄부터 자연어 설명을 작성합니다.

[명령 태그 예시]
- 전략 추천: "공격적인 전략" -> [AGGRESSIVE]
- 전략 추천: "안정적으로 투자" -> [STABLE]
- 전략 초기화: "봇 꺼줘", "기본으로" -> [DEFAULT]
- 긴급 매도: "다 팔아!", "손절" -> [PANIC_SELL]
- 설정 변경: "레버리지 5배" -> [SET_LEV:5]
- 설정 변경: "비중 20%" -> [SET_RISK:20]
- 전체 전략 목록: "전략 다 보여줘" -> [SHOW_ALL]

[사용자 메시지]
"{user_msg}"

위 규칙에 따라 필요하면 태그를 활용한 응답을 생성하세요.
태그가 없다면 일반적인 설명만 출력해도 됩니다.
"""

        response = ai_model.generate_content(prompt)
        reply_text = response.text.strip()

        clean_reply = reply_text
        recommendations: list[dict] = []

        # 1) 수동 분석 명령 처리 (ReAct)
        if "분석" in user_msg or "analyze" in user_msg.lower():
            react_trader.run_react_loop()
            clean_reply = react_trader.get_chat_summary()

            if react_trader.suggested_strategy_id:
                s_id = react_trader.suggested_strategy_id
                if s_id in STRATEGY_MAP:
                    s = STRATEGY_MAP[s_id]
                    recommendations = [
                        {"id": s_id, "name": s.name, "return": 0, "mdd": 0}
                    ]

        # 2) 태그 기반 처리
        else:
            # 공격적 / 안정적 전략 추천
            if "[AGGRESSIVE]" in reply_text:
                clean_reply = reply_text.replace("[AGGRESSIVE]", "").strip()
                recommendations = get_recommended_strategies("aggressive")

            elif "[STABLE]" in reply_text:
                clean_reply = reply_text.replace("[STABLE]", "").strip()
                recommendations = get_recommended_strategies("stable")

            elif "[DEFAULT]" in reply_text:
                clean_reply = reply_text.replace("[DEFAULT]", "").strip()
                recommendations = [
                    {
                        "id": 0,
                        "name": "전략 미선택 (매매 중지)",
                        "return": 0,
                        "mdd": 0,
                    }
                ]

            elif "[SHOW_ALL]" in reply_text:
                clean_reply = reply_text.replace("[SHOW_ALL]", "").strip()
                recommendations = get_all_strategies()

            elif "[PANIC_SELL]" in reply_text:
                clean_reply = reply_text.replace("[PANIC_SELL]", "").strip()
                res_msg = strategy_agent.panic_sell_all()
                clean_reply += f"\n\n(시스템: {res_msg})"

            elif "[SET_LEV:" in reply_text:
                import re

                match = re.search(r"\[SET_LEV:(\d+)\]", reply_text)
                if match:
                    val = match.group(1)
                    res_msg = strategy_agent.update_settings(leverage=val)
                    clean_reply = (
                        reply_text.replace(match.group(0), "").strip()
                        + f"\n\n(시스템: {res_msg})"
                    )

            elif "[SET_RISK:" in reply_text:
                import re

                match = re.search(r"\[SET_RISK:(\d+)\]", reply_text)
                if match:
                    val = match.group(1)
                    res_msg = strategy_agent.update_settings(risk=val)
                    clean_reply = (
                        reply_text.replace(match.group(0), "").strip()
                        + f"\n\n(시스템: {res_msg})"
                    )

        # 대화 내역 저장
        CHAT_HISTORY.append({"sender": "user", "text": user_msg})
        CHAT_HISTORY.append({"sender": "bot", "text": clean_reply})

        return {"reply": clean_reply, "recommendations": recommendations}

    except Exception as e:
        return {"reply": f"오류: {e}", "recommendations": []}


# ============================================================
# [전략 선택 (백테스트 + DB 저장)]
# ============================================================
class StrategySelectRequest(BaseModel):
    strategy_id: int


@app.post("/api/v1/select-strategy")
async def select_strategy(req: StrategySelectRequest):
    s_id = req.strategy_id
    if s_id in STRATEGY_MAP:
        selected_strat = STRATEGY_MAP[s_id]

        # [NEW] 최적화된 설정이 캐시에 있다면 우선 적용
        cached_data = load_backtest_result(s_id)
        if cached_data and 'config' in cached_data:
            opt_config = cached_data['config']
            # 에이전트 설정 업데이트
            strategy_agent.leverage = opt_config.get('leverage', strategy_agent.leverage)
            strategy_agent.risk_percent = opt_config.get('risk_percent', strategy_agent.risk_percent)
            
            # 전략 객체에도 주입
            selected_strat.leverage = strategy_agent.leverage
            selected_strat.risk_percent = strategy_agent.risk_percent
            
            print(f"[API] ⚡ 최적화 설정 적용: {selected_strat.name} (Lev {strategy_agent.leverage}x, Risk {strategy_agent.risk_percent}%)")
            
            if hasattr(strategy_agent, "switch_strategy"):
                strategy_agent.switch_strategy(selected_strat)
                
            return {
                "status": "success",
                "message": f"전략 변경 완료 (최적 설정): {selected_strat.name}",
                "markers": cached_data.get('markers', []),
                "equity_curve": cached_data.get('equity_curve', []),
            }

        # 현재 에이전트 설정 주입 (Fallback)
        selected_strat.leverage = strategy_agent.leverage
        selected_strat.risk_percent = strategy_agent.risk_percent

        if hasattr(strategy_agent, "switch_strategy"):
            strategy_agent.switch_strategy(selected_strat)

        backtest_markers = []
        equity_curve = []

        try:
            df = _load_candles_safe()
            if df is not None and not df.empty:
                print(
                    f"[API] {selected_strat.name} 전체 데이터({len(df)}개) 백테스트 시작 (Lev: {selected_strat.leverage}x)..."
                )
                bt_agent = BacktestAgent(initial_equity=10000.0)
                res = bt_agent.run_single_strategy(df, selected_strat)
                backtest_markers = res.get("trade_markers", [])
                equity_curve = res.get("equity_curve", [])

                save_data = {
                    "equity_curve": equity_curve,
                    "markers": backtest_markers,
                }
                save_backtest_result(s_id, save_data)
                print(
                    f"[API] 백테스트 결과 DB 저장 완료 (마커 {len(backtest_markers)}개)"
                )
        except Exception as e:
            print(f"[API Error] 백테스트 실패: {e}")

        return {
            "status": "success",
            "message": f"전략 변경 완료: {selected_strat.name}",
            "markers": backtest_markers,
            "equity_curve": equity_curve,
        }

    return {
        "status": "error",
        "message": "전략 변경 실패",
        "markers": [],
        "equity_curve": [],
    }

# ---------------------------------------------------------
# AI 투자 성향 심층 면접 API
# ---------------------------------------------------------

class UserAnswer(BaseModel):
    question: str
    answer: str

class PersonalityContext(BaseModel):
    history: list[UserAnswer]

@app.post("/api/v1/personality/next-question")
async def generate_personality_question(ctx: PersonalityContext):
    """
    투자 성향 분석 질문 생성기
    - Q1: 투자 경험 유무 (고정 질문)
    - Q2~: 비트코인/선물 거래 경험 및 성향 파악 (AI 생성)
    """
    
    # 1. [고정 질문] 첫 번째 질문은 무조건 투자 경험을 물어봅니다.
    if not ctx.history:
        return {
            "q": "본격적인 시작에 앞서, 투자를 직접 해보신 경험이 있으신가요?",
            "options": [
                { "t": "아니요, 투자가 처음입니다.", "s": 1 },
                { "t": "주식이나 코인을 소액으로 해봤습니다.", "s": 2 },
                { "t": "코인 현물 거래 경험이 꽤 있습니다.", "s": 3 },
                { "t": "네, 선물(Futures)이나 마진 거래 경험도 있습니다.", "s": 4 }
            ]
        }

    # 2. [AI 질문 생성] 두 번째 질문부터는 이전 답변을 바탕으로 AI가 생성합니다.
    history_text = "\n".join(
        [f"- 질문{i+1}: {h.question}\n  답변: {h.answer}" for i, h in enumerate(ctx.history)]
    )
    
    q_num = len(ctx.history) + 1
    
    prompt = f"""
    당신은 '비트코인 시스템 트레이딩 봇'의 AI 면접관입니다.
    사용자의 투자 성향을 파악하여 **비트코인(암호화폐) 선물 거래 전략**을 추천하기 위한 객관식 질문을 생성하세요.

    [현재 상황]
    - 현재 {q_num}번째 질문입니다.
    - 이전 대화 기록:
    {history_text}

    [필수 규칙 - 절대 어기지 마세요]
    1. **오직 '비트코인'과 '암호화폐'에 대해서만 이야기하세요.** (주식, 부동산, 채권, 적금 등 다른 자산 언급 금지)
    2. **질문 단계별 가이드:**
       - **현재 질문 번호: {q_num}**
       
       [CASE 1: 현재가 2번째 질문일 경우]
       - 만약 1번 질문(경험 유무)에서 사용자가 "경험이 있다"고 답했다면: 
         -> **"비트코인 선물(Futures)이나 레버리지/마진 거래를 해본 적이 있는지"** 물어보세요.
       - 만약 "경험이 없다"고 답했다면: 
         -> **"일시적인 마이너스 수익률(손실)을 얼마나 견딜 수 있는지"** 심리적인 부분을 물어보세요.

       [CASE 2: 현재가 3번째 ~ 10번째 질문일 경우]
       - 이전 답변들의 맥락을 파악하여, **겹치지 않는 새로운 심층 질문**을 던지세요.
       - 추천 주제: 투자 목표 기간, 목표 수익률, 운용 가능한 자금 규모, 손절 원칙, 차트 분석 능력 등.
       - **절대 이전에 했던 질문을 반복하지 마세요.**
    3. 선택지(options)는 4개를 만들고, 점수('s')를 부여하세요.
       (1점: 극도로 안전 지향 ~ 4점: 고위험 고수익 선호)
    4. **반드시 아래 JSON 형식으로만 응답하세요.**

    [JSON 예시]
    {{
        "q": "비트코인 가격이 하루에 10% 급락했습니다. 선물 포지션이 청산 위기라면 어떻게 하시겠습니까?",
        "options": [
            {{ "t": "무서워서 즉시 손절한다.", "s": 1 }},
            {{ "t": "상황을 지켜본다.", "s": 2 }},
            {{ "t": "물타기(추가 매수)를 시도한다.", "s": 3 }},
            {{ "t": "고배율 숏 포지션으로 스위칭하여 멘징한다.", "s": 4 }}
        ]
    }}
    """

    try:
        response = ai_model.generate_content(prompt)
        text = response.text.strip()
        
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
            
        question_data = json.loads(text)
        return question_data

    except Exception as e:
        print(f"[Personality AI Error] {e}")
        return {
            "q": f"[오류 발생] AI 연결 상태를 확인해주세요.\n(에러 내용: {str(e)})\n\n변동성이 큰 비트코인 시장에서, 원금 손실을 어디까지 감내하실 수 있나요?",
            "options": [
                { "t": "원금 보장이 최우선입니다 (손실 싫음)", "s": 1 },
                { "t": "-5% 정도는 괜찮습니다", "s": 2 },
                { "t": "-20%까지는 버틸 수 있습니다", "s": 3 },
                { "t": "청산 당하더라도 고수익을 노립니다", "s": 4 }
            ]
        }

class GreetingRequest(BaseModel):
    score: int

@app.post("/api/v1/chat/greeting")
async def chat_greeting(req: GreetingRequest):
    """
    [최종 수정] 모듈 임포트 명시화 및 예외 처리 강화
    """
    # [핵심] 여기서 명시적으로 import를 해줍니다. (NameError 방지)
    import db_handler
    
    global CHAT_HISTORY
    CHAT_HISTORY.clear() 

    # 1. 사용자 성향 파악 (저장된 성향이 있으면 우선 사용)
    score = req.score
    
    # 성향 점수 파일 저장/로드 로직
    PERSONALITY_FILE = "personality.json"
    
    if score > 0:
        # 점수가 전달되었으면 파일에 저장
        try:
            with open(PERSONALITY_FILE, "w") as f:
                json.dump({"score": score}, f)
        except Exception as e:
            print(f"[System] 성향 저장 실패: {e}")
    else:
        # 점수가 0(없음)이면 파일에서 로드 시도
        try:
            if os.path.exists(PERSONALITY_FILE):
                with open(PERSONALITY_FILE, "r") as f:
                    data = json.load(f)
                    score = data.get("score", 0)
                    print(f"[System] 저장된 성향 점수 로드: {score}")
        except Exception as e:
            print(f"[System] 성향 로드 실패: {e}")

    user_type = "안정 추구형 (Low Risk)"
    if score >= 10: user_type = "공격적인 고수익 추구형 (High Risk)"
    elif score >= 7: user_type = "균형 잡힌 중립형 (Moderate Risk)"

    # 2. 데이터 가져오기
    recommendation_list = []
    market_status_text = ""
    
    try:
        # 이제 db_handler를 확실하게 인식합니다.
        strategies = db_handler.get_all_strategies()
        print(f"[API] DB 조회 결과: {len(strategies)}개 전략 발견")

        if not strategies or len(strategies) == 0:
            loading_msg = (
                f"반갑습니다! 고객님의 성향은 **'{user_type}'**으로 분석되었습니다.\n\n"
                "현재 AI가 전체 시장 데이터를 기반으로 **전략 최적화(Optimization)**를 진행 중입니다. "
                "약 1~2분 뒤에 다시 말을 걸어주시면, 가장 완벽한 전략을 추천해 드리겠습니다! ⏳"
            )
            CHAT_HISTORY.append({"sender": "bot", "text": loading_msg})
            return {"reply": loading_msg, "recommendations": []}

        # 데이터가 있으면 -> 수익률 순 정렬
        sorted_strats = sorted(strategies, key=lambda x: x['return'], reverse=True)
        top_strats = sorted_strats[:4] 
        
        market_status_text = "현재 실전 운용 가능한 전략 목록 (Fact):\n"
        for s in top_strats:
            market_status_text += f"- 전략명: [{s['name']}], 수익률: {s['return']}%, MDD: {s['mdd']}%\n"
            
            recommendation_list.append({
                "id": s['id'],
                "name": s['name'],
                "return": s['return'],
                "mdd": s['mdd']
            })
            
    except Exception as e:
        print(f"[API Error] 전략 로드 실패: {e}")
        err_msg = "죄송합니다. 내부 데이터베이스 연결에 일시적인 문제가 발생했습니다."
        return {"reply": err_msg, "recommendations": []}

    # 3. AI 프롬프트
    prompt = f"""
    당신은 비트코인 AI 트레이딩 비서입니다.
    
    [사용자 정보]
    - 성향: **'{user_type}' (점수: {score}/12)**
    
    [현재 승률 상위 전략 데이터]
    {market_status_text}

    [작성 규칙]
    1. **성향 분석:** 사용자의 성향(안정/공격)에 대해 간단히 코멘트하세요.
    2. **전략 추천:** 위 [현재 승률 상위 전략 데이터] 목록 중에서, 사용자의 성향에 가장 잘 맞는 것 **하나를 골라 이름을 정확히 언급**하며 추천하세요.
       - 예: "고객님께는 수익률 00%를 기록 중인 **'OOO 전략'**을 추천합니다."
    3. **근거 제시:** 추천한 전략의 수익률과 MDD 수치를 인용하여 이유를 설명하세요.
    4. 절대 목록에 없는 가상의 전략 이름을 지어내지 마세요.
    """

    try:
        resp = ai_model.generate_content(prompt)
        reply_text = resp.text.strip()
        CHAT_HISTORY.append({"sender": "bot", "text": reply_text})
        
        return {
            "reply": reply_text,
            "recommendations": recommendation_list 
        }
    except Exception as e:
        return {"reply": "AI 응답 생성 중 오류가 발생했습니다.", "recommendations": []}


# ============================================================
# [ReAct 관련 API]
# ============================================================
@app.get("/api/v1/react/status")
def get_react_status():
    return {
        "observation": react_trader.current_observation,
        "thought": react_trader.current_thought,
        "action": react_trader.current_action,
        "analysis_results": react_trader.analysis_results,
        "suggested_strategy_id": react_trader.suggested_strategy_id,
    }


@app.post("/api/v1/react/analyze")
def trigger_react_analysis():
    try:
        result = react_trader.run_react_loop()
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/v1/react/approve-switch")
def approve_strategy_switch():
    try:
        msg = react_trader.apply_suggested_strategy()
        return {"status": "success", "message": msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}



@app.get("/api/v1/personality")
async def get_personality():
    PERSONALITY_FILE = "personality.json"
    try:
        if os.path.exists(PERSONALITY_FILE):
            with open(PERSONALITY_FILE, "r") as f:
                data = json.load(f)
                return data
        return {"score": 0}
    except Exception as e:
        return {"score": 0, "error": str(e)}

# ============================================================
# [WebSocket 엔드포인트]
# ============================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ============================================================
# [Entry Point]
# ============================================================
if __name__ == "__main__":
    uvicorn.run("main_api:app", host="0.0.0.0", port=8000, reload=True)
