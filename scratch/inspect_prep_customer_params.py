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
            if node.get('name') == 'Prep Customer Params':
                print("JS CODE:")
                print(node.get('parameters', {}).get('jsCode'))
    else:
        print("Workflow not found.")

if __name__ == "__main__":
    main()
