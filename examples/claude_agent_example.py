#!/usr/bin/env python3
"""Example: Using ContextGraph with Claude Agent SDK.

This shows how to integrate ContextGraph hooks with the Claude Agent SDK
to automatically capture DecisionRecords.
"""

# from claude_agent_sdk import Agent, AgentConfig
# from contextgraph import ContextGraphClient, Config
# from contextgraph.integrations.claude_agent import contextgraph_hooks

# Example usage (uncomment when using with real Claude Agent SDK):

"""
# Configure ContextGraph
config = Config(
    server_url="http://localhost:8080",
    write_tools=["Bash", "Write", "Edit"],  # Claude Code tool names
    read_tools=["Read", "Glob", "Grep"],
)

client = ContextGraphClient(config)

# Define optional policy checks
def no_destructive_commands(tool_name: str, tool_input: dict, context) -> dict:
    \"\"\"Block destructive bash commands.\"\"\"
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if "rm -rf" in cmd or "DROP TABLE" in cmd:
            return {"passed": False, "message": "Destructive command blocked"}
    return {"passed": True}

# Create hooks preset
hooks = contextgraph_hooks(
    client=client,
    config=config,
    policies={"no_destructive": no_destructive_commands},
)

# Configure agent with hooks
agent = Agent(config=AgentConfig(
    model="claude-sonnet-4-5-20250929",
    hooks=hooks,
))

# Run the agent - ContextGraph hooks capture the decision trace!
# PreToolUse: captures intent + runs policies
# PostToolUse: captures evidence/actions
# Stop: finalizes and sends DecisionRecord

result = agent.run("Create a file with today's date")

# The hooks have now:
# 1. Checked policies before each tool use
# 2. Captured Read/Glob as evidence
# 3. Captured Write/Edit as actions
# 4. Created a DecisionRecord on stop
"""

print("""
Claude Agent SDK Integration Example
=====================================

To use ContextGraph with Claude Agent SDK:

1. Install dependencies:
   pip install claude-agent-sdk contextgraph

2. Create hooks and configure agent:

   from claude_agent_sdk import Agent, AgentConfig
   from contextgraph import ContextGraphClient, Config
   from contextgraph.integrations.claude_agent import contextgraph_hooks

   config = Config(
       server_url="http://localhost:8080",
       write_tools=["Bash", "Write", "Edit"],
   )

   hooks = contextgraph_hooks(client=ContextGraphClient(config))

   agent = Agent(config=AgentConfig(
       model="claude-sonnet-4-5-20250929",
       hooks=hooks,
   ))

3. Run your agent normally - hooks capture decisions automatically!

4. Query the explain endpoint:
   curl http://localhost:8080/v1/decisions/{decision_id}/explain
""")
