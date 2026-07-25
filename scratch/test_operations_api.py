import asyncio
import sys
import requests

def main():
    headers = {
        "X-API-Key": "freightforce-dev-123",
        "X-Organization-ID": "d519ac7f-9c38-46c6-a981-0426cf6e561b",
        "Content-Type": "application/json"
    }

    # Since operations endpoints require user authentication or org header injection,
    # let's call the API directly using mock headers or verify response structures.
    # Note: Local uvicorn is running. Let's make request with organization header:
    print("Testing GET /api/v1/ai-reply/dashboard...")
    res_dash = requests.get("http://localhost:8000/api/v1/ai-reply/dashboard", headers=headers)
    print("Dashboard Status:", res_dash.status_code)
    print("Dashboard Content:", res_dash.json() if res_dash.status_code == 200 else res_dash.text)

    print("\nTesting GET /api/v1/ai-reply/list...")
    res_list = requests.get("http://localhost:8000/api/v1/ai-reply/list", headers=headers)
    print("List Status:", res_list.status_code)
    data_list = res_list.json() if res_list.status_code == 200 else []
    print("List count:", len(data_list))

    if data_list:
        sample_id = data_list[0]["reply_id"]
        print(f"\nTesting GET /api/v1/ai-reply/{sample_id}...")
        res_detail = requests.get(f"http://localhost:8000/api/v1/ai-reply/{sample_id}", headers=headers)
        print("Detail Status:", res_detail.status_code)
        print("Detail Keys:", list(res_detail.json().keys()) if res_detail.status_code == 200 else res_detail.text)

if __name__ == "__main__":
    main()
