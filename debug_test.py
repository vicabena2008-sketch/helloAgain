import sqlite3
import json
import os

DB_PATH = "helloagain.db"

def check_db():
    if not os.path.exists(DB_PATH):
        print("DB does not exist locally")
        return
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT id, session_id, tag, status FROM customers").fetchall()
    for row in rows:
        print(dict(row))

def test_llm():
    try:
        from llm import llm
        from langchain_core.messages import HumanMessage
        print("Testing LLM...")
        resp = llm.invoke([HumanMessage(content="Hello")])
        print("Resp:", resp.content)
    except Exception as e:
        print("LLM Error:", type(e), e)

if __name__ == "__main__":
    check_db()
    test_llm()
