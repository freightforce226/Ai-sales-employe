import requests

def main():
    url = "http://localhost:8000/api/v1/ai-reply/complete"
    headers = {
        "X-API-Key": "freightforce-dev-123",
        "Content-Type": "application/json"
    }
    payload = {
        "message_id": "AQMkADAwATNiZmYAZS1hZjRiLTVjMDItMDACLTAwCgBGAAADvPkW3AHC8Eul5yg1iSsQogcA1Woe4kkRVkCJrHuz0FRo8wAAAgEPAAAA1Woe4kkRVkCJrHuz0FRo8wAAAEAJOo8AAAA=",
        "sent_at": "2026-07-23T04:05:13.435728Z"
    }
    
    print("Testing POST /api/v1/ai-reply/complete...")
    res = requests.post(url, headers=headers, json=payload)
    print("Status Code:", res.status_code)
    print("Response Body:", res.json())

if __name__ == "__main__":
    main()
