import requests
import json

try:
    res = requests.post(
        "http://127.0.0.1:8000/api/v1/generate-report",
        headers={"Content-Type": "application/json"},
        json={"period": "monthly"}
    )
    print(res.status_code)
    print(res.text[:200])
except Exception as e:
    print(e)
