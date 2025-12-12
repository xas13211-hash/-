# tests/test_api_react.py
import requests
import time

BASE_URL = "http://localhost:8000/api/v1"

def test_react_status():
    print("Testing GET /react/status...")
    try:
        res = requests.get(f"{BASE_URL}/react/status")
        if res.status_code == 200:
            data = res.json()
            print("✅ Status OK")
            print(f"   Observation: {data.get('observation')}")
            print(f"   Action: {data.get('action')}")
        else:
            print(f"❌ Failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

def test_trigger_analysis():
    print("\nTesting POST /react/analyze...")
    try:
        res = requests.post(f"{BASE_URL}/react/analyze")
        if res.status_code == 200:
            data = res.json()
            print("✅ Analysis Triggered")
            print(f"   Result: {data}")
        else:
            print(f"❌ Failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("⚠️ Make sure the backend server is running on port 8000!")
    test_react_status()
    # test_trigger_analysis() # Uncomment to trigger analysis (may take time)
