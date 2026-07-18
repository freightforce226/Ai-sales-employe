import asyncio
import httpx

async def main():
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            r = await client.post(
                'http://localhost:8000/api/v1/auth/login',
                json={'email': 'dev@freightforce.ai', 'password': '123456'}
            )
            print('Login Status:', r.status_code)
            print('Login Response:', r.text[:300])
        except Exception as e:
            print('Error:', type(e).__name__, str(e))

asyncio.run(main())
