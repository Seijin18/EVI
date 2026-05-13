# /home/marshibs/Projects/EVI/agent/graph.py
import operator
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage
from datetime import datetime, timedelta


class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    task_type: str
    iterations: int
    final_answer: str


llm = ChatOllama(
    model="qwen2.5:7b-instruct-q4_K_M",
    base_url="http://host.docker.internal:11434",
    temperature=0.1,
    num_ctx=2048,  # Reduced from 4096 to save VRAM on the 6GB GTX 1060
    num_gpu=10,  # Halved to 10 to heavily reduce VRAM footprint and prevent CUDA OOM
)

SYSTEM_PROMPT = """You are EVI, a precise and helpful personal AI assistant.

{calendar_context}
CRITICAL RULES:
1. When the user asks to schedule an event for a relative day ("tomorrow", "next week"), you MUST find the exact date in the CALENDAR LOOKUP TABLE above and use it.
2. If asked what the current date or time is, answer EXACTLY with the "Today is..." line above. DO NOT hallucinate dates.
3. You have native access to tools. Call the appropriate tool when needed.

Available tools: {tool_names}"""

from tools.file_organizer import organize_inbox
from tools.rag_tool import ingest_university_pdf, query_university_notes
from tools.calendar_tool import schedule_event

# Initialize tool registry
tools = [organize_inbox, ingest_university_pdf, query_university_notes, schedule_event]


def agent_node(state: AgentState) -> dict:
    """Core reasoning node — decides next action."""
    if state["iterations"] > 10:
        return {
            "final_answer": "Max iterations reached.",
            "messages": [],
            "iterations": state["iterations"] + 1,
        }

    llm_with_tools = llm.bind_tools(tools)

    now = datetime.now()
    calendar_text = f"Today is {now.strftime('%A, %Y-%m-%d')}. Current time: {now.strftime('%H:%M:%S')}\n"
    calendar_text += "CALENDAR LOOKUP TABLE:\n"
    for i in range(1, 15):
        day = now + timedelta(days=i)
        desc = "Tomorrow" if i == 1 else "Next Week" if i >= 7 else "This Week"
        calendar_text += f"- +{i} days ({desc}): {day.strftime('%A')} -> {day.strftime('%Y-%m-%d')}\n"

    system_message = SystemMessage(
        content=SYSTEM_PROMPT.format(
            calendar_context=calendar_text, tool_names=[t.name for t in tools]
        )
    )

    response = llm_with_tools.invoke([system_message] + state["messages"])

    return {"messages": [response], "iterations": state["iterations"] + 1}


def should_continue(state: AgentState) -> str:
    """Router: tool call → tools node, else → end."""
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"
    return END


def build_agent_graph(tool_list: list):
    global tools
    tools = tool_list

    tool_node = ToolNode(tools)
    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")

    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()
