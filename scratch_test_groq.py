import os
from langchain_groq import ChatGroq
from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

print(f"Testing Groq API key: {GROQ_API_KEY[:8]}...")
print(f"Testing Model: {GROQ_MODEL}")

try:
    llm = ChatGroq(
        model=GROQ_MODEL,
        temperature=0.5,
        api_key=GROQ_API_KEY
    )
    res = llm.invoke("Hi! Are you there?")
    print("Success! Response:")
    print(res.content)
except Exception as e:
    print("Error calling Groq API:")
    import traceback
    traceback.print_exc()
