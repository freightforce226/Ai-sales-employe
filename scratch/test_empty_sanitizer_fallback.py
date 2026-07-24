import asyncio
import sys
from unittest.mock import AsyncMock

sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')
from app.services.ai_reply_service import AIReplyService
from app.db.session import AsyncSessionLocal

async def test_empty_sanitizer_fallback():
    async with AsyncSessionLocal() as session:
        service = AIReplyService(session)
        
        # Mock LLMService.generate_text to return the bad signature-only output
        service.llm.generate_text = AsyncMock(return_value="Regards,\nAI Sales Agent")
        
        res = await service.generate_reply_draft(
            org_id="d519ac7f-9c38-46c6-a981-0426cf6e561b",
            customer_id="c58a9ee7-efd6-43a6-96f8-d3551fa2d974",
            thread_id="test_empty_thread_123",
            customer_reply_text="Hello"
        )
        
        # Assert LLM was called exactly twice (initial attempt + retry attempt)
        print(f"LLM Call count: {service.llm.generate_text.call_count}")
        assert service.llm.generate_text.call_count == 2, f"Expected exactly 2 LLM calls, found {service.llm.generate_text.call_count}!"
        
        # Assert that reply_body contains the fallback message narrative (excluding signature)
        print(f"Reply Body:\n{res.reply_body}")
        
        # The fallback reply text from LLM service contains:
        # "Our logistics team is currently reviewing your shipment details"
        assert "Our logistics team is currently reviewing your shipment details" in res.reply_body, \
            "Fallback reply text was not returned!"
            
        print("\nSUCCESS: Empty/short sanitizer fallback integration test passed successfully!")

if __name__ == "__main__":
    asyncio.run(test_empty_sanitizer_fallback())
