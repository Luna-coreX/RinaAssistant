"""
Калькулятор для голосовых и текстовых команд.

Понимает «посчитай 15*12», «сколько будет 2+2», «20 процентов от 3000»,
а также словесные операторы («умножь 7 на 6»), потому что распознавание речи
почти никогда не выдаёт символы «*» и «/».

Вычисление идёт по разобранному дереву выражения (ast) с белым списком узлов —
eval() на строке из микрофона использовать нельзя.
"""

import ast
import operator
import re

from core.i18n import t as tr


# команда считается «про счёт», если начинается с одного из этих слов
# (глаголы-действия тоже: «умножь 7 на 6» — это запрос на вычисление)
TRIGGERS = (
    "посчитай", "подсчитай", "вычисли", "сколько будет", "чему равно",
    "умножить", "умножь", "разделить", "раздели", "поделить", "подели",
    "прибавь", "прибавить", "отними", "отнять", "вычти", "вычесть", "сложи",
    "calculate", "compute", "how much is", "what is",
)

# Словесные операторы -> символы (речь не даёт знаков арифметики).
# Порядок важен: составные обороты идут первыми, иначе «разделить на»
# распадётся на «разделить» + отдельное «на» и выражение сломается.
WORD_OPS = [
    # составные
    (r"\bразделить на\b", "/"), (r"\bподелить на\b", "/"),
    (r"\bумножить на\b", "*"), (r"\bумножь на\b", "*"),
    (r"\bdivided by\b", "/"), (r"\bmultiplied by\b", "*"),
    (r"\bв степени\b", "**"), (r"\bв квадрате\b", "**2"),
    # одиночные
    (r"\bплюс\b", "+"), (r"\bприбавить\b", "+"), (r"\bсложить\b", "+"),
    (r"\bминус\b", "-"), (r"\bотнять\b", "-"), (r"\bвычесть\b", "-"),
    (r"\bумножить\b", "*"), (r"\bумножь\b", "*"),
    (r"\bразделить\b", "/"), (r"\bподелить\b", "/"),
    (r"\bplus\b", "+"), (r"\bminus\b", "-"), (r"\btimes\b", "*"),
    # «на» как умножение — только последним, когда прочие обороты разобраны
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

MAX_POWER = 64          # защита от 9**99999999 (зависание/память)


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
    """Аккуратный вывод: целые — без .0, дробные — до 4 знаков."""
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


def _percent_of(expr):
    """«20 процентов от 3000» / «20% от 3000» -> 20/100*3000."""
    m = re.search(
        r"(-?\d+(?:[.,]\d+)?)\s*(?:%|процент(?:а|ов)?|percent)\s*(?:от|of)\s*"
        r"(-?\d+(?:[.,]\d+)?)", expr)
    if not m:
        return None
    part = float(m.group(1).replace(",", "."))
    whole = float(m.group(2).replace(",", "."))
    return part / 100.0 * whole


# Глагольные конструкции: связка между операндами зависит от глагола.
# «раздели 100 на 5» — это деление, хотя «на» в других фразах значит умножение.
VERB_PATTERNS = [
    (r"^(?:раздели(?:ть)?|подели(?:ть)?)\s+(.+?)\s+на\s+(.+)$", "({0})/({1})"),
    (r"^(?:умнож(?:ь|ить))\s+(.+?)\s+на\s+(.+)$", "({0})*({1})"),
    (r"^(?:прибав(?:ь|ить)|сложи|сложить)\s+(.+?)\s+(?:к|и)\s+(.+)$", "({0})+({1})"),
    (r"^(?:отними|отнять|вычти|вычесть)\s+(.+?)\s+(?:от|из)\s+(.+)$", "({1})-({0})"),
]


def _verb_expression(low):
    """Разбирает «раздели X на Y» и подобное. Возвращает выражение или None."""
    for pattern, template in VERB_PATTERNS:
        m = re.match(pattern, low)
        if m:
            left, right = m.group(1).strip(), m.group(2).strip()
            if re.search(r"\d", left) and re.search(r"\d", right):
                return template.format(left, right)
    return None


def _to_expression(text):
    """Приводит фразу к арифметическому выражению (или None)."""
    low = text.lower().strip()

    expr = _verb_expression(low)
    if expr is None:
        expr = _strip_triggers(low)
    if not expr:
        return None

    for pattern, symbol in WORD_OPS:
        expr = re.sub(pattern, symbol, expr)

    expr = expr.replace("×", "*").replace("÷", "/").replace("^", "**")
    # десятичная запятая: «3,5» -> «3.5» (но не разделитель перечисления)
    expr = re.sub(r"(\d),(\d)", r"\1.\2", expr)
    expr = expr.replace("=", " ").replace("?", " ")
    expr = re.sub(r"[^0-9+\-*/%().\s]", " ", expr)
    expr = re.sub(r"\s+", " ", expr).strip()
    # «умножь 7 на 6» превращается в «* 7 * 6» — ведущий оператор лишний
    expr = re.sub(r"^[*/%]+\s*", "", expr).strip()
    return expr or None


def try_calculate(text):
    """
    Возвращает текст ответа, если фраза — арифметика, иначе None.
    """
    if not text:
        return None
    low = text.lower().strip()
    has_trigger = any(low.startswith(t) for t in TRIGGERS)

    # процент от числа — считаем до общего разбора
    percent = _percent_of(low)
    if percent is not None:
        return tr("Получается {result}.", result=_format_number(percent))

    expr = _to_expression(text)
    if not expr:
        return None

    # без явного триггера считаем только «голое» выражение вида 2+2,
    # иначе любая фраза с числами превращалась бы в арифметику
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
