# backend/data_sync.py
import time
import rest_client
import db_handler

def sync_market_data(instId="BTC-USDT-SWAP", bar="30m"):
    """
    OKX 서버와 로컬 DB 동기화 (기본 30m 설정)
    """
    print(f"[Sync] 🔄 '{instId}' ({bar}) 데이터 동기화 시작...")
    
    last_db_ts = db_handler.get_latest_timestamp()
    
    if last_db_ts > 0:
        print(f"[Sync] 📅 로컬 데이터 발견: 마지막 기록 {last_db_ts}")
    else:
        print(f"[Sync] 📂 로컬 데이터 없음. 전체 다운로드 시작...")

    cursor_after = None 
    total_fetched = 0
    
    while True:
        limit = 100
        params = f"?instId={instId}&bar={bar}&limit={limit}"
        if cursor_after:
            params += f"&after={cursor_after}"
            
        res = rest_client.public_get(f"/api/v5/market/history-candles{params}")
        
        if not res or res.get("code") != "0":
            print(f"[Sync] ⚠️ API 종료/오류: {res}")
            break
            
        candles = res.get("data", [])
        if not candles:
            break
        
        new_candles = []
        stop_sync = False
        
        for c in candles:
            ts = int(c[0])
            if ts > last_db_ts:
                new_candles.append(c)
            else:
                stop_sync = True
        
        if new_candles:
            db_handler.save_candles_bulk(new_candles)
            total_fetched += len(new_candles)
            cursor_after = new_candles[-1][0] 
        else:
            stop_sync = True

        if total_fetched > 0 and total_fetched % 1000 == 0:
            print(f"[Sync] 📥 {total_fetched}개 저장 중...")

        if stop_sync:
            break
            
        time.sleep(0.1) # Rate Limit 방지

    print(f"[Sync] ✅ 동기화 완료. {total_fetched}개 업데이트.")
    return db_handler.load_all_candles_as_df()