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
            # Let's see if the node type is an OpenAI or LLM node
            node_type = node.get('type', '')
            if 'openai' in node_type.lower() or 'llm' in node_type.lower() or 'chat' in node_type.lower() or 'anthropic' in node_type.lower():
                print(f"Workflow: {w_name} | Node: {node.get('name')} | Type: {node_type}")
                print("  Params:", json.dumps(node.get('parameters', {}), indent=2))

if __name__ == "__main__":
    main()
