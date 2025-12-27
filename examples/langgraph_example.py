#!/usr/bin/env python3
"""Example: Using ContextGraph with LangGraph.

This shows how to integrate the ContextGraph checkpointer wrapper
with LangGraph to automatically capture DecisionRecords from checkpoints.
"""

# from langgraph.graph import StateGraph, START, END
# from langgraph.checkpoint.memory import MemorySaver
# from contextgraph import ContextGraphClient, Config
# from contextgraph.integrations.langgraph import ContextGraphCheckpointer

# Example usage (uncomment when using with real LangGraph):

"""
from typing import TypedDict, Annotated
from operator import add

# Define state
class State(TypedDict):
    messages: Annotated[list, add]
    account_data: dict
    approved: bool

# Configure ContextGraph
config = Config(
    server_url="http://localhost:8080",
    write_tools=["send_email", "update_crm"],
)

client = ContextGraphClient(config)

# Wrap the checkpointer
base_saver = MemorySaver()
cg_checkpointer = ContextGraphCheckpointer(
    underlying=base_saver,
    client=client,
    config=config,
    state_keys_as_evidence=["account_data"],  # Capture these state keys as evidence
    action_node_names=["send_email_node"],     # These nodes are actions
)

# Build graph
def gather_data(state: State) -> dict:
    # This becomes evidence (read operation)
    return {"account_data": {"id": "ACC-100", "arr": 500000}}

def review_node(state: State) -> dict:
    return {"approved": True}

def send_email_node(state: State) -> dict:
    # This becomes an action (write operation)
    return {"messages": ["Email sent to account"]}

builder = StateGraph(State)
builder.add_node("gather", gather_data)
builder.add_node("review", review_node)
builder.add_node("send_email_node", send_email_node)

builder.add_edge(START, "gather")
builder.add_edge("gather", "review")
builder.add_edge("review", "send_email_node")
builder.add_edge("send_email_node", END)

# Compile with interrupt for human-in-the-loop
graph = builder.compile(
    checkpointer=cg_checkpointer,
    interrupt_before=["send_email_node"],  # Pause for approval
)

# Run until interrupt
config = {"configurable": {"thread_id": "user-123"}}
result = graph.invoke({"messages": []}, config)

# Human approves
cg_checkpointer.on_resume(config, approver_id="manager@company.com", resume_value="approved")
result = graph.invoke(None, config)

# Finalize and emit DecisionRecord
record = cg_checkpointer.finalize_thread(config, success=True)
print(f"Created DecisionRecord: {record.decision_id}")
"""

print("""
LangGraph Integration Example
=============================

To use ContextGraph with LangGraph:

1. Install dependencies:
   pip install langgraph contextgraph

2. Wrap your checkpointer:

   from langgraph.checkpoint.memory import MemorySaver
   from contextgraph import ContextGraphClient, Config
   from contextgraph.integrations.langgraph import ContextGraphCheckpointer

   config = Config(
       server_url="http://localhost:8080",
       write_tools=["send_email", "update_crm"],
   )

   base_saver = MemorySaver()
   cg_checkpointer = ContextGraphCheckpointer(
       underlying=base_saver,
       client=ContextGraphClient(config),
       state_keys_as_evidence=["account_data"],
       action_node_names=["send_node"],
   )

3. Use with your graph:

   graph = builder.compile(checkpointer=cg_checkpointer)

4. For human-in-the-loop, call:

   cg_checkpointer.on_interrupt(config, interrupt_value)
   cg_checkpointer.on_resume(config, approver_id, resume_value)

5. Finalize when done:

   record = cg_checkpointer.finalize_thread(config)

6. Query the explain endpoint:
   curl http://localhost:8080/v1/decisions/{decision_id}/explain
""")
