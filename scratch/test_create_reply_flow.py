import requests
import json
import sqlite3

def main():
    url = "http://localhost:8000/api/v1/email/send"
    headers = {
        "X-API-Key": "freightforce-dev-123",
        "Content-Type": "application/json"
    }

    # Fetch a valid organization and customer from n8n database to run integration test
    conn = sqlite3.connect(r"C:\Users\golu\.n8n\database.sqlite")
    cursor = conn.cursor()
    
    # 1. Test Scenario 2 (New Conversation / fallback)
    payload_new = {
        "organization_id": "d519ac7f-9c38-46c6-a981-0426cf6e561b",
        "customer_email": "dev@freightforce.ai",
        "subject": "Integration Test - Scenario 2 Standard Outbound",
        "html_body": "<p>This is a standard outbound test message.</p>",
        "attachments": []
    }
    
    print("\n--- Testing Scenario 2 (Standard sendMail) ---")
    res_new = requests.post(url, headers=headers, json=payload_new)
    print("Status Code:", res_new.status_code)
    print("Response:", res_new.json())

    # 2. Test Scenario 1 (Threaded Reply with parent_message_id)
    # We will use the Hitachi parent Graph message ID if available
    payload_reply = {
        "organization_id": "d519ac7f-9c38-46c6-a981-0426cf6e561b",
        "customer_email": "dev@freightforce.ai",
        "subject": "Re: Following Up - Hitachi",
        "html_body": "<p>This is a threaded reply test acknowledgement.</p>",
        "parent_message_id": "AQMkADAwATNiZmYAZS1hZjRiLTVjMDItMDACLTAwCgBGAAADvPkW3AHC8Eul5yg1iSsQogcA1Woe4kkRVkCJrHuz0FRo8wAAAgEMAAAA1Woe4kkRVkCJrHuz0FRo8wAAAEAJKPQAAAA=",
        "attachments": []
    }
    
    print("\n--- Testing Scenario 1 (Threaded createReply) ---")
    res_reply = requests.post(url, headers=headers, json=payload_reply)
    print("Status Code:", res_reply.status_code)
    print("Response:", res_reply.json())

if __name__ == "__main__":
    main()
