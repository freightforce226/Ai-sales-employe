import requests
import json

url = "http://localhost:8000/api/v1/email/send"
headers = {
    "X-API-Key": "freightforce-dev-123",
    "Content-Type": "application/json"
}

payload = {
    "organization_id": "d519ac7f-9c38-46c6-a981-0426cf6e561b",
    "customer_email": "dev@freightforce.ai",
    "mailbox_email": "gouravshamraa@outlook.com",
    "subject": "Re: Test AI Reply Payload",
    "thread_id": "thread_123",
    "references": "msg_123",
    "conversation_id": "conv_123",
    "cc": [],
    "email_type": "ai_reply"
}

print("Sending payload...")
try:
    response = requests.post(url, headers=headers, json=payload)
    print("Status Code:", response.status_code)
    try:
        print("Response Body:", json.dumps(response.json(), indent=2))
    except Exception:
        print("Response Text:", response.text)
except Exception as e:
    print("Error sending request:", str(e))
