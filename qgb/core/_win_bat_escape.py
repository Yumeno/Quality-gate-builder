"""Windows ``.bat`` / ``.cmd`` argument escaping (Step 3.1d).

When the user's ``contract.command`` invokes a ``.bat`` / ``.cmd``
file, the Windows ``cmd.exe`` interpreter parses argv in **two
distinct stages** before the script sees the values:

1. **MSVCRT / ``CommandLineToArgvW`` parsing.** The command line is a
   single string; cmd.exe splits it on whitespace and respects the
   classic C runtime rules for double quotes and backslashes.

2. **cmd.exe metacharacter interpretation.** After argv is split,
   cmd.exe interprets ``&``, ``|``, ``<``, ``>``, ``^``, ``%``, etc.
   in the resulting tokens — but **not inside double-quoted regions**.
   A literal ``a & b`` in argv[1] becomes "run program ``a``, then
   run program ``b``" — a command injection vector if the argument
   came from user data.

The combined rule we follow:

* Apply the MSVCRT layer ourselves (the algorithm matches
  ``subprocess.list2cmdline``, re-implemented here for explicitness):
  any argument with whitespace, ``"``, or a cmd.exe metacharacter
  gets wrapped in ``"..."`` with backslash/quote handling per CRT
  rules. The wrapping is what makes cmd.exe treat the metacharacters
  as literal (quoted region).
* Then, defensively prefix any remaining ``^``-needs character that
  could leak out of a quoted region with a literal ``^``. In
  practice the MSVCRT layer alone is sufficient for ``.bat`` because
  cmd.exe's metacharacter scan respects quotes — but we keep the
  carat pass as a belt-and-braces for the few cases where the
  metacharacter could appear after a closing quote (e.g. a future
  caller that bypasses our string builder).

The resulting command line is passed to :class:`subprocess.Popen` as
a single string (``args=str``), **not** as a list. When ``args`` is a
str on Windows and ``shell=False``, Popen passes the string verbatim
to ``CreateProcessW`` — bypassing ``list2cmdline``, which would
otherwise re-quote our output. This is the Microsoft-recommended way
to take exact control over the command line on Windows
(see :func:`subprocess.list2cmdline` docs).

What is **out of scope** for Step 3.1d (framework-shape.md §5):

* Delayed expansion ``!VAR!`` is a stateful cmd.exe mode toggled by
  ``SETLOCAL ENABLEDELAYEDEXPANSION`` inside the user's ``.bat``.
  If the user's script enables it AND we pass ``!VAR!`` as an
  argument, the script may interpret it at execution time. We do
  **not** escape ``!`` — production ``.bat`` files should either
  keep delayed expansion off or never read raw user input.
* Calling ``cmd.exe`` with ``argv[0]="cmd.exe"`` and ``argv[1]``
  being the ``.bat`` path. The escaping below targets the case
  ``argv[0]`` is the ``.bat`` directly.
* Other shell-like targets (``.ps1`` PowerShell scripts, WSH ``.vbs``)
  parse arguments under their own rules and need their own escapers.

References:

* MSVCRT argv parsing:
  https://learn.microsoft.com/en-us/cpp/cpp/main-function-command-line-args#parsing-c-command-line-arguments
* cmd.exe escape character (``^``):
  https://ss64.com/nt/syntax-esc.html
* CreateProcess command line semantics:
  https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw
"""

from __future__ import annotations

import os
from pathlib import PurePath

# cmd.exe metacharacters. Any argument that contains one of these is
# wrapped in double quotes so cmd.exe's metacharacter scan skips it
# (cmd.exe explicitly ignores metacharacters inside quoted tokens,
# except for ``%`` expansion which is handled by ``%`` being escaped
# AFTER MSVCRT wrapping). The carat itself is in the set so a literal
# ``^`` triggers wrapping too — otherwise a bare ``^`` at the end of
# an argument could merge with whatever follows it on the command line.
_CMD_METACHARACTERS = "&|<>()%^"


def needs_bat_escaping(argv: list[str]) -> bool:
    """Return True iff ``argv[0]`` is a ``.bat`` / ``.cmd`` invocation.

    Step 3.1d only escapes when the direct target is a batch file.
    Plain ``.exe`` / interpreter targets do not go through cmd.exe and
    therefore do not need the metacharacter layer; ``subprocess`` /
    Python's own list2cmdline handles the MSVCRT layer correctly for
    those cases.

    Mixed-case extensions and short paths are both accepted because
    Windows is case-insensitive on file names.
    """
    if os.name != "nt":
        return False
    if not argv:
        return False
    head = argv[0]
    if not isinstance(head, str) or not head:
        return False
    suffix = PurePath(head).suffix.lower()
    return suffix in (".bat", ".cmd")


def escape_argv_for_msvcrt(arg: str) -> str:
    """Return ``arg`` quoted per CommandLineToArgvW rules.

    This is the algorithm used by ``subprocess.list2cmdline``,
    re-implemented here so :func:`build_command_line` can pin the
    behaviour without depending on a private stdlib helper, and so we
    can layer the cmd.exe carat pass on top.

    Rules (citing the MS docs linked at the top of this module):

    * A run of N backslashes followed by ``"``: each backslash
      doubles, and the ``"`` is escaped to ``\\"``.
    * A run of N backslashes NOT followed by ``"``: literal.
    * Whitespace, ``"``, or a cmd.exe metacharacter: wrap in double
      quotes. Whitespace alone follows ``list2cmdline``; the
      metacharacter case is the Step 3.1d extension — wrapping is
      what makes cmd.exe treat the metacharacters as literal **after
      we additionally carat-prefix them inside the quotes**, see
      :func:`build_command_line`.
    * Trailing backslashes inside a quoted region: double them so
      they do not merge with the closing quote.
    * Empty argument: ``""`` so it occupies an argv slot.

    The function does **not** apply the carat pass — that is the
    caller's responsibility (:func:`build_command_line` does it for
    ``.bat`` invocations only). This separation keeps the MSVCRT
    layer reusable for other Windows target types.
    """
    if not arg:
        return '""'

    needs_quotes = any(
        ch in arg
        for ch in (" ", "\t", '"', *_CMD_METACHARACTERS)
    )

    result: list[str] = []
    backslash_run = 0
    for ch in arg:
        if ch == "\\":
            backslash_run += 1
        elif ch == '"':
            # Double the preceding backslashes, then escape the quote.
            result.append("\\" * (backslash_run * 2))
            backslash_run = 0
            result.append("\\\"")
        else:
            if backslash_run:
                result.append("\\" * backslash_run)
                backslash_run = 0
            result.append(ch)
    if backslash_run:
        if needs_quotes:
            result.append("\\" * (backslash_run * 2))
        else:
            result.append("\\" * backslash_run)

    body = "".join(result)
    return f'"{body}"' if needs_quotes else body


def escape_cmd_metacharacters(arg: str) -> str:
    """Prefix each cmd.exe metacharacter in ``arg`` with ``^``.

    Used as the second pass **after** MSVCRT quoting, on the assumption
    that the quoting in :func:`escape_argv_for_msvcrt` already
    neutralises metacharacters inside the quoted span. The carat
    pass is therefore a defence in depth: it handles ``^`` characters
    that survived (because the argument did not need quoting), and a
    future caller who bypasses :func:`build_command_line` and writes
    a raw command line by hand.

    Empty string passes through unchanged.
    """
    if not arg:
        return arg
    return "".join(
        ("^" + ch) if ch in _CMD_METACHARACTERS else ch
        for ch in arg
    )


def build_command_line(argv: list[str]) -> str:
    """Return a Windows command line string for a ``.bat`` argv.

    The result is suitable for ``subprocess.Popen(args=string,
    shell=False)`` on Windows.

    For each non-argv-0 item we apply **both** Windows-side layers:

    1. The cmd.exe carat pass (``^`` before each ``& | < > ( ) % ^``)
       — this protects against cmd.exe metacharacter scanning which
       happens **even inside** the quoted region when the target is
       a ``.bat`` / ``.cmd`` (see Microsoft's "everyone quotes
       arguments the wrong way" article; the cmd.exe-as-intermediary
       case is the load-bearing scenario).
    2. The MSVCRT quoting pass (:func:`escape_argv_for_msvcrt`) —
       this protects against argv splitting and escapes ``"``
       characters per CRT rules.

    Order matters: the carat MUST run first so the ``^`` characters
    it introduces are inside the quoted region that the MSVCRT pass
    creates. If we applied MSVCRT first, the carat pass would prefix
    the surrounding ``"`` and corrupt the token.

    ``argv[0]`` (the script path) is left untouched.

    Empty argv → empty string (caller is expected to check
    ``needs_bat_escaping`` first; calling with an empty argv would
    not invoke anything anyway).
    """
    if not argv:
        return ""
    head = argv[0]
    escaped_tail: list[str] = []
    for a in argv[1:]:
        carat_escaped = _carat_escape_metacharacters(a)
        escaped_tail.append(escape_argv_for_msvcrt(carat_escaped))
    if not escaped_tail:
        return head
    return f"{head} " + " ".join(escaped_tail)


def _carat_escape_metacharacters(arg: str) -> str:
    """Prefix cmd.exe metacharacters with ``^``.

    Internal helper for :func:`build_command_line`. The carat itself
    is escaped to ``^^`` so a literal ``^`` survives cmd.exe's own
    carat-processing pass.

    This is intentionally a different function from
    :func:`escape_cmd_metacharacters`, whose public-API contract is
    "transform an already-quoted MSVCRT token". The build-time pass
    here runs on the *raw* user argument before MSVCRT wrapping.
    """
    if not arg:
        return arg
    return "".join(
        ("^" + ch) if ch in _CMD_METACHARACTERS else ch
        for ch in arg
    )


def apply_bat_escaping(argv: list[str]) -> list[str]:
    """Convenience pass-through retained for unit-test compatibility.

    Step 3.1d's runtime path uses :func:`build_command_line` because
    Popen needs a single string (a list would go back through
    ``list2cmdline`` and undo our quoting). This function remains as
    a *list*-shaped helper for tests that want to inspect per-argument
    transforms without rebuilding the full command line.

    ``argv[0]`` is left untouched; each subsequent item is replaced
    by the carat-then-MSVCRT escaped form (same order as
    :func:`build_command_line`).
    """
    if not argv:
        return argv
    out: list[str] = [argv[0]]
    for arg in argv[1:]:
        carat_escaped = _carat_escape_metacharacters(arg)
        out.append(escape_argv_for_msvcrt(carat_escaped))
    return out
