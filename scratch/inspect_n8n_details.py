import sqlite3
import json

def main():
    conn = sqlite3.connect(r"C:\Users\golu\.n8n\database.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, nodes FROM workflow_entity;")
    for row in cursor.fetchall():
        w_id, w_name, nodes_json = row
        nodes = json.loads(nodes_json)
        for node in nodes:
            node_str = json.dumps(node)
            if 'Sanjay' in node_str or 'prompt' in node_str or 'prompt' in node_str.lower() or 'openai' in node_str.lower() or 'claude' in node_str.lower() or 'model' in node_str.lower():
                print(f"Workflow: {w_name} | Node: {node.get('name')} | Type: {node.get('type')}")
                print("  Params:", json.dumps(node.get('parameters', {}), indent=2))

if __name__ == "__main__":
    main()
