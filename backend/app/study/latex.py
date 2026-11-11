"""Static LaTeX safety and syntax checks for formula sheets (spec 10.3, 10.4).

Nothing here proves a formula is mathematically correct; it only rejects unsafe input and flags
syntax a renderer would choke on. Expressions are rendered client-side by a safe renderer
(KaTeX-style, no HTML trust); the backend never renders or evaluates them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_EXPRESSION = 600

_FORBIDDEN = re.compile(
    r"\\(?:href|url|input|include|includegraphics|write|read|openin|openout|def|edef|gdef|xdef|"
    r"let|newcommand|renewcommand|providecommand|newenvironment|catcode|csname|immediate|verb|"
    r"usepackage|documentclass|special|expandafter|style|class|htmlClass|htmlId|htmlStyle|"
    r"htmlData|char|message|errmessage|jobname|number|romannumeral|string)(?![A-Za-z])"
)
_HTML = re.compile(r"</?[A-Za-z!]|javascript:|data:|&#|&[a-z]+;", re.IGNORECASE)
_DELIMS = (("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)"), ("$", "$"))
_BEGIN_END = re.compile(r"\\(begin|end)\s*\{([A-Za-z*]+)\}")
_KNOWN_ENVS = frozenset(
    {"matrix", "pmatrix", "bmatrix", "vmatrix", "cases", "aligned", "array", "align", "split"}
)
_NOT_VARIABLES = frozenset(
    "frac dfrac sqrt sum prod int lim log ln exp sin cos tan sec csc cot sinh cosh tanh arcsin "
    "arccos arctan min max sup inf det dim ker cdot times div pm mp leq geq neq approx equiv "
    "propto infty partial nabla left right text mathrm mathbf mathbb mathcal mathit operatorname "
    "ldots cdots dots vec hat bar overline underline tilde dot ddot begin end quad qquad to "
    "rightarrow leftarrow Rightarrow Leftrightarrow in notin subset cup cap forall exists "
    "binom bigl bigr Big Bigr Bigl langle rangle mid".split()
)
_GREEK = frozenset(
    "alpha beta gamma delta epsilon varepsilon zeta eta theta lambda mu nu xi pi rho sigma tau "
    "phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Phi Psi Omega".split()
)
_SYMBOL = re.compile(r"\\([A-Za-z]+)|([A-Za-z])")
_TEXT_ARG = re.compile(r"\\(?:text|mathrm|operatorname|mathbf)\s*\{[^{}]*\}")
_SUBSCRIPT = re.compile(r"_\s*(?:\{[^{}]*\}|[A-Za-z0-9])")


@dataclass
class LatexCheck:
    expression: str
    dangerous: bool = False
    issues: list[str] = field(default_factory=list)  # fixed codes, never the expression itself

    @property
    def ok(self) -> bool:
        return not self.dangerous and not self.issues


def strip_delimiters(expr: str) -> str:
    text = expr.strip()
    for open_, close in _DELIMS:
        if len(text) >= len(open_) + len(close) and text.startswith(open_) and text.endswith(close):
            return text[len(open_) : len(text) - len(close)].strip()
    return text


def _brace_balanced(expr: str) -> bool:
    depth = 0
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == "\\":
            i += 2  # skip the escaped character (\{ \} \\)
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0


def check_latex(raw: str) -> LatexCheck:
    expr = strip_delimiters(raw)
    result = LatexCheck(expression=expr)
    if not expr or len(expr) > MAX_EXPRESSION:
        result.dangerous = True
        result.issues.append("length")
        return result
    if _FORBIDDEN.search(expr) or _HTML.search(expr) or "\x00" in expr:
        result.dangerous = True
        result.issues.append("unsafe_content")
        return result
    if "$" in expr.replace("\\$", ""):
        result.issues.append("stray_dollar")
    if not _brace_balanced(expr):
        result.issues.append("unbalanced_braces")
    stack: list[str] = []
    for kind, env in _BEGIN_END.findall(expr):
        if env.rstrip("*") not in _KNOWN_ENVS:
            result.issues.append("unknown_environment")
        elif kind == "begin":
            stack.append(env)
        elif not stack or stack.pop() != env:
            result.issues.append("mismatched_environment")
    if stack:
        result.issues.append("mismatched_environment")
    if expr.count("\\left") != expr.count("\\right"):
        result.issues.append("unbalanced_left_right")
    if re.search(r"\\\s*$", expr):
        result.issues.append("trailing_backslash")
    result.issues = list(dict.fromkeys(result.issues))
    return result


def variable_symbols(expr: str) -> set[str]:
    """Symbols that should be defined as variables: single letters and Greek letters, ignoring
    function names, operators, text arguments and subscripts."""
    cleaned = _SUBSCRIPT.sub("", _TEXT_ARG.sub("", expr))
    symbols: set[str] = set()
    for command, letter in _SYMBOL.findall(cleaned):
        if letter:
            symbols.add(letter)
        elif command in _GREEK:
            symbols.add("\\" + command)
    return symbols


def defined_symbol(name: str) -> str:
    """Base symbol of a variable name such as '$v_0$', 'x', 'alpha' or '\\alpha'."""
    text = _SUBSCRIPT.sub("", strip_delimiters(name)).replace(" ", "")
    match = re.match(r"^\\?[A-Za-z]+", text)
    token = match.group(0).lstrip("\\") if match else text
    if token in _GREEK:
        return "\\" + token
    return token[:1]
