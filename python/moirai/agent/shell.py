"""Shell lines: the files they name, and how to show them.

Two jobs on one parser's worth of knowledge:

* :func:`shell_files` -- ``(scripts, reads, writes)``, the paths a shell line
  names, which the recorder turns into ``used`` / ``generated`` relations.
* :func:`command_lines`, :func:`command_language`, :func:`command_summary` --
  render a command the way it was written, not the way it was passed. An agent
  that wants to run a twenty-line Python program hands the whole program to
  ``python3 -c`` as one argument; the quoting that survives
  (``$'import csv\\nrows=[]\\n...'``) is correct and unreadable. The program is
  pulled back out and shown as a program. Three shapes cover what agents send:

  * an inline program -- ``python3 -c '...'``, ``bash -c``, ``perl -e``;
  * a heredoc -- ``python3 - <<'PY' ... PY``;
  * a plain shell command, possibly a chain of them.

  Nothing is invented and nothing is dropped: the invocation is shown exactly
  as written, and the program body is the argument with its quoting undone.
"""
import os
import re
import shlex

INTERPRETERS = {"python", "python3", "bash", "sh", "zsh", "perl", "ruby",
                "node", "Rscript", "lua", "awk", "julia"}


def shell_files(command, cwd):
    """``(scripts, reads, writes)``: the paths named on a shell line. Only what
    is named: what a script opens by itself is seen by tracing it, not here."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return [], [], []
    scripts, reads, writes = [], [], []
    start, redirect = True, False
    for i, token in enumerate(tokens):
        if set(token) <= set("|&;()<>"):
            redirect = ">" in token
            start = not (redirect or "<" in token)
            continue
        path = os.path.normpath(os.path.join(cwd, os.path.expanduser(token)))
        was_redirect, redirect = redirect, False
        if was_redirect:
            writes.append(path)
        elif os.path.isfile(path):
            after_interpreter = (i > 0 and os.path.basename(tokens[i - 1])
                                 in INTERPRETERS)
            run = start and ("/" in token and os.access(path, os.X_OK))
            (scripts if run or after_interpreter else reads).append(path)
        elif not start and ("/" in token or "." in token) and os.path.isdir(
                os.path.dirname(path)):
            writes.append(path)  # not there yet: it may be an output
        start = False
    return scripts, reads, writes


# How many lines of an inline program to show before saying how many are left.
MAX_PROGRAM_LINES = 200
# Below this a command is already readable: ``bash -c 'ls'`` stays as it is.
MIN_REFORMAT_LENGTH = 80
# How deep to follow one interpreter invoking another.
MAX_NESTING = 3

# Which flag gives an interpreter its program as an argument. Per interpreter:
# ``grep -e pattern`` is a pattern, not a program.
INLINE_PROGRAM_FLAGS = {
    "python": {"-c"},
    "perl": {"-e", "-E"},
    "ruby": {"-e"},
    "node": {"-e", "--eval"},
    "bash": {"-c"},
    "sh": {"-c"},
    "zsh": {"-c"},
    "dash": {"-c"},
}
# What an inline program is written in, as highlight.js names it.
INTERPRETER_LANGUAGES = {
    "python": "python",
    "perl": "perl",
    "ruby": "ruby",
    "node": "javascript",
    "bash": "bash",
    "sh": "bash",
    "zsh": "bash",
    "dash": "bash",
}
SHELL_LANGUAGE = "bash"
# The comment that names the invocation, where it is not ``#``.
COMMENT_MARKERS = {"javascript": "//"}
# The escapes of bash's ``$'...'``; anything else is left as written.
ANSI_C_ESCAPES = {
    "a": "\a",
    "b": "\b",
    "e": "\x1b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "?": "?",
}
CHAIN_OPERATORS = ("&&", "||", ";", "|")
# Words after which a command starts.
COMMAND_SEPARATORS = frozenset({"&&", "||", ";", "|", "|&", "(", "{", "then",
                                "do", "else"})
# Lines that open a program without saying what it does.
PREAMBLE = ("import ", "from ", "#", "\'\'\'", '"""', "use ", "require ",
            "set -")

HEREDOC = re.compile(
    r"<<-?\s*(?P<quote>['\"]?)(?P<marker>[A-Za-z_][A-Za-z0-9_]*)(?P=quote)")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
EMPTY_INIT = re.compile(r"^[\w.]+\s*=\s*(\[\]|\{\}|\(\)|''|\"\"|0)\s*$")


def command_lines(command):
    """``command`` laid out for reading: as the program it carries, or as a
    chain, one command to a line. One readable line stays as it is."""
    text = (command or "").strip()
    if not text:
        return ""
    program = _heredoc_program(text) or _inline_program(text)
    if program:
        return _program_block(*program)
    return _chain_block(text)


def command_language(command):
    """The language of what :func:`command_lines` shows, as highlight.js names
    it: the program's, else the shell."""
    text = (command or "").strip()
    program = _heredoc_program(text) or _inline_program(text)
    return program[2] if program and program[2] else SHELL_LANGUAGE


def command_summary(command, limit=60):
    """One line naming what ``command`` did, cut to ``limit``: for a program its
    invocation, its length and the first line that says anything."""
    text = (command or "").strip()
    program = _heredoc_program(text) or _inline_program(text)
    if program:
        invocation, body, _ = program
        lines = [line for line in body.splitlines() if line.strip()]
        subject = _first_substantive(lines)
        count = f"({len(lines)} lines)" if len(lines) > 1 else ""
        text = " ".join(part for part in (invocation, count, subject) if part)
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[:limit]}..."


def _first_substantive(lines):
    """The first line that is not preamble, else the first."""
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(PREAMBLE) and not EMPTY_INIT.match(stripped):
            return stripped
    return lines[0].strip() if lines else ""


def _program_block(invocation, body, language):
    """The invocation, as a comment of the program's language so that the block
    is one piece of source, then the program."""
    lines = body.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    note = f"{len(lines)} line{'s' if len(lines) != 1 else ''}"
    if language:
        note += f" of {language}"
    shown = lines[:MAX_PROGRAM_LINES]
    if len(lines) > MAX_PROGRAM_LINES:
        shown.append(f"... {len(lines) - MAX_PROGRAM_LINES} more line(s)")
    marker = COMMENT_MARKERS.get(language, "#")
    return "\n".join([f"{marker} {invocation}    ({note})", "", *shown])


def _chain_block(text):
    """A long chain of commands, one per line with what joined it."""
    if len(text) < MIN_REFORMAT_LENGTH or "\n" in text:
        return text
    parts = _split_chain(text)
    if len(parts) < 2:
        return text
    lines = [parts[0][1]]
    lines += [f"  {operator} {segment}" for operator, segment in parts[1:]]
    return "\n".join(lines)


def _split_chain(text):
    """``(operator, command)`` per segment, split at unquoted operators; the
    first operator is empty."""
    parts = []
    operator = ""
    start = 0
    for index, quoted in _scan(text):
        if quoted:
            continue
        found = next((op for op in CHAIN_OPERATORS
                      if text.startswith(op, index)), "")
        if not found:
            continue
        parts.append((operator, text[start:index].strip()))
        operator = found
        start = index + len(found)
    parts.append((operator, text[start:].strip()))
    return [part for part in parts if part[1]]


def _scan(text):
    """``(index, quoted)`` for each position of a command."""
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\\" and index + 1 < length:
            yield index, True
            yield index + 1, True
            index += 2
            continue
        if char == "'" or (char == "$" and text.startswith("$'", index)):
            start = index + (2 if char == "$" else 1)
            end = _closing_quote(text, start, "'", ansi_c=char == "$")
            for position in range(index, min(end + 1, length)):
                yield position, True
            index = end + 1
            continue
        if char == '"':
            end = _closing_quote(text, index + 1, '"', ansi_c=False)
            for position in range(index, min(end + 1, length)):
                yield position, True
            index = end + 1
            continue
        yield index, False
        index += 1


def _closing_quote(text, start, quote, *, ansi_c):
    """Where the quote opened at ``start`` closes, or the end of the text. A
    plain ``'...'`` has no escapes; ``$'...'`` and ``"..."`` do."""
    index = start
    escapes = ansi_c or quote == '"'
    while index < len(text):
        char = text[index]
        if escapes and char == "\\" and index + 1 < len(text):
            index += 2
            continue
        if char == quote:
            return index
        index += 1
    return len(text)


def _inline_program(text, depth=0):
    """``(invocation, program, language)`` of a program given to an interpreter
    as an argument, at any command position (``cd data && python3 -c '...'``),
    or ``None``."""
    words = _words(text)
    if len(words) < 2 or depth >= MAX_NESTING:
        return None
    for position in _command_positions(words):
        flags = INLINE_PROGRAM_FLAGS.get(_interpreter_name(words[position][0]))
        if not flags:
            continue
        found = _program_after(text, words, position, flags, depth)
        if found:
            return found
    return None


def _program_after(text, words, position, flags, depth):
    """The program the interpreter at ``position`` was given, if any."""
    name = _interpreter_name(words[position][0])
    for offset in range(position + 1, len(words) - 1):
        value, _, end = words[offset]
        if value not in flags:
            continue
        program, _, program_end = words[offset + 1]
        language = INTERPRETER_LANGUAGES.get(name, "")
        # A shell given a program is usually a wrapper around the real one.
        if language == SHELL_LANGUAGE:
            nested = (_inline_program(program, depth + 1)
                      or _heredoc_program(program))
            if nested:
                inner_invocation, inner_program, inner_language = nested
                prefix = text[:end].strip()
                return (f"{prefix} … {inner_invocation}", inner_program,
                        inner_language)
        if "\n" not in program and len(program) < MIN_REFORMAT_LENGTH:
            return None
        invocation = text[:end].strip()
        trailing = text[program_end:].strip()
        if trailing:
            invocation = f"{invocation} … {trailing}"
        return invocation, program, language
    return None


def _command_positions(words):
    """Where a command name can start: stepping over assignments and ``env``,
    so that ``PYTHONPATH=. python3 -c`` is python."""
    positions = []
    expecting = True
    for index, (value, _, _) in enumerate(words):
        if value in COMMAND_SEPARATORS:
            expecting = True
            continue
        if not expecting:
            continue
        if ASSIGNMENT.match(value) or value == "env":
            continue
        positions.append(index)
        expecting = False
    return positions


def _heredoc_program(text):
    """``(invocation, program, language)`` of a program fed to an interpreter
    as a heredoc, or ``None``."""
    match = HEREDOC.search(text)
    if not match:
        return None
    newline = text.find("\n", match.end())
    if newline == -1:
        return None
    marker = match.group("marker")
    invocation = text[:newline].strip()
    body, trailing = [], []
    closed = False
    for line in text[newline + 1:].split("\n"):
        if not closed and line.strip() == marker:
            closed = True
            continue
        (trailing if closed else body).append(line)
    rest = " ".join(line.strip() for line in trailing if line.strip())
    if rest:
        invocation = f"{invocation} … {rest}"
    # The interpreter is what started the command the heredoc feeds.
    head = _words(text[:match.start()])
    positions = _command_positions(head)
    name = _interpreter_name(head[positions[-1]][0]) if positions else ""
    return invocation, "\n".join(body), INTERPRETER_LANGUAGES.get(name, "")


def _words(text):
    """``(value, start, end)`` per word, quoting undone; the offsets are into
    ``text``, so an invocation can be shown as it was written."""
    words = []
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index] in " \t\n":
            index += 1
        if index >= length:
            break
        start = index
        value = []
        while index < length and text[index] not in " \t\n":
            char = text[index]
            if char == "'":
                end = _closing_quote(text, index + 1, "'", ansi_c=False)
                value.append(text[index + 1:end])
                index = end + 1
            elif char == "$" and text.startswith("$'", index):
                end = _closing_quote(text, index + 2, "'", ansi_c=True)
                value.append(_unescape_ansi_c(text[index + 2:end]))
                index = end + 1
            elif char == '"':
                end = _closing_quote(text, index + 1, '"', ansi_c=False)
                value.append(_unescape_double(text[index + 1:end]))
                index = end + 1
            elif char == "\\" and index + 1 < length:
                value.append(text[index + 1])
                index += 2
            else:
                value.append(char)
                index += 1
        words.append(("".join(value), start, index))
    return words


def _unescape_ansi_c(body):
    """Undo ``$'...'``'s escapes, leaving unknown ones as written."""
    out = []
    index = 0
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body):
            escape = body[index + 1]
            out.append(ANSI_C_ESCAPES.get(escape, char + escape))
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _unescape_double(body):
    """Undo what a double-quoted string escapes (``"``, ``\\``, ``$``, a
    backtick); any other backslash is a backslash."""
    out = []
    index = 0
    while index < len(body):
        if (body[index] == "\\" and index + 1 < len(body)
                and body[index + 1] in '"\\$`'):
            out.append(body[index + 1])
            index += 2
            continue
        out.append(body[index])
        index += 1
    return "".join(out)


def _interpreter_name(word):
    """The interpreter a word names, without path or version: ``python`` for
    ``/usr/bin/python3.11``, ``node`` for ``nodejs``."""
    name = word.rsplit("/", 1)[-1]
    if name.startswith("nodejs"):
        return "node"
    return re.sub(r"[0-9.]+$", "", name) or name
