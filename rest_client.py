# rest_client.py
# -----------------
# 주문 실행 및 계정 조회 (REST API) 담당

import requests
import json
import hmac
import base64
import time
from config import API_KEY, SECRET_KEY, PASSPHRASE, IS_DEMO, DEMO_HEADER_KEY, DEMO_HEADER_VALUE, BASE_URL

# --- 인증 헤더 생성 함수 ---
def _get_rest_auth_headers(method, request_path, body=''):
    iso_timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.', time.gmtime(time.time())) + f"{int(time.time() * 1000) % 1000:03d}Z"
    body_str = json.dumps(body) if body else ''
    message = iso_timestamp + method + request_path + body_str
    
    mac = hmac.new(bytes(SECRET_KEY, encoding='utf-8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    sign = base64.b64encode(mac.digest()).decode('utf-8')

    headers = {
        'Content-Type': 'application/json',
        'OK-ACCESS-KEY': API_KEY,
        'OK-ACCESS-SIGN': sign,
        'OK-ACCESS-TIMESTAMP': iso_timestamp,
        'OK-ACCESS-PASSPHRASE': PASSPHRASE
    }

    if IS_DEMO:
        headers[DEMO_HEADER_KEY] = DEMO_HEADER_VALUE
    return headers

# --- 공개 API 호출 헬퍼 (auth 없이) ---
def public_get(request_path):
    method = 'GET'
    url = BASE_URL + request_path
    print(f"[API 요청] 공개 GET: {request_path}")
    try:
        response = requests.get(url)
        return response.json()
    except Exception as e:
        print(f"[API 오류] 공개 GET: {e}")
        return None

# --- 범용 주문 함수 (양방향) ---
def place_order(instId, tdMode, side, ordType, sz, posSide, px=None):
    request_path = "/api/v5/trade/order"
    method = 'POST'
    url = BASE_URL + request_path
    
    order_body = {
        "instId": instId, "tdMode": tdMode, "side": side,
        "ordType": ordType, "sz": sz, "posSide": posSide
    }
    if ordType == 'limit':
        order_body['px'] = px

    headers = _get_rest_auth_headers(method, request_path, order_body)
    
    print(f"[API 요청] 신규 주문: {instId} {side} ({posSide}) {sz}@{ordType}")
    try:
        response = requests.post(url, headers=headers, data=json.dumps(order_body))
        return response.json()
    except Exception as e:
        print(f"[API 오류] 신규 주문: {e}")
        return None

# --- 계정 설정 (양방향 모드) ---
def set_position_mode_long_short():
    request_path = "/api/v5/account/set-position-mode"
    method = 'POST'
    url = BASE_URL + request_path
    body = {"posMode": "long_short_mode"}
    headers = _get_rest_auth_headers(method, request_path, body)
    
    print(f"\n[API 요청] 계정 포지션 모드를 'long_short_mode' (양방향)로 설정 시도...")
    try:
        response = requests.post(url, headers=headers, data=json.dumps(body))
        result = response.json()
        if result.get("code") == "0":
            print("[계정 설정 성공] 포지션 모드가 'long_short_mode'로 설정되었습니다.")
        else:
            print(f"[계정 설정 실패] {result.get('msg')}")
        return result
    except Exception as e:
        print(f"[API 오류] 계정 설정: {e}")
        return None

# --- [신규] 과거 3개월 거래 내역 조회 ---
def get_transaction_history_3months(instType="SWAP", limit="100"):
    """
    최근 3개월 간의 거래 내역(체결 내역)을 조회합니다.
    엔드포인트: /api/v5/trade/fills-history (최근 3일은 fills, 3개월은 fills-history)
    """
    request_path = f"/api/v5/trade/fills-history?instType={instType}&limit={limit}"
    
    method = 'GET'
    url = BASE_URL + request_path
    headers = _get_rest_auth_headers(method, request_path, '')
    
    print(f"[API 요청] 3개월치 거래 내역 조회 (fills-history)")
    try:
        response = requests.get(url, headers=headers)
        return response.json()
    except Exception as e:
        print(f"[API 오류] 거래 원장 조회: {e}")
        return None

# --- 과거 캔들 조회 (공개 API – auth 제거) ---
def get_historical_candles(instId, bar="30m", limit=100, max_bars=10000):
    all_candles = []
    after_ts = None
    
    print(f"[페이징 시작] {instId} {bar} - 최대 {max_bars}바 로드 목표")
    while len(all_candles) < max_bars:
        params = f"?instId={instId}&bar={bar}&limit={limit}"
        if after_ts:
            params += f"&after={after_ts}"
        
        request_path = f"/api/v5/market/history-candles{params}"
        
        # ✅ public_get 사용 (auth 헤더 없음)
        data = public_get(request_path)
        
        if data and data.get("code") == "0" and data.get("data"):
            new_candles = data["data"]
            all_candles.extend(new_candles)
            if len(new_candles) < limit:
                break
            after_ts = int(new_candles[-1][0])  # 문자열 → int 변환

            time.sleep(0.1) # Rate limit 방지
        else:
            print(f"[API 오류] {data.get('msg') if data else 'No data'}")
            break
    
    # 최신순으로 정렬 (역순: 과거 → 최신)
    all_candles.reverse()
    print(f"[완료] 총 {len(all_candles)}바 캔들 로드 ({bar}, {instId})")
    return all_candles  # [[ts, open, high, low, close, vol, ...], ...]