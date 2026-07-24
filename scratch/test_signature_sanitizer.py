import sys
from dotenv import load_dotenv

load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from app.services.ai_reply_service import AIReplyService

def test():
    service = AIReplyService(None)
    
    test_cases = [
        (
            "Hello,\nWe will verify this.\n\nBest Regards,\nAI Sales Agent",
            "Hello,\nWe will verify this."
        ),
        (
            "Hi there,\nLet us coordinate shipping next week.\n\nThanks,\nJohn Doe\nFreightForce LLC",
            "Hi there,\nLet us coordinate shipping next week."
        ),
        (
            "Hi,\nThanks for your response. We will coordinate route optimization.\n\nSincerely,\nAI Agent",
            "Hi,\nThanks for your response. We will coordinate route optimization."
        ),
        (
            "Hello customer,\nNo signature here.",
            "Hello customer,\nNo signature here."
        )
    ]
    
    print("Testing sanitize_llm_reply...")
    for orig, expected in test_cases:
        res = service.sanitize_llm_reply(orig)
        print("\n--- ORIGINAL ---")
        print(repr(orig))
        print("--- SANITIZED ---")
        print(repr(res))
        print("--- MATCHED EXPECTATION? ---", res == expected)
        assert res == expected

if __name__ == "__main__":
    test()
