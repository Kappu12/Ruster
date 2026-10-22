"""Per-user MCP configuration. Never stored in map/project data."""
import secrets
from . import settings

DEFAULT_PORT=9877


def port(config):
    value=config.get('mcp_port',DEFAULT_PORT)
    return value if isinstance(value,int) and not isinstance(value,bool) and 1024<=value<=65535 else DEFAULT_PORT


def enabled(config):return config.get('mcp_enabled') is True


def token():
    config=settings.load()
    value=config.get('mcp_token')
    if not isinstance(value,str) or len(value)<32:
        value=secrets.token_urlsafe(32)
        settings.save({**config,'mcp_token':value})
    return value
