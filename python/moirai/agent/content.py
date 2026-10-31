"""What an agent exchanged, on its way to moirai's artifact store.

A trace holds names, not payloads. Every prompt, response, tool input and
output becomes a transient artifact, and its entity's URI is the artifact's
key. Secrets are taken out first, so what is stored -- and the digest in the
trace -- is of the redacted text: a secret cannot be confirmed from a trace.
"""
import json

from moirai.agent.redact import (SECRETS, is_sensitive_path, redact_path,
                                  redact_text, sensitive_globs, site_patterns)


def render(value):
    """A value as text: strings as they are, the rest as stable JSON."""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", "replace")
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


class Content:
    """Redacts and keeps values through ``api``, moirai's API."""

    def __init__(self, api):
        self.api = api
        conf = api.agent_configuration()
        self.patterns = SECRETS + site_patterns(conf.redact)
        self.globs = sensitive_globs(conf.sensitive_paths)

    def sensitive(self, path):
        """Whether ``path`` is a file whose name and content are not kept."""
        return is_sensitive_path(path, self.globs)

    def path(self, path):
        """``path`` as it may be stored: see :func:`redact.redact_path`."""
        return redact_path(path, self.patterns, self.globs)

    def put(self, value):
        """Keep ``value``; the URI for its entity."""
        text, _ = redact_text(render(value), self.patterns)
        return self.api.store_artifact(text).uri

    def file(self, path, lifetime):
        """Keep the file at ``path``: its artifact, falsy if unreadable."""
        return self.api.store_artifact_file(path, lifetime)
