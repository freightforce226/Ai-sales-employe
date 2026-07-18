import sqlite3
import json

def main():
    conn = sqlite3.connect(r"C:\Users\golu\.n8n\database.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT nodes FROM workflow_entity WHERE name = 'FreightForce AI - Workflow 2 - Engagement Engine';")
    row = cursor.fetchone()
    if row:
        nodes = json.loads(row[0])
        for node in nodes:
            if node.get('name') == 'Build Gemini Prompt':
                print("NODE TYPE:", node.get('type'))
                print("NODE PARAMS:")
                print(json.dumps(node.get('parameters', {}), indent=2))
    else:
        print("Workflow not found.")

if __name__ == "__main__":
    main()
