# backend/db_handler.py

import psycopg2
from psycopg2.extras import DictCursor, execute_values  # <--- [수정] execute_values 추가 (인코딩 해결용)
import pandas as pd
import json
import time
import os
from strategies import STRATEGY_MAP, NoStrategy
import optimizer
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

# --- 1. DB 연결 및 초기화 ---

def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn

def init_db():
    print(f"[DB] PostgreSQL 연결 시도: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 전략 성과 요약 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS strategy_perf (
                id INTEGER PRIMARY KEY, 
                name TEXT, 
                risk_level TEXT, 
                total_return REAL, 
                mdd REAL
            )
        ''')
        
        # 캔들 데이터 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS candles (
                ts BIGINT PRIMARY KEY, 
                open REAL, 
                high REAL, 
                low REAL, 
                close REAL, 
                vol REAL
            )
        ''')
        
        # 백테스트 상세 결과(JSON) 저장 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backtest_cache (
                strategy_id INTEGER PRIMARY KEY, 
                updated_at BIGINT, 
                json_data TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        print("[DB] 데이터베이스 준비 완료.")
    except Exception as e:
        print(f"[DB Error] 초기화 실패: {e}")

# --- 2. 캔들 데이터 관리 ---

def get_latest_timestamp():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(ts) FROM candles")
        result = cursor.fetchone()[0]
        conn.close()
        return result or 0
    except Exception as e:
        print(f"[DB Error] get_latest_timestamp: {e}")
        return 0

def save_candles_bulk(candles_list):
    """
    [수정됨] execute_values를 사용하여 윈도우 인코딩 오류 해결 및 속도 향상
    """
    if not candles_list: return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 데이터 타입 변환 및 정제
        data = []
        for c in candles_list:
            try: 
                # (timestamp, open, high, low, close, vol) 순서
                data.append((int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])))
            except: 
                continue
        
        if not data: return

        # execute_values를 사용한 안전하고 빠른 대량 삽입 (CP949 인코딩 문제 해결)
        query = """
            INSERT INTO candles (ts, open, high, low, close, vol) 
            VALUES %s 
            ON CONFLICT (ts) DO NOTHING
        """
        
        execute_values(cursor, query, data)
        
        conn.commit()
        conn.close()
        # print(f"[DB] {len(data)}개 캔들 저장 완료") 
    except Exception as e:
        print(f"[DB Error] save_candles_bulk: {e}")

def load_all_candles_as_df():
    try:
        conn = get_db_connection()
        # pandas read_sql uses SQLAlchemy or DBAPI2 connection
        df = pd.read_sql("SELECT * FROM candles ORDER BY ts ASC", conn)
        conn.close()
        
        if not df.empty:
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            for c in ['open', 'high', 'low', 'close', 'vol']: 
                df[c] = df[c].astype(float)
            return df
        else:
            return pd.DataFrame()
    except Exception as e:
        print(f"[DB Error] load_all_candles_as_df: {e}")
        return pd.DataFrame()

# --- 3. 백테스트 결과 및 전략 관리 ---

def save_backtest_result(strategy_id, result_data):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        json_str = json.dumps(result_data, ensure_ascii=False, indent=2)
        
        # PostgreSQL UPSERT (있으면 업데이트, 없으면 삽입)
        cursor.execute("""
            INSERT INTO backtest_cache (strategy_id, updated_at, json_data) 
            VALUES (%s, %s, %s)
            ON CONFLICT (strategy_id) 
            DO UPDATE SET updated_at = EXCLUDED.updated_at, json_data = EXCLUDED.json_data
        """, (strategy_id, int(time.time()), json_str))
        
        conn.commit()
        conn.close()
        print(f"[DB] 백테스트 상세 데이터 저장 성공 → strategy_id={strategy_id}")
    except Exception as e:
        print(f"[DB Error] 상세 데이터 저장 실패 (id={strategy_id}): {e}")

def load_backtest_result(strategy_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT json_data FROM backtest_cache WHERE strategy_id = %s", (strategy_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            data = json.loads(row[0])
            print(f"[Cache] DB에서 전략 {strategy_id} 캐시 로드 성공")
            return data
        else:
            print(f"[Cache] DB에 전략 {strategy_id} 캐시 없음")
            return None
    except Exception as e:
        print(f"[DB Error] 백테스트 로드 실패 (id={strategy_id}): {e}")
        return None

def get_last_active_strategy_id():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT strategy_id FROM backtest_cache ORDER BY updated_at DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0]
        return 0
    except Exception as e:
        print(f"[DB Error] get_last_active_strategy_id: {e}")
        return 0

# --- 4. 전략 추천 및 조회 ---

def get_recommended_strategies(risk_level):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        target_risk = "Aggressive" if risk_level.lower() == "aggressive" else "Stable"
        
        if target_risk == "Stable":
            cursor.execute("SELECT id, name, total_return, mdd FROM strategy_perf WHERE risk_level IN ('Stable', 'Moderate') ORDER BY total_return DESC LIMIT 5")
        else:
            cursor.execute("SELECT id, name, total_return, mdd FROM strategy_perf WHERE risk_level = 'Aggressive' ORDER BY total_return DESC LIMIT 5")
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r[0], "name": r[1], "return": r[2], "mdd": r[3]} for r in rows]
    except Exception as e:
        print(f"[DB Error] get_recommended_strategies: {e}")
        return []

def get_all_strategies():
    result = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, total_return, mdd FROM strategy_perf ORDER BY total_return DESC")
        rows = cursor.fetchall()
        conn.close()
        if rows:
            for r in rows:
                result.append({"id": r[0], "name": r[1], "return": round(r[2], 2), "mdd": round(abs(r[3]), 2)})
    except Exception as e:
        print(f"[DB Error] get_all_strategies: {e}")
    return result

def get_strategy_perf(strategy_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT risk_level, total_return, mdd FROM strategy_perf WHERE id=%s", (strategy_id,))
        row = cursor.fetchone()
        conn.close()
        return row
    except Exception as e:
        print(f"[DB Error] get_strategy_perf: {e}")
        return None

# --- 5. 배치 최적화 실행 ---

def run_batch_backtest(df):
    if df is None or df.empty: return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM strategy_perf")
        count = cursor.fetchone()[0]
        
        if count > 0: 
            print(f"[DB] ✅ 이미 최적화된 데이터({count}개)가 존재합니다. 스킵합니다.")
            conn.close()
            return

        print(f"[DB] 🚀 모든 전략({len(STRATEGY_MAP)-1}개) 정밀 최적화 시작...")
        cursor.execute("DELETE FROM strategy_perf") 
        
        count_success = 0
        
        for s_id, strategy in STRATEGY_MAP.items():
            if s_id == 0 or isinstance(strategy, NoStrategy): continue
                
            try:
                print(f"   👉 [{count_success+1}/{len(STRATEGY_MAP)-1}] '{strategy.name}' 최적화 중...")
                
                best_config, best_res = optimizer.find_optimal_settings(df, s_id)
                
                if best_config and best_res:
                    trade_markers = best_res.get('trade_markers', [])
                    trade_count = len(trade_markers)
                    
                    if trade_count == 0:
                        print(f"      -> 거래 없음 (Skip)")
                        continue

                    best_res['summary'] = best_res.get('summary', {})
                    best_res['summary']['trade_count'] = trade_count

                    ret = best_config['total_return']
                    mdd = best_config['mdd']
                    lev = best_config['leverage']

                    # 1. 요약 테이블 저장 (목록용)
                    cursor.execute("""
                        INSERT INTO strategy_perf (id, name, risk_level, total_return, mdd)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (s_id, strategy.name, strategy.risk_level, round(ret, 2), round(mdd, 2)))
                    
                    # 2. [중요] 상세 데이터 테이블 저장 (상세보기용)
                    save_backtest_result(s_id, best_res)
                    
                    print(f"      ✅ 완료 & 저장! ROI: {round(ret,2)}% (Lev {lev}x)")
                    count_success += 1
                else:
                    print("      -> 최적화 실패")

            except Exception as e:
                print(f"      ⚠️ 에러: {e}")

        conn.commit()
        conn.close()
        print(f"[DB] 🎉 모든 전략 최적화 및 저장 완료! (총 {count_success}개)")
    except Exception as e:
        print(f"[DB Error] run_batch_backtest: {e}")