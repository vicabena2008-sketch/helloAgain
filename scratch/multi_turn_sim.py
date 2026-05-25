import sys
import os

# ensure project root is on sys.path so imports work when executed from scratch/
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from chat import chat
from conversation import ConversationState


def run_sim():
    state = ConversationState()

    turns = [
        "Phone under NGN 150,000",
        "any other alternative phone aside the infinix",
        "can pay 70, 000 NGN to get it?",
    ]

    for i, u in enumerate(turns, start=1):
        print(f"\n--- Turn {i} USER: {u}")
        resp = chat(u, state)
        print(f"ASSISTANT: {resp}\n")
        print(f"State summary: active_brand={state.active_brand}, active_product={state.active_product}, budget={state.budget_mentioned}\n")


if __name__ == '__main__':
    run_sim()
