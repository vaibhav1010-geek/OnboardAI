from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver


load_dotenv()

llm = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0.7
  )

class ChatState(TypedDict):
  messages : Annotated[list[BaseMessage] , add_messages]

def chat_node(state:ChatState):
  messages = state['messages']
  response = llm.invoke(messages)

  return {'messages' : [response]}

checkpointer = MemorySaver()
graph = StateGraph(ChatState)

graph.add_node('chat_node' , chat_node)

graph.add_edge(START, 'chat_node')
graph.add_edge('chat_node', END)

chatbot = graph.compile(checkpointer=checkpointer)

initial_state = {
  'messages' : [HumanMessage(content='What is capital of India')]
}

# print(chatbot.invoke(initial_state)['messages'][-1].content)
thread_id = '1'
while True:

  user_message = input('Enter your message : ')
  print(user_message)
  if user_message.strip().lower() in ['exit' , 'quit' , 'bye']:
    break
  config = {'configurable' : {'thread_id' : 'thread_id'}}
  response = chatbot.invoke({'messages' : [HumanMessage(content=user_message)]}  , config=config)
  print('AI:' , response['messages'][-1].content)

# we use in memory saver which is application of persistence to maintain the state to allow the llm
# to answer follow up questions with previous context . each time we call invoke the current state
# erased to avoid that we use checkpointers and config. But memorysaver saves state in ram , hence 
# whenever we refresh state gets erased this is solved in the backend file.

# checpointer creates a checkpointer before execution of every node or every super set node(when nodes are in parallel),
# which helps us to maintain state history according to each node execution . thread id helps us to refer to a particular,
# llm call and stores state history for it .
# to get final state history : chatbot.get_state(config) 
# to get intermediate state history : chatbot.get_state_history(config)
# state stores everything for eg ai message , human message , thread id for a particular conversation