# config.py
# -----------------
# API 키 및 주요 설정 파일

# --- 1. 설정: OKX 데모 트레이딩 API 키 ---
API_KEY = "8f2e8ad1-5cb4-4c0b-acda-12fe494dd8a1"
SECRET_KEY = "C550E4CFD4A598F90FE3B132D76CD637"
PASSPHRASE = "Wlskdhek3277#"

# --- 2. 데모 트레이딩 환경 설정 ---
IS_DEMO = True  # True: 데모, False: 실계좌
DEMO_HEADER_KEY = "x-simulated-trading"
DEMO_HEADER_VALUE = "1"

# --- 3. API 엔드포인트 ---
BASE_URL = "https://www.okx.com"

# WebSocket URL (데모/실계좌)
WS_PRIVATE_URL = "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999" if IS_DEMO else "wss://ws.okx.com:8443/ws/v5/private"
WS_PUBLIC_URL = "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999" if IS_DEMO else "wss://ws.okx.com:8443/ws/v5/public"

# --- 4. Google Gemini API 키 ---
# 여기에 발급받으신 AIza... 로 시작하는 키를 입력하세요.
GEMINI_API_KEY = "AIzaSyBiQjLkEb79WOgaqh3HJRsXOkfDLHdLmkY"

# --- 5. PostgreSQL Database 설정 ---
# 로컬 DB 설정 (사용자 환경에 맞게 수정 필요)
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "trading_db"
DB_USER = "postgres"
DB_PASSWORD = "wlskdhek3277#"  # 실제 비밀번호로 변경 필요