"""Configuration for ContextGraph client."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """Configuration for ContextGraph client."""

    # Server settings
    server_url: str = "http://localhost:8080"
    api_key: Optional[str] = None
    tenant_id: str = "default"

    # Tool classification
    write_tools: list[str] = field(default_factory=list)
    read_tools: list[str] = field(default_factory=list)

    # Batching
    batch_size: int = 100
    flush_interval_seconds: float = 5.0

    # Network
    timeout: float = 30.0
    raise_on_error: bool = False

    # Storage (for local mode)
    postgres_url: Optional[str] = None
    local_mode: bool = False

    def is_write_tool(self, tool_name: str) -> bool:
        if tool_name in self.write_tools:
            return True
        if tool_name in self.read_tools:
            return False
        # Heuristics for common patterns
        write_patterns = ["create", "update", "delete", "send", "post", "put", "patch", "write", "set", "add", "remove"]
        tool_lower = tool_name.lower()
        return any(p in tool_lower for p in write_patterns)

    def is_read_tool(self, tool_name: str) -> bool:
        return not self.is_write_tool(tool_name)
