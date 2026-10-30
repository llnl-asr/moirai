"""moirai.agent's names and defaults, each in one place (``constants.h`` on the
C++ side). ``ConfigurationManager`` reads the settings; these are for writing
them into what a hook or a command inherits, and for reading what it was given.
"""
ENV_PREFIX = "MOIRAI_"
ENV_ENABLE = "MOIRAI_ENABLE"
ENV_LOG_FILE = "MOIRAI_LOG_FILE"
ENV_TRACE_IO = "MOIRAI_TRACE_IO"
ENV_DATA_DIR = "MOIRAI_DATA_DIR"
ENV_PC_FLUSH_MS = "MOIRAI_PC_FLUSH_MS"
ENV_AGENT_DIR = "MOIRAI_AGENT_DIR"
ENV_AGENT_TRACE_IO = "MOIRAI_AGENT_TRACE_IO"
ENV_AGENT_PRELOAD = "MOIRAI_AGENT_PRELOAD"

# As constants.h, for a launcher that has not loaded moirai.
DEFAULT_AGENT_DIR = "~/.moirai/agent"
DEFAULT_FLUSH_MS = 200
# How long a session's name (its first prompt) may be.
SESSION_NAME_CHARS = 120
