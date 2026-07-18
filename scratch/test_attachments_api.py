import asyncio
import httpx

async def main():
    base_url = "http://localhost:8000/api/v1"
    login_url = f"{base_url}/auth/login"
    
    # 1. Login
    async with httpx.AsyncClient(timeout=60.0) as client:
        login_res = await client.post(
            login_url,
            json={"email": "dev@freightforce.ai", "password": "123456"}
        )
        print("Login Status:", login_res.status_code)
        if login_res.status_code != 200:
            print("Login failed:", login_res.text)
            return
            
        cookies = login_res.cookies
        
        # 2. Upload Invalid Attachment Type (.txt should fail with 400)
        files_invalid = {"file": ("test.txt", b"this is a text file, not a pdf", "text/plain")}
        data_invalid = {
            "attachment_name": "Test Text File",
            "attachment_type": "Product Brochure",
            "always_attach": "true",
            "status_state": "active"
        }
        res_invalid = await client.post(
            f"{base_url}/attachments",
            files=files_invalid,
            data=data_invalid,
            cookies=cookies
        )
        print("POST /attachments (.txt upload - should be 400) Status:", res_invalid.status_code)
        print("POST /attachments (.txt upload) Payload:", res_invalid.text)
        print("-" * 50)

        
        # 3. Upload Valid Attachment (PDF)
        # Create a tiny 1KB dummy PDF header
        dummy_pdf_content = b"%PDF-1.4\n%..."
        files_valid = {"file": ("brochure.pdf", dummy_pdf_content, "application/pdf")}
        data_valid = {
            "attachment_name": "Dev Product Brochure",
            "attachment_type": "Product Brochure",
            "always_attach": "true",
            "status_state": "active"
        }
        res_valid = await client.post(
            f"{base_url}/attachments",
            files=files_valid,
            data=data_valid,
            cookies=cookies
        )
        print("POST /attachments (Valid PDF) Status:", res_valid.status_code)
        if res_valid.status_code != 201:
            print("Failed PDF upload details:", res_valid.text)
            return
        
        uploaded_attachment = res_valid.json()
        attachment_id = uploaded_attachment.get("id")
        print("Uploaded attachment details:", uploaded_attachment)
        print("-" * 50)
        
        # 4. GET /attachments listing
        list_res = await client.get(f"{base_url}/attachments", cookies=cookies)
        print("GET /attachments Status:", list_res.status_code)
        print("GET /attachments Total:", list_res.json().get("total"))
        print("-" * 50)

        # 5. GET /attachments/{id} details
        detail_res = await client.get(f"{base_url}/attachments/{attachment_id}", cookies=cookies)
        print("GET /attachments/{id} Status:", detail_res.status_code)
        print("GET /attachments/{id} Name:", detail_res.json().get("attachment_name"))
        print("GET /attachments/{id} Type:", detail_res.json().get("attachment_type"))
        print("GET /attachments/{id} Always Attach:", detail_res.json().get("attach_to_every_email"))
        print("-" * 50)

        # 6. GET /attachments/{id}/download preview streaming
        download_res = await client.get(f"{base_url}/attachments/{attachment_id}/download", cookies=cookies)
        print("GET /attachments/{id}/download Status:", download_res.status_code)
        print("GET /attachments/{id}/download Content-Type:", download_res.headers.get("content-type"))
        print("GET /attachments/{id}/download Length:", len(download_res.content))
        print("-" * 50)

        # 7. PUT /attachments/{id} update metadata
        update_payload = {
            "attachment_name": "Updated Dev Product Brochure",
            "attachment_type": "Pricing Sheet",
            "always_attach": False,
            "is_active": True
        }
        update_res = await client.put(
            f"{base_url}/attachments/{attachment_id}",
            params=update_payload,
            cookies=cookies
        )
        print("PUT /attachments/{id} Status:", update_res.status_code)
        
        # Verify changes
        check_res = await client.get(f"{base_url}/attachments/{attachment_id}", cookies=cookies)
        print("Updated Name:", check_res.json().get("attachment_name"))
        print("Updated Type:", check_res.json().get("attachment_type"))
        print("Updated Always Attach:", check_res.json().get("attach_to_every_email"))
        print("-" * 50)

        # 8. POST /attachments/{id}/replace
        replace_pdf = b"%PDF-1.4\n%replaced content..."
        files_replace = {"file": ("replaced.pdf", replace_pdf, "application/pdf")}
        replace_res = await client.post(
            f"{base_url}/attachments/{attachment_id}/replace",
            files=files_replace,
            cookies=cookies
        )
        print("POST /attachments/{id}/replace Status:", replace_res.status_code)
        print("POST /attachments/{id}/replace Payload:", replace_res.json())
        print("-" * 50)

        # Verify replacement download
        check_download = await client.get(f"{base_url}/attachments/{attachment_id}/download", cookies=cookies)
        print("GET /attachments/{id}/download (Replaced) Content Length:", len(check_download.content))
        print("GET /attachments/{id}/download (Replaced) Content:", check_download.content)
        print("-" * 50)

        # 9. DELETE /attachments/{id}
        del_res = await client.delete(f"{base_url}/attachments/{attachment_id}", cookies=cookies)
        print("DELETE /attachments/{id} Status:", del_res.status_code)
        
        # Verify deleted
        after_del_res = await client.get(f"{base_url}/attachments/{attachment_id}", cookies=cookies)
        print("GET /attachments/{id} (after delete) Status:", after_del_res.status_code)
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())
