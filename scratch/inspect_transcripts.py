import json
import os

transcript_path = r"C:\Users\golu\.gemini\antigravity-ide\brain\e716ce4f-dc04-4fbd-9715-e3cecb091e69\.system_generated\logs\transcript_full.jsonl"
if not os.path.exists(transcript_path):
    transcript_path = r"C:\Users\golu\.gemini\antigravity-ide\brain\e716ce4f-dc04-4fbd-9715-e3cecb091e69\.system_generated\logs\transcript.jsonl"

def find_initial_write():
    with open(transcript_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                if "tool_calls" in data:
                    for tc in data["tool_calls"]:
                        name = tc.get("name")
                        args = tc.get("args", {})
                        target = args.get("TargetFile") or args.get("AbsolutePath") or ""
                        if "ai_reply_service.py" in target:
                            # Let's print step 3391 chunk or any initial write
                            step = data.get('step_index')
                            if name in ["write_to_file", "multi_replace_file_content", "replace_file_content"] and step < 3395:
                                print("=" * 80)
                                print(f"Step {step}: Tool {name} -> {target}")
                                print("Arguments:")
                                print(json.dumps(args, indent=2))
            except Exception as e:
                pass

if __name__ == "__main__":
    find_initial_write()
