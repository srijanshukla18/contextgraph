"""Tests for the ContextGraph configuration module."""

import pytest
from contextgraph.core.config import Config


class TestConfigDefaults:
    """Tests for Config default values."""

    def test_default_server_url(self):
        """Config has correct default server URL."""
        config = Config()
        assert config.server_url == "http://localhost:8080"

    def test_default_api_key_is_none(self):
        """Config defaults to no API key."""
        config = Config()
        assert config.api_key is None

    def test_default_tenant_id(self):
        """Config has correct default tenant ID."""
        config = Config()
        assert config.tenant_id == "default"

    def test_default_batch_size(self):
        """Config has correct default batch size."""
        config = Config()
        assert config.batch_size == 100

    def test_default_flush_interval(self):
        """Config has correct default flush interval."""
        config = Config()
        assert config.flush_interval_seconds == 5.0

    def test_default_timeout(self):
        """Config has correct default timeout."""
        config = Config()
        assert config.timeout == 30.0

    def test_default_raise_on_error(self):
        """Config defaults to not raising on error."""
        config = Config()
        assert config.raise_on_error is False

    def test_default_local_mode(self):
        """Config defaults to non-local mode."""
        config = Config()
        assert config.local_mode is False

    def test_default_postgres_url_is_none(self):
        """Config defaults to no postgres URL."""
        config = Config()
        assert config.postgres_url is None

    def test_default_write_tools_empty(self):
        """Config defaults to empty write tools list."""
        config = Config()
        assert config.write_tools == []

    def test_default_read_tools_empty(self):
        """Config defaults to empty read tools list."""
        config = Config()
        assert config.read_tools == []


class TestConfigCustomValues:
    """Tests for Config with custom values."""

    def test_custom_server_url(self):
        """Config accepts custom server URL."""
        config = Config(server_url="http://custom:9000")
        assert config.server_url == "http://custom:9000"

    def test_custom_api_key(self):
        """Config accepts custom API key."""
        config = Config(api_key="my-secret-key")
        assert config.api_key == "my-secret-key"

    def test_custom_tenant_id(self):
        """Config accepts custom tenant ID."""
        config = Config(tenant_id="acme-corp")
        assert config.tenant_id == "acme-corp"

    def test_custom_batch_size(self):
        """Config accepts custom batch size."""
        config = Config(batch_size=50)
        assert config.batch_size == 50

    def test_custom_timeout(self):
        """Config accepts custom timeout."""
        config = Config(timeout=60.0)
        assert config.timeout == 60.0

    def test_custom_write_tools(self):
        """Config accepts custom write tools list."""
        config = Config(write_tools=["send_email", "create_ticket"])
        assert config.write_tools == ["send_email", "create_ticket"]

    def test_custom_read_tools(self):
        """Config accepts custom read tools list."""
        config = Config(read_tools=["get_account", "search"])
        assert config.read_tools == ["get_account", "search"]

    def test_local_mode_with_postgres_url(self):
        """Config accepts local mode with postgres URL."""
        config = Config(
            local_mode=True,
            postgres_url="postgresql://user:pass@localhost/db"
        )
        assert config.local_mode is True
        assert config.postgres_url == "postgresql://user:pass@localhost/db"


class TestIsWriteTool:
    """Tests for the is_write_tool method."""

    def test_explicit_write_tool_returns_true(self):
        """Explicitly configured write tools return True."""
        config = Config(write_tools=["send_email", "create_ticket"])

        assert config.is_write_tool("send_email") is True
        assert config.is_write_tool("create_ticket") is True

    def test_explicit_read_tool_returns_false(self):
        """Explicitly configured read tools return False."""
        config = Config(read_tools=["get_account", "fetch_data"])

        assert config.is_write_tool("get_account") is False
        assert config.is_write_tool("fetch_data") is False

    def test_explicit_write_takes_precedence(self):
        """Write tools take precedence when tool appears in both lists."""
        config = Config(
            write_tools=["my_tool"],
            read_tools=["my_tool"]  # Same tool in both lists
        )

        # Write tools list is checked first
        assert config.is_write_tool("my_tool") is True

    def test_heuristic_create_is_write(self):
        """Heuristic: 'create' pattern detected as write."""
        config = Config()
        assert config.is_write_tool("create_user") is True
        assert config.is_write_tool("createRecord") is True

    def test_heuristic_update_is_write(self):
        """Heuristic: 'update' pattern detected as write."""
        config = Config()
        assert config.is_write_tool("update_account") is True
        assert config.is_write_tool("UpdateSettings") is True

    def test_heuristic_delete_is_write(self):
        """Heuristic: 'delete' pattern detected as write."""
        config = Config()
        assert config.is_write_tool("delete_user") is True
        assert config.is_write_tool("deleteRecord") is True

    def test_heuristic_send_is_write(self):
        """Heuristic: 'send' pattern detected as write."""
        config = Config()
        assert config.is_write_tool("send_email") is True
        assert config.is_write_tool("sendNotification") is True

    def test_heuristic_post_is_write(self):
        """Heuristic: 'post' pattern detected as write."""
        config = Config()
        assert config.is_write_tool("post_message") is True
        assert config.is_write_tool("postComment") is True

    def test_heuristic_put_is_write(self):
        """Heuristic: 'put' pattern detected as write."""
        config = Config()
        assert config.is_write_tool("put_data") is True
        assert config.is_write_tool("putItem") is True

    def test_heuristic_patch_is_write(self):
        """Heuristic: 'patch' pattern detected as write."""
        config = Config()
        assert config.is_write_tool("patch_record") is True
        assert config.is_write_tool("patchSettings") is True

    def test_heuristic_write_is_write(self):
        """Heuristic: 'write' pattern detected as write."""
        config = Config()
        assert config.is_write_tool("write_file") is True
        assert config.is_write_tool("writeData") is True

    def test_heuristic_set_is_write(self):
        """Heuristic: 'set' pattern detected as write."""
        config = Config()
        assert config.is_write_tool("set_value") is True
        assert config.is_write_tool("setConfig") is True

    def test_heuristic_add_is_write(self):
        """Heuristic: 'add' pattern detected as write."""
        config = Config()
        assert config.is_write_tool("add_user") is True
        assert config.is_write_tool("addItem") is True

    def test_heuristic_remove_is_write(self):
        """Heuristic: 'remove' pattern detected as write."""
        config = Config()
        assert config.is_write_tool("remove_item") is True
        assert config.is_write_tool("removeUser") is True

    def test_heuristic_get_is_not_write(self):
        """Heuristic: 'get' pattern is not detected as write."""
        config = Config()
        assert config.is_write_tool("get_user") is False
        assert config.is_write_tool("getAccount") is False

    def test_heuristic_fetch_is_not_write(self):
        """Heuristic: 'fetch' pattern is not detected as write."""
        config = Config()
        assert config.is_write_tool("fetch_data") is False
        assert config.is_write_tool("fetchRecords") is False

    def test_heuristic_list_is_not_write(self):
        """Heuristic: 'list' pattern is not detected as write."""
        config = Config()
        assert config.is_write_tool("list_items") is False
        assert config.is_write_tool("listUsers") is False

    def test_heuristic_search_is_not_write(self):
        """Heuristic: 'search' pattern is not detected as write."""
        config = Config()
        assert config.is_write_tool("search_records") is False
        assert config.is_write_tool("searchUsers") is False

    def test_heuristic_query_is_not_write(self):
        """Heuristic: 'query' pattern is not detected as write."""
        config = Config()
        assert config.is_write_tool("query_database") is False
        assert config.is_write_tool("queryData") is False

    def test_heuristic_read_is_not_write(self):
        """Heuristic: 'read' pattern is not detected as write."""
        config = Config()
        assert config.is_write_tool("read_file") is False
        assert config.is_write_tool("readConfig") is False

    def test_heuristic_case_insensitive(self):
        """Heuristic detection is case insensitive."""
        config = Config()

        # Lowercase
        assert config.is_write_tool("create_user") is True
        # Uppercase
        assert config.is_write_tool("CREATE_USER") is True
        # Mixed case
        assert config.is_write_tool("CreateUser") is True

    def test_unknown_tool_default_is_read(self):
        """Unknown tools without heuristic match default to read."""
        config = Config()

        # Tool names that don't match any patterns
        assert config.is_write_tool("process_data") is False
        assert config.is_write_tool("analyze") is False
        assert config.is_write_tool("transform") is False


class TestIsReadTool:
    """Tests for the is_read_tool method."""

    def test_is_read_tool_inverse_of_is_write_tool(self):
        """is_read_tool returns opposite of is_write_tool."""
        config = Config(write_tools=["send_email"])

        # Write tool -> not a read tool
        assert config.is_read_tool("send_email") is False

        # Read tool (by heuristic) -> is a read tool
        assert config.is_read_tool("get_account") is True

    def test_explicit_read_tools_return_true(self):
        """Explicitly configured read tools return True."""
        config = Config(read_tools=["custom_read"])

        assert config.is_read_tool("custom_read") is True

    def test_explicit_write_tools_return_false(self):
        """Explicitly configured write tools return False for is_read_tool."""
        config = Config(write_tools=["custom_write"])

        assert config.is_read_tool("custom_write") is False


class TestConfigImmutability:
    """Tests verifying Config behavior with mutable default values."""

    def test_write_tools_not_shared(self):
        """Each Config instance has its own write_tools list."""
        config1 = Config()
        config2 = Config()

        config1.write_tools.append("tool1")

        assert "tool1" not in config2.write_tools

    def test_read_tools_not_shared(self):
        """Each Config instance has its own read_tools list."""
        config1 = Config()
        config2 = Config()

        config1.read_tools.append("tool1")

        assert "tool1" not in config2.read_tools
