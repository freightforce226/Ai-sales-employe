import sqlite3

conn = sqlite3.connect(r"C:\Users\golu\.n8n\database.sqlite")
cursor = conn.cursor()
cursor.execute("SELECT id, name, active FROM workflow_entity;")
for r in cursor.fetchall():
    print(f"ID: {r[0]} | Name: {r[1]} | Active: {r[2]}")
conn.close()
