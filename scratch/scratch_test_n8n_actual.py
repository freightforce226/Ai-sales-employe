import asyncio
import httpx

async def main():
    url = "http://localhost:5678/webhook/customer-import"
    headers = {
        "X-API-Key": "freightforce-dev-123"
    }
    payload = {
        "import_batch_id": "00000000-0000-0000-0000-000000000000",
        "organization_id": "97550311-89c4-464a-acb4-af5133fdeece",
        "storage_path": "97550311-89c4-464a-acb4-af5133fdeece/117e3679-a442-48c4-9a1a-6e6b9d48e2a5_importers data (1).csv",
        "header_row": 1,
        "column_mapping": {
            "company_name": "IMPORTER  NAME",
            "contact_email": "CONTACT INFO"
        }
    }
    
    async with httpx.AsyncClient() as client:
        res = await client.post(url, json=payload, headers=headers)
        print("Status Code:", res.status_code)
        print("Response Body:")
        print(res.text)

if __name__ == '__main__':
    asyncio.run(main())
