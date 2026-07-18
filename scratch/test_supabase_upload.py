"""
Diagnostic test to pinpoint the exact Supabase upload failure.
"""
import asyncio
import httpx
import os
import sys

# Load settings from env
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')
from app.core.config import get_settings

settings = get_settings()

async def main():
    print(f"Supabase URL: {settings.supabase_url}")
    print(f"Service Role Key (first 20 chars): {settings.supabase_service_role_key[:20]}...")
    print("-" * 60)

    # Test 1: Try to upload a PNG to tenant-attachments
    dummy_png = b"fake png data"
    storage_path = "test-org/test-uuid_test.png"
    upload_url = f"{settings.supabase_url}/storage/v1/object/tenant-attachments/{storage_path}"

    print(f"Uploading PNG to: {upload_url}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                upload_url,
                content=dummy_png,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "Content-Type": "image/png"
                }
            )
            print(f"PNG Upload Status: {res.status_code}")
            print(f"PNG Upload Response: {res.text[:500]}")
    except Exception as e:
        print(f"PNG Upload Exception: {type(e).__name__}: '{str(e)}'")
        import traceback
        traceback.print_exc()

    print("-" * 60)

    # Test 2: Try to upload a PDF to tenant-attachments
    dummy_pdf = b"%PDF-1.4\n%..."
    pdf_path = "test-org/test-uuid_brochure.pdf"
    pdf_upload_url = f"{settings.supabase_url}/storage/v1/object/tenant-attachments/{pdf_path}"

    print(f"Uploading PDF to: {pdf_upload_url}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                pdf_upload_url,
                content=dummy_pdf,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "Content-Type": "application/pdf"
                }
            )
            print(f"PDF Upload Status: {res.status_code}")
            print(f"PDF Upload Response: {res.text[:500]}")
    except Exception as e:
        print(f"PDF Upload Exception: {type(e).__name__}: '{str(e)}'")
        import traceback
        traceback.print_exc()

    print("-" * 60)

    # Test 3: List buckets to confirm tenant-attachments exists
    buckets_url = f"{settings.supabase_url}/storage/v1/bucket"
    print(f"Listing Supabase buckets at: {buckets_url}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(
                buckets_url,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                }
            )
            print(f"Buckets Status: {res.status_code}")
            print(f"Buckets Response: {res.text[:1000]}")
    except Exception as e:
        print(f"Buckets Exception: {type(e).__name__}: '{str(e)}'")

asyncio.run(main())
