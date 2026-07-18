import asyncio
import httpx

async def main():
    base_url = "http://localhost:8000/api/v1"
    login_url = f"{base_url}/auth/login"
    
    # 1. Login
    async with httpx.AsyncClient() as client:
        login_res = await client.post(
            login_url,
            json={"email": "dev@freightforce.ai", "password": "123456"}
        )
        print("Login Status:", login_res.status_code)
        if login_res.status_code != 200:
            print("Login failed:", login_res.text)
            return
            
        cookies = login_res.cookies
        
        # 2. Get Industries list
        ind_res = await client.get(f"{base_url}/templates/industries", cookies=cookies)
        print("GET /industries Status:", ind_res.status_code)
        print("GET /industries Payload:", ind_res.json())
        
        # 3. Create Valid Template
        valid_payload = {
            "template_name": "Steel Outreach Template",
            "industry": "Steel",
            "subject": "Shipment assistance for {{company_name}}",
            "body": "<p>Hello {{contact_name}},</p><p>We specialize in {{industry}} logistics.</p><p>Best,<br>{{sender_name}}</p>",
            "status": "active"
        }
        create_res = await client.post(f"{base_url}/templates", json=valid_payload, cookies=cookies)
        print("POST /templates (Valid) Status:", create_res.status_code)
        if create_res.status_code != 201:
            print("Failed body:", create_res.text)
        template = create_res.json() if create_res.status_code == 201 else {}
        print("Created template ID:", template.get("id"))
        print("Created template name:", template.get("name"), "subject:", template.get("subject"))
        print("Created template example_subject:", template.get("example_subject"), "industry_tag:", template.get("industry_tag"))
        print("Created template status:", template.get("status"), "is_active:", template.get("is_active"))
        print("-" * 50)
        
        template_id = template.get("id")
        
        # 4. Create Template with Malformed/Invalid Placeholders
        invalid_payload = {
            "template_name": "Invalid Template",
            "industry": "Steel",
            "subject": "Hello {contact_name}",
            "body": "<p>Hi {{invalid_placeholder}}</p>",
            "status": "draft"
        }
        invalid_res = await client.post(f"{base_url}/templates", json=invalid_payload, cookies=cookies)
        print("POST /templates (Invalid tags) Status:", invalid_res.status_code)
        print("POST /templates (Invalid tags) Response:", invalid_res.text)
        print("-" * 50)
        
        # 5. Create Template with Unsafe HTML (Sanitization)
        unsafe_payload = {
            "template_name": "Unsafe Template",
            "industry": "Chemicals",
            "subject": "Greetings {{contact_name}}",
            "body": "<p>Click <a href='#' onclick='alert(1)'>here</a></p><script>alert('XSS')</script><iframe></iframe>",
            "status": "draft"
        }
        unsafe_res = await client.post(f"{base_url}/templates", json=unsafe_payload, cookies=cookies)
        print("POST /templates (Unsafe HTML) Status:", unsafe_res.status_code)
        unsafe_template = unsafe_res.json()
        print("Sanitized Body:", unsafe_template.get("body"))
        print("-" * 50)
        
        unsafe_id = unsafe_template.get("id")
        
        # 6. Get List of Templates
        list_res = await client.get(f"{base_url}/templates?q=Steel", cookies=cookies)
        print("GET /templates Status:", list_res.status_code)
        print("GET /templates Total:", list_res.json().get("total"))
        print("-" * 50)
        
        # 7. Edit Template
        update_payload = {
            "template_name": "Updated Steel Outreach Template",
            "subject": "Urgent update for {{company_name}}"
        }
        update_res = await client.put(f"{base_url}/templates/{template_id}", json=update_payload, cookies=cookies)
        print("PUT /templates/{id} Status:", update_res.status_code)
        print("Updated name:", update_res.json().get("template_name"))
        print("-" * 50)
        
        # 8. Duplicate Template
        dup_res = await client.post(f"{base_url}/templates/{template_id}/duplicate", cookies=cookies)
        print("POST /templates/{id}/duplicate Status:", dup_res.status_code)
        duplicated = dup_res.json()
        print("Duplicated Name:", duplicated.get("template_name"))
        print("Duplicated Status:", duplicated.get("status"), "is_active:", duplicated.get("is_active"))
        print("-" * 50)
        
        duplicated_id = duplicated.get("id")
        
        # 9. Clean up (Delete created templates)
        for tid in [template_id, unsafe_id, duplicated_id]:
            if tid:
                del_res = await client.delete(f"{base_url}/templates/{tid}", cookies=cookies)
                print(f"DELETE /templates/{tid} Status:", del_res.status_code)

if __name__ == '__main__':
    asyncio.run(main())
