import os
from dotenv import load_dotenv
load_dotenv()

from chat import chat
from conversation import ConversationState

state = ConversationState()
print("Testing chat function...")
try:
    reply = chat("I want to buy a laptop", state)
    print("Reply 1:", reply)
    reply2 = chat("how much?", state)
    print("Reply 2:", reply2)
except Exception as e:
    import traceback
    traceback.print_exc()
