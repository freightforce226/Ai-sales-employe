import json
import os

transcript_path = r"C:\Users\golu\.gemini\antigravity-ide\brain\e716ce4f-dc04-4fbd-9715-e3cecb091e69\.system_generated\logs\transcript_full.jsonl"
if not os.path.exists(transcript_path):
    transcript_path = r"C:\Users\golu\.gemini\antigravity-ide\brain\e716ce4f-dc04-4fbd-9715-e3cecb091e69\.system_generated\logs\transcript.jsonl"

def find_sql_versions():
    with open(transcript_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                step = data.get('step_index')
                if step in [2844, 2937, 3391]:
                    if "tool_calls" in data:
                        for tc in data["tool_calls"]:
                            args = tc.get("args", {})
                            content = args.get("CodeContent", "") or args.get("ReplacementContent", "") or ""
                            if "SELECT" in content and "FROM email_log" in content:
                                print("=" * 80)
                                print(f"VERSION AT STEP {step}:")
                                start_idx = content.find("SELECT")
                                end_idx = content.find("ORDER BY", start_idx)
                                if end_idx == -1:
                                    end_idx = start_idx + 1500
                                else:
                                    end_idx += 100
                                print(content[start_idx:end_idx])
            except Exception as e:
                pass

if __name__ == "__main__":
    find_sql_versions()
