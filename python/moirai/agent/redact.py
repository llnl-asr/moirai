"""What is taken out of text and names before they are stored or shown.

Shared by the recorder and by any consumer. Importing this needs no native
module.

Text: :data:`SECRETS` are the credentials that show up in tool output and
environment dumps; :func:`redact_text` replaces them and keeps what names the
secret. ``MOIRAI_AGENT_REDACT`` adds a site's own patterns, one per line
(:func:`site_patterns`).

Names: a path can give a secret away (``/home/x/.aws/credentials``,
``sk-...`` in a file name) or name something that should not be in a report.
:func:`redact_path` applies the secret patterns to a path and replaces the whole
name of a *sensitive file* (:func:`is_sensitive_path`) by a stable placeholder,
``sensitive-file:1a2b3c4d``: the same file is always the same placeholder, so
two accesses still correlate, and the name is not revealed. Which files are
sensitive is :data:`SENSITIVE_PATHS` plus ``MOIRAI_AGENT_SENSITIVE_PATHS``.

The names in a dftracer trace of a traced command are *not* redacted: they are
written by the traced processes, not by moirai. A consumer calls
:func:`redact_path` on every name it displays.
"""
import fnmatch
import hashlib
import os
import re

# Credentials that show up in tool output and environment dumps. Replacements
# keep what names the secret. MOIRAI_AGENT_REDACT adds a site's own patterns,
# one per line.
SECRETS = [
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "[REDACTED:api-key]"),
    (re.compile(r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{20,}"),
     "[REDACTED:github-token]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "[REDACTED:github-token]"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"), "[REDACTED:gitlab-token]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "[REDACTED:slack-token]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED:aws-key]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?"
                r"-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "[REDACTED:private-key]"),
    (re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]{16,}"),
     r"\1[REDACTED:bearer]"),
    (re.compile(r"(?i)((?:[a-z0-9_]*(?:api[_-]?key|secret|token|passw(?:or)?d)"
                r"[a-z0-9_]*)[\"']?\s*[=:]\s*[\"']?)[^\s\"',;]{6,}"),
     r"\1[REDACTED:assignment]"),
]

# Files that hold credentials, by glob. Without a '/', a glob is matched
# against the file's name; with one, against the end of the path ('*' matches
# '/' too, so '.ssh/*' is everything below a .ssh directory); starting with
# '/', against the whole path. Case does not matter.
SENSITIVE_PATHS = [
    ".env*", ".netrc", "_netrc", ".git-credentials",
    ".npmrc", ".pypirc", ".pgpass", ".htpasswd",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore",
    ".aws/credentials", ".ssh/*", ".gnupg/*", ".config/gh/hosts.yml",
    ".docker/config.json", ".kube/config",
    "*secret*", "*credential*", "*token*",
]


def site_patterns(text):
    return [(re.compile(p), "[REDACTED:site]")
            for p in (text or "").splitlines() if p]


def redact_text(text, patterns=None):
    """``(text, count)`` with the credentials in ``text`` replaced. ``patterns``
    is a list of ``(compiled regex, replacement)``; the default is
    :data:`SECRETS`."""
    total = 0
    for pattern, replacement in SECRETS if patterns is None else patterns:
        text, n = pattern.subn(replacement, text)
        total += n
    return text, total


def sensitive_globs(setting=None):
    """The globs in effect: :data:`SENSITIVE_PATHS` and ``setting``'s (default:
    ``moirai.agent_configuration().sensitive_paths``, and with no native module
    nothing, so the built-in list still holds), one per line.
    A line ``!glob`` drops that glob from the list so far; a first line
    ``@only`` makes the list just what follows. Blank lines and lines starting
    with ``#`` are ignored."""
    if setting is None:
        try:
            import moirai

            setting = moirai.agent_configuration().sensitive_paths
        except ImportError:
            setting = ""
    lines = [ln.strip() for ln in str(setting or "").splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    globs = list(SENSITIVE_PATHS)
    if lines[:1] == ["@only"]:
        globs, lines = [], lines[1:]
    for line in lines:
        if line.startswith("!"):
            globs = [g for g in globs if g != line[1:].strip()]
        elif line not in globs:
            globs.append(line)
    return globs


def _match(glob, path):
    glob, path = glob.lower(), path.lower()
    if glob.startswith("/"):
        return fnmatch.fnmatchcase(path, glob)
    if "/" in glob:
        return fnmatch.fnmatchcase("/" + path.lstrip("/"), "*/" + glob)
    return fnmatch.fnmatchcase(path.rstrip("/").rsplit("/", 1)[-1], glob)


def is_sensitive_path(path, globs=None):
    """Whether ``path`` names a file that should not be shown by name."""
    path = os.fspath(path)
    return any(_match(g, path) for g in (sensitive_globs() if globs is None
                                         else globs))


def placeholder(path):
    """The stable stand-in for a sensitive file's name."""
    digest = hashlib.sha256(os.path.normpath(os.fspath(path)).encode(
        "utf-8", "replace")).hexdigest()[:8]
    return f"sensitive-file:{digest}"


def redact_path(path, patterns=None, globs=None):
    """``path`` as it may be stored or shown: the placeholder if it is a
    sensitive file, else with the secret patterns applied. Anything that is not
    text is returned as it is."""
    if not isinstance(path, (str, os.PathLike)):
        return path
    path = os.fspath(path)
    if is_sensitive_path(path, globs):
        return placeholder(path)
    return redact_text(path, patterns)[0]
