from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from typing_extensions import NotRequired
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

import sqlite3
import requests
import asyncio

load_dotenv()

# -------------------
# 1. LLM
# -------------------
llm = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0.7
  )

client = MultiServerMCPClient(
    {
      "my-fastmcp-server": {
      "transport": "stdio",
      "command": "C:\\Users\\gupta\\mcp_server\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\gupta\\mcp_server\\demo_server\\server.py"
      ]
    }
    }
)

# -------------------
# 2. Tools
# -------------------
# Tools
# search_tool = DuckDuckGoSearchRun(region="us-en")

@tool
def calculator(first_num: float, second_num: float, operation: str) -> dict:
    """
    Perform a basic arithmetic operation on two numbers.
    Supported operations: add, sub, mul, div
    """
    try:
        if operation == "add":
            result = first_num + second_num
        elif operation == "sub":
            result = first_num - second_num
        elif operation == "mul":
            result = first_num * second_num
        elif operation == "div":
            if second_num == 0:
                return {"error": "Division by zero is not allowed"}
            result = first_num / second_num
        else:
            return {"error": f"Unsupported operation '{operation}'"}
        
        return {"first_num": first_num, "second_num": second_num, "operation": operation, "result": result}
    except Exception as e:
        return {"error": str(e)}

# tools = [calculator]
# llm_with_tools = llm.bind_tools(tools)

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    title: NotRequired[str]

async def build_graph():

    tools = await client.get_tools()
    print(tools)
    llm_with_tools = llm.bind_tools(tools)
    # nodes
    async def chat_node(state: ChatState):

        messages = state["messages"]
        response = await llm_with_tools.ainvoke(messages)
        return {'messages': [response]}

    tool_node = ToolNode(tools)

    # defining graph and nodes
    graph = StateGraph(ChatState)

    graph.add_node("chat_node", chat_node)
    graph.add_node("tools", tool_node)

    # defining graph connections
    graph.add_edge(START, "chat_node")
    graph.add_conditional_edges("chat_node", tools_condition)
    graph.add_edge("tools", "chat_node")

    chatbot = graph.compile()

    return chatbot

async def main():

    chatbot = await build_graph()

    # running the graph
    result = await chatbot.ainvoke({"messages": [HumanMessage(content="Roll a dice 3 times using my mcp server")]})

    print(result['messages'][-1].content)

if __name__ == '__main__':
    asyncio.run(main())