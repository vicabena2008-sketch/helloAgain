from chat import chat as ai_chat
from conversation import ConversationState

state = ConversationState()
state.history.append(('Hello', 'Hi'))
print(ai_chat('okay', state))
