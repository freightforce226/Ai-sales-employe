import asyncio
import httpx

async def main():
    url = "http://localhost:5678/webhook/customer-import"
    headers = {
        "X-API-Key": "freightforce-dev-123"
    }
    payload = {
        "batch_id": "00000000-0000-0000-0000-000000000000",
        "organization_id": "00000000-0000-0000-0000-000000000000",
        "file_path": "https://dnbobdyycoxjzgzrepcu.supabase.co/storage/v1/object/authenticated/csv-imports/test.csv",
        "column_mapping": {}
    }
    
    print(f"Sending test POST to {url}...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=5.0)
            print("Status Code:", response.status_code)
            print("Response Body:", response.text)
        except Exception as e:
            print("Error connecting to n8n:", str(e))

if __name__ == "__main__":
    asyncio.run(main())
