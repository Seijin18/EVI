# /home/marshibs/Projects/EVI/agent/graph.py
import operator
import os
from datetime import datetime, timedelta
from typing import Annotated, TypedDict

from langchain_core.messages import SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from llm import build_llm
from tools.registry import get_all_tools

llm = build_llm()

SYSTEM_PROMPT = """You are EVI, a precise and helpful personal AI assistant for Marcos (Brazil).

{calendar_context}
CRITICAL RULES:
0. Reply in the same language the user writes. Default: Brazilian Portuguese (pt-BR). Never switch to English unless the user writes in English.
1. Calendar times are local wall clock in EVI_TIMEZONE (default America/Sao_Paulo). Use `2026-06-10T09:00:00` for 9h — never append `Z` unless the user explicitly gives UTC.
2. When the user asks to schedule an event for a relative day ("tomorrow", "next week"), you MUST find the exact date in the CALENDAR LOOKUP TABLE above and use it.
3. If asked what the current date or time is, answer EXACTLY with the "Today is..." line above. DO NOT hallucinate dates.
4. You have native access to tools. Call the appropriate tool when needed.
5. WhatsApp commitments are queued in Postgres. Use list_pending_commitments, list_scheduled_today, then confirm_commitments (ids) to schedule events on Calendar or create Google Tasks, or dismiss_commitments when the user asks to review or skip them. For Google Calendar events already booked, use list_calendar_events.
6. NEVER say an event was scheduled unless you called schedule_event (or confirm_commitments) in THIS turn and the tool returned success. Do not invent calendar links. Paste only the exact Link: URL from the tool result, never markdown [text](url).

Available tools: {tool_names}"""

tools = get_all_tools()


class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    task_type: str
    iterations: int
    final_answer: str


def agent_node(state: AgentState) -> dict:
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
