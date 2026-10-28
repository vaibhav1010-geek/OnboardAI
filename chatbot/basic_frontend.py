import streamlit as st
from langgraph_backend import chatbot
from langchain_core.messages import HumanMessage

# st.session_state -> dict -> 
CONFIG = {'configurable': {'thread_id': 'thread-1'}}
# agar yeh nahi karenge toh bas to chat boz banenge human and ai aur usi pe content overwrite hota rahega
if 'message_history' not in st.session_state:
    st.session_state['message_history'] = []

# loading the conversation history
for message in st.session_state['message_history']:
    with st.chat_message(message['role']):
        st.text(message['content'])

#{'role': 'user', 'content': 'Hi'}
#{'role': 'assistant', 'content': 'Hi=ello'}

user_input = st.chat_input('Type here')

if user_input:

    # first add the message to message_history
    st.session_state['message_history'].append({'role': 'user', 'content': user_input})
    with st.chat_message('user'):
        st.text(user_input)

    response = chatbot.invoke({'messages': [HumanMessage(content=user_input)]}, config=CONFIG)
    
    ai_message = response['messages'][-1].content
    # first add the message to message_history
    st.session_state['message_history'].append({'role': 'assistant', 'content': ai_message})
    with st.chat_message('assistant'):
        st.text(ai_message)

# st.session_state is a dictionary which is used to store message history in frontend
# it's format looks like this for eg : {'message_history' : ['role' : 'user' , 'content' : 'hi']} , if we
# manually use a normal dictionary it will get erased as soon as we press enter , but
# st.session_state resets upon refreshing the page
# streamlit is built in suh a manner that whenever we interact with our app for ex give an input and press 
# enter the entire file re runs st.session_state survives that re run and keeps previous memory safe

