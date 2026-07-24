import sys
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from app.main import app
from app.core.config import get_settings

def main():
    settings = get_settings()
    api_key = settings.n8n_service_api_key
    print(f"Using API Key: {api_key}")
    
    client = TestClient(app)
    headers = {"X-API-Key": api_key}
    
    response = client.get("/api/v1/ai-reply/pending", headers=headers)
    print("Response Status Code:", response.status_code)
    print("Response JSON Content:")
    print(response.json())

if __name__ == "__main__":
    main()
