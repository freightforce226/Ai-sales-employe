import sqlite3
import json

def main():
    conn = sqlite3.connect(r"C:\Users\golu\.n8n\database.sqlite")
    cursor = conn.cursor()
    
    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    print("Tables in n8n sqlite:", [r[0] for r in cursor.fetchall()])
    
    # Query workflows
    cursor.execute("SELECT id, name, active FROM workflow_entity;")
    workflows = cursor.fetchall()
    print("Workflows:")
    for w in workflows:
        print(f"ID: {w[0]}, Name: {w[1]}, Active: {w[2]}")
        
    # Search nodes for 'Sanjay'
    cursor.execute("SELECT id, name, nodes FROM workflow_entity;")
    for row in cursor.fetchall():
        w_id, w_name, nodes_json = row
        if 'Sanjay' in nodes_json or 'Customer Relationship Manager' in nodes_json or 'CRM' in nodes_json:
            print(f"Match found in workflow: {w_name} (ID: {w_id})")
            nodes = json.loads(nodes_json)
            for node in nodes:
                node_str = json.dumps(node)
                if 'Sanjay' in node_str or 'Customer' in node_str:
                    print(f"  Node: {node.get('name')} | Type: {node.get('type')}")
                    # Print interesting parts
                    if 'parameters' in node:
                        print("  Params:", json.dumps(node['parameters'], indent=2))

if __name__ == "__main__":
    main()
