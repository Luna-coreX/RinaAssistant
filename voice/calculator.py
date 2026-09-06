"""
A calculator for voice and text commands.

Understands "посчитай 15*12", "сколько будет 2+2", "20 процентов от 3000",
and also verbal operators ("умножь 7 на 6"), because speech recognition
almost never gives out the symbols "*" and "/".

The computation goes over a parsed expression tree (ast) with a whitelist of
nodes — eval() must not be used on a string from a microphone.
"""

import ast
import operator
import re

from core.i18n import t as tr


# a command counts as "about arithmetic" if it begins with one of these
# words (action verbs too: "умножь 7 на 6" is a request to compute)
TRIGGERS = (
    "посчитай", "подсчитай", "вычисли", "сколько будет", "чему равно",
    "умножить", "умножь", "разделить", "раздели", "поделить", "подели",
    "прибавь", "прибавить", "отними", "отнять", "вычти", "вычесть", "сложи",
    "calculate", "compute", "how much is", "what is",
)

# Verbal operators -> symbols (speech gives no arithmetic signs).
# The order matters: compound phrases come first, or "разделить на" falls
# apart into "разделить" plus a separate "на" and the expression breaks.
WORD_OPS = [
    # the compound ones
    (r"\bразделить на\b", "/"), (r"\bподелить на\b", "/"),
    (r"\bумножить на\b", "*"), (r"\bумножь на\b", "*"),
    (r"\bdivided by\b", "/"), (r"\bmultiplied by\b", "*"),
    (r"\bв степени\b", "**"), (r"\bв квадрате\b", "**2"),
    # the single ones
    (r"\bплюс\b", "+"), (r"\bприбавить\b", "+"), (r"\bсложить\b", "+"),
    (r"\bминус\b", "-"), (r"\bотнять\b", "-"), (r"\bвычесть\b", "-"),
    (r"\bумножить\b", "*"), (r"\bумножь\b", "*"),
    (r"\bразделить\b", "/"), (r"\bподелить\b", "/"),
    (r"\bplus\b", "+"), (r"\bminus\b", "-"), (r"\btimes\b", "*"),
    # "на" as multiplication — only last, once the other phrases are parsed
    (r"\bна\b(?=\s*\d)", "*"),
]

_ALLOWED_BINOP = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

MAX_POWER = 64          # a guard against 9**99999999 (hanging/memory)


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError("unsupported constant")
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_BINOP:
            raise ValueError("unsupported operator")
        left, right = _eval_node(node.left), _eval_node(node.right)
        if op_type is ast.Pow and (abs(right) > MAX_POWER or abs(left) > 1e6):
            raise ValueError("power too large")
        return _ALLOWED_BINOP[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_UNARY:
            raise ValueError("unsupported unary")
        return _ALLOWED_UNARY[op_type](_eval_node(node.operand))
    raise ValueError("unsupported expression")


def _format_number(value):
    """Tidy output: whole numbers without .0, fractions to 4 places."""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{round(value, 4):g}"
    return str(value)


def _strip_triggers(low):
    for trigger in TRIGGERS:
        if low.startswith(trigger):
            return low[len(trigger):].strip(" ,:")
    return low


_PERCENT_RE = re.compile(
    r"(-?\d+(?:[.,]\d+)?)\s*(?:%|процент(?:а|ов)?|percent)\s*(?:от|of)\s*"
    r"(-?\d+(?:[.,]\d+)?)")


def _percent_of(expr):
    """"20 процентов от 3000" / "20% от 3000" -> (value, match)."""
    m = _PERCENT_RE.search(expr)
    if not m:
        return None, None
    part = float(m.group(1).replace(",", "."))
    whole = float(m.group(2).replace(",", "."))
    return part / 100.0 * whole, m


# Verb constructions: the link between the operands depends on the verb.
# "раздели 100 на 5" is division, although "на" in other phrases means
# multiplication.
VERB_PATTERNS = [
    (r"^(?:раздели(?:ть)?|подели(?:ть)?)\s+(.+?)\s+на\s+(.+)$", "({0})/({1})"),
    (r"^(?:умнож(?:ь|ить))\s+(.+?)\s+на\s+(.+)$", "({0})*({1})"),
    (r"^(?:прибав(?:ь|ить)|сложи|сложить)\s+(.+?)\s+(?:к|и)\s+(.+)$", "({0})+({1})"),
    (r"^(?:отними|отнять|вычти|вычесть)\s+(.+?)\s+(?:от|из)\s+(.+)$", "({1})-({0})"),
]


def _verb_expression(low):
    """Parses "раздели X на Y" and the like. Returns an expression or None."""
    for pattern, template in VERB_PATTERNS:
        m = re.match(pattern, low)
        if m:
            left, right = m.group(1).strip(), m.group(2).strip()
            if re.search(r"\d", left) and re.search(r"\d", right):
                return template.format(left, right)
    return None


def _to_expression(text):
    """Brings a phrase to an arithmetic expression (or None)."""
    low = text.lower().strip()

    expr = _verb_expression(low)
    if expr is None:
        expr = _strip_triggers(low)
    if not expr:
        return None

    for pattern, symbol in WORD_OPS:
        expr = re.sub(pattern, symbol, expr)

    expr = expr.replace("×", "*").replace("÷", "/").replace("^", "**")
    # a decimal comma: "3,5" -> "3.5" (but not a list separator)
    expr = re.sub(r"(\d),(\d)", r"\1.\2", expr)
    expr = expr.replace("=", " ").replace("?", " ")
    expr = re.sub(r"[^0-9+\-*/%().\s]", " ", expr)
    expr = re.sub(r"\s+", " ", expr).strip()
    # "умножь 7 на 6" turns into "* 7 * 6" — the leading operator is superfluous
    expr = re.sub(r"^[*/%]+\s*", "", expr).strip()
    return expr or None


def classify(text):
    """
    A pure parse: ("calc", {"result": ...}), or ("calc.zero_division", {}),
    or None. Performs nothing and writes nothing.

    Separated from try_calculate for the router's sake (4.0-B02): that needs
    an intent with arguments, not a ready-made phrase to speak.
    """
    if not text:
        return None
    low = text.lower().strip()
    has_trigger = any(low.startswith(t) for t in TRIGGERS)

    percent, match = _percent_of(low)
    if percent is not None:
        rest = low[:match.start()] + " " + low[match.end():]
        rest = re.sub(r"[^\w]+", " ", rest).strip()
        if has_trigger or not rest:
            return "calc", {"result": _format_number(percent)}

    expr = _to_expression(text)
    if not expr:
        return None
    if not has_trigger and not re.fullmatch(r"[\d\s+\-*/%().]+", low):
        return None
    if not re.search(r"\d", expr) or not re.search(r"[+\-*/%]", expr):
        return None

    try:
        result = _eval_node(ast.parse(expr, mode="eval"))
    except ZeroDivisionError:
        return "calc.zero_division", {}
    except Exception:
        return None

    if isinstance(result, complex):
        return None
    return "calc", {"result": _format_number(result)}


def try_calculate(text):
    """
    Returns the text of an answer if the phrase is arithmetic, otherwise
    None.
    """
    if not text:
        return None
    low = text.lower().strip()
    has_trigger = any(low.startswith(t) for t in TRIGGERS)

    # A percentage of a number — before the general parse, but by the same
    # admission rules: either the phrase was explicitly addressed to
    # arithmetic, or it is nothing but that expression. Otherwise an
    # ordinary line "скинули 20 процентов от 3000, беру" was intercepted by
    # arithmetic instead of being answered on its merits.
    percent, match = _percent_of(low)
    if percent is not None:
        rest = low[:match.start()] + " " + low[match.end():]
        rest = re.sub(r"[^\w]+", " ", rest).strip()
        if has_trigger or not rest:
            return tr("Получается {result}.",
                      result=_format_number(percent))

    expr = _to_expression(text)
    if not expr:
        return None

    # without an explicit trigger we compute only a "bare" expression of the
    # form 2+2, or any phrase with numbers would turn into arithmetic
    if not has_trigger and not re.fullmatch(r"[\d\s+\-*/%().]+", low):
        return None
    if not re.search(r"\d", expr) or not re.search(r"[+\-*/%]", expr):
        return None

    try:
        tree = ast.parse(expr, mode="eval")
        result = _eval_node(tree)
    except ZeroDivisionError:
        return tr("На ноль делить нельзя.")
    except Exception:
        return None

    if isinstance(result, complex):
        return None
    return tr("Получается {result}.", result=_format_number(result))
