import json
import os

transcript_path = r"C:\Users\golu\.gemini\antigravity-ide\brain\e716ce4f-dc04-4fbd-9715-e3cecb091e69\.system_generated\logs\transcript_full.jsonl"
if not os.path.exists(transcript_path):
    transcript_path = r"C:\Users\golu\.gemini\antigravity-ide\brain\e716ce4f-dc04-4fbd-9715-e3cecb091e69\.system_generated\logs\transcript.jsonl"

def find_all_versions():
    with open(transcript_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                if "tool_calls" in data:
                    for tc in data["tool_calls"]:
                        name = tc.get("name")
                        args = tc.get("args", {})
                        target = args.get("TargetFile") or args.get("AbsolutePath") or ""
                        if "ai_reply_service.py" in target and name in ["write_to_file", "replace_file_content", "multi_replace_file_content"]:
                            content = args.get("CodeContent", "") or args.get("ReplacementContent", "") or ""
                            if "get_pending_replies" in content:
                                print("=" * 80)
                                print(f"Step {data.get('step_index')}: Tool {name} -> {target}")
                                start_idx = content.find("async def get_pending_replies")
                                if start_idx != -1:
                                    end_idx = content.find("async def complete_reply", start_idx)
                                    if end_idx == -1:
                                        end_idx = start_idx + 1000
                                    print(content[start_idx:end_idx])
                                else:
                                    print("Snippet contains get_pending_replies but not the full definition definition.")
            except Exception as e:
                pass

if __name__ == "__main__":
    find_all_versions()
