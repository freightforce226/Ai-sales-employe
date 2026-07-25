import asyncio
import sys

sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')
from app.db.session import AsyncSessionLocal
from app.services.ai_reply_service import AIReplyService

async def test_service():
    async with AsyncSessionLocal() as session:
        service = AIReplyService(session)
        org_id = "d519ac7f-9c38-46c6-a981-0426cf6e561b"
        
        print("Testing get_operations_dashboard...")
        kpis = await service.get_operations_dashboard(org_id)
        print("KPIs:", kpis)
        
        print("\nTesting get_operations_list...")
        items = await service.get_operations_list(org_id)
        print("Found items:", len(items))
        if items:
            sample = items[0]
            print("Sample item:", sample)
            
            print(f"\nTesting get_operations_detail for id: {sample['reply_id']}...")
            detail = await service.get_operations_detail(org_id, sample["reply_id"])
            print("Detail customer name:", detail["customer_name"])
            print("Detail recipients:", detail["recipients"])
            print("Detail timeline length:", len(detail["timeline"]))
            print("Detail original body starts with:", detail["original_body"][:100] if detail["original_body"] else None)
            print("Detail final sent starts with:", detail["final_sent"][:100] if detail["final_sent"] else None)

if __name__ == "__main__":
    asyncio.run(test_service())
