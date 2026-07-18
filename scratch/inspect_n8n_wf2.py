import sqlite3
import json

def main():
    conn = sqlite3.connect(r"C:\Users\golu\.n8n\database.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT nodes FROM workflow_entity WHERE name = 'FreightForce AI - Workflow 2 - Engagement Engine';")
    row = cursor.fetchone()
    if row:
        nodes = json.loads(row[0])
        print("Nodes in Workflow 2:")
        for node in nodes:
            print(f"- Name: {node.get('name')} | Type: {node.get('type')}")
            # If it's a Postgres node, show query
            if 'postgres' in node.get('type', '').lower():
                print("  Postgres Params:", json.dumps(node.get('parameters', {}), indent=2))
    else:
        print("Workflow not found.")

if __name__ == "__main__":
    main()
