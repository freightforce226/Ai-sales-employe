import sqlite3
import json

def main():
    conn = sqlite3.connect(r"C:\Users\golu\.n8n\database.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT name, nodes FROM workflow_entity WHERE name LIKE '%Ai-reply-engine%' OR name LIKE '%reply-detection%';")
    rows = cursor.fetchall()
    print(f"Found {len(rows)} matching workflows:")
    for name, nodes_json in rows:
        print(f"\n--- WORKFLOW: {name} ---")
        nodes = json.loads(nodes_json)
        for node in nodes:
            # Check for HTTP Request or postgres nodes
            n_type = node.get('type')
            n_name = node.get('name')
            print(f"Node: {n_name} | Type: {n_type}")
            if 'http' in n_type.lower() or 'code' in n_type.lower():
                print("Parameters:", json.dumps(node.get('parameters', {}), indent=2))

if __name__ == "__main__":
    main()
