# backend/websocket_manager.py
# -----------------
# 실시간 데이터 수신 (WebSocket) 담당
# [수정] 25초마다 Ping을 보내는 Keep-Alive 기능 추가

import websocket
import json
import hmac
import base64
import time
import threading
import datetime 
from config import API_KEY, SECRET_KEY, PASSPHRASE

class OKXWebSocketManager:
    def __init__(self, ws_url, channels_to_subscribe, connection_manager=None, strategy_agent=None):
        self.api_key = API_KEY
        self.secret_key = SECRET_KEY
        self.passphrase = PASSPHRASE
        self.ws_url = ws_url
        self.channels = channels_to_subscribe
        self.ws = None
        self.should_run = True
        
        self.connection_manager = connection_manager 
        self.strategy_agent = strategy_agent     
        
        print(f"[{self.ws_url.split('/')[-1]}] 매니저 초기화 완료")

    def _get_timestamp(self):
        return str(time.time())

    def _get_sign(self, timestamp):
        message = timestamp + 'GET' + '/users/self/verify'
        mac = hmac.new(bytes(self.secret_key, encoding='utf-8'), bytes(message, encoding='utf-8'), digestmod='sha256')
        return base64.b64encode(mac.digest()).decode('utf-8')

    def _login(self):
        timestamp = self._get_timestamp()
        sign = self._get_sign(timestamp)
        login_payload = {
            "op": "login",
            "args": [
                {
                    "apiKey": self.api_key,
                    "passphrase": self.passphrase,
                    "timestamp": timestamp,
                    "sign": sign
                }
            ]
        }
        self.ws.send(json.dumps(login_payload))
        print(f"[{self.ws_url.split('/')[-1]}] 로그인 시도...")

    def _subscribe(self, channels):
        sub_payload = {
            "op": "subscribe",
            "args": channels
        }
        self.ws.send(json.dumps(sub_payload))
        print(f"[{self.ws_url.split('/')[-1]}] 구독 시도: {channels}")

    # 🛑 [신규] 25초마다 "ping"을 보내 연결을 유지하는 함수
    def _keep_alive(self):
        while self.should_run:
            time.sleep(25) # 25초 대기
            if self.ws and self.ws.sock and self.ws.sock.connected:
                try:
                    self.ws.send("ping")
                    # print(f"[{self.ws_url.split('/')[-1]}] ❤️ Heartbeat (Ping) sent")
                except Exception as e:
                    print(f"[Heartbeat Error] {e}")
                    break
            else:
                break

    def on_open(self, ws):
        print(f"[{self.ws_url.split('/')[-1]}] OKX 연결됨.")
        
        # 🛑 [신규] 연결되자마자 심장박동(Keep-Alive) 스레드 시작
        threading.Thread(target=self._keep_alive, daemon=True).start()

        if "private" in self.ws_url:
            self._login()
            time.sleep(1) 
        self._subscribe(self.channels)

    def on_message(self, ws, message):
        # 서버가 보내는 ping에는 pong으로 응답 (기존 유지)
        if message == "ping":
            self.ws.send("pong")
            return
        
        # 우리가 보낸 "ping"에 대한 서버의 "pong" 응답은 무시 (로그 안 남김)
        if message == "pong":
            return

        try:
            data = json.loads(message)
        except:
            return
        
        if "event" in data:
            if data.get("event") == "login" and data.get("code") == "0":
                print(f"[{self.ws_url.split('/')[-1]}] OKX 로그인 성공!")
            elif data.get("event") == "subscribe" and data.get("code") == "0":
                print(f"[{self.ws_url.split('/')[-1]}] OKX 구독 성공: {data.get('arg')}")
            elif data.get("event") == "error":
                print(f"[{self.ws_url.split('/')[-1]}] OKX 오류: {data.get('msg')}")
        
        elif "arg" in data and "data" in data:
            channel = data['arg']['channel']
            
            if channel == "tickers":
                ticker_data = data['data'][0]
                
                if self.connection_manager:
                    threading.Thread(target=self.connection_manager.broadcast_json_sync, 
                                     args=({"type": "ticker", "data": ticker_data},)).start()
                
                if self.strategy_agent:
                    current_price = ticker_data['last']
                    # [수정] 실제 ticker의 timestamp 사용 (ms 단위)
                    ticker_timestamp = int(ticker_data['ts'])
                    self.strategy_agent.on_new_price(current_price, ticker_timestamp)

            elif channel == "orders":
                order_data = data['data'][0]
                state = order_data.get('state')
                
                if state == 'filled':
                    print(f"✅ [OKX 실시간 원장] 체결 감지!")
                    if self.connection_manager:
                        threading.Thread(target=self.connection_manager.broadcast_json_sync, 
                                         args=({"type": "fill", "data": order_data},)).start()

    def on_error(self, ws, error):
        print(f"[OKX WS] 오류 발생: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print(f"[OKX WS] 연결 종료.")
        if self.should_run:
            print("OKX 재연결 시도...")
            time.sleep(5) 
            self.start_websocket_thread() 

    def start_websocket_thread(self):
        """백그라운드 스레드에서 WebSocket 실행"""
        # 🛑 [수정] ping_interval 추가 (라이브러리 차원의 Keep-alive 이중 안전장치)
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        ws_thread = threading.Thread(
            target=lambda: self.ws.run_forever(ping_interval=30, ping_timeout=10), 
            daemon=True
        )
        ws_thread.start()
        print(f"[{self.ws_url.split('/')[-1]}] OKX 스레드 시작.")

    def stop(self):
        self.should_run = False
        if self.ws:
            self.ws.close()