import sqlite3
import json

def main():
    conn = sqlite3.connect(r"C:\Users\golu\.n8n\database.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT nodes FROM workflow_entity WHERE name = 'reply-detection';")
    row = cursor.fetchone()
    if row:
        nodes = json.loads(row[0])
        for node in nodes:
            if node.get('name') == 'record_ai_reply':
                print(json.dumps(node, indent=2))
    else:
        print("Workflow 'reply-detection' not found.")
    conn.close()

if __name__ == "__main__":
    main()
