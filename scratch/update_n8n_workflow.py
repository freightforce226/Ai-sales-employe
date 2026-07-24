import sqlite3
import json

def main():
    db_path = r"C:\Users\golu\.n8n\database.sqlite"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Fetch current nodes for reply-detection
    cursor.execute("SELECT id, name, nodes FROM workflow_entity WHERE name = 'reply-detection';")
    row = cursor.fetchone()
    if not row:
        print("Workflow 'reply-detection' not found!")
        return
        
    wf_id, wf_name, nodes_json = row
    nodes = json.loads(nodes_json)
    
    updated = False
    for node in nodes:
        if node.get('name') == 'email-payload':
            print("Found email-payload node. Current JS Code:")
            print(node['parameters'].get('jsCode'))
            
            # Update the JS Code to send html_body, plain_text_body, and empty attachments array
            new_code = (
                "return [{\n"
                "  json: {\n"
                "    organization_id: $json.organization_id,\n"
                "    customer_email: $json.customer_email,\n"
                "    mailbox_email: $json.mailbox_email,\n"
                "    subject: $json.subject,\n"
                "    html_body: $json.reply_body,\n"
                "    plain_text_body: $json.reply_body,\n"
                "    thread_id: $json.thread_id,\n"
                "    references: $json.internet_message_id,\n"
                "    conversation_id: $json.conversation_id,\n"
                "    cc: $json.default_cc,\n"
                "    attachments: []\n"
                "  }\n"
                "}]"
            )
            node['parameters']['jsCode'] = new_code
            updated = True
            print("\nUpdated JS Code to:")
            print(new_code)
            
    if updated:
        new_nodes_json = json.dumps(nodes)
        cursor.execute("UPDATE workflow_entity SET nodes = ? WHERE id = ?;", (new_nodes_json, wf_id))
        conn.commit()
        print("\nSuccessfully updated workflow in SQLite database!")
    else:
        print("Node 'email-payload' not found in workflow nodes.")
        
    conn.close()

if __name__ == "__main__":
    main()
