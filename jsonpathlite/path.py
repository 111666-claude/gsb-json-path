"""JSONPath 子集求值：递归下降、通配符、过滤器。

只用标准库；求值过程只读取文档，不复制、不修改任何节点。
"""

_MISSING = object()


class JsonPathError(ValueError):
    """查询语法不合法。column 为 1 基列号，无法定位时为 None。"""

    def __init__(self, message, column=None):
        self.message = message
        self.column = column
        if column is not None:
            message = "第 %d 列：%s" % (column, message)
        super().__init__(message)


def tokenize(query):
    """把查询拆成 token，任何语法错误都带列号抛出 JsonPathError。"""
    if not isinstance(query, str) or not query.startswith("$"):
        raise JsonPathError("查询必须以 $ 开头", 1)
    tokens = []
    pos = 1
    while pos < len(query):
        ch = query[pos]
        if ch == ".":
            recursive = query.startswith("..", pos)
            pos += 2 if recursive else 1
            name, pos = _read_name(query, pos)
            tokens.append(("descend", name) if recursive else ("key", name))
        elif ch == "[":
            token, pos = _read_bracket(query, pos)
            tokens.append(token)
        else:
            raise JsonPathError("看不懂的字符 %r" % ch, pos + 1)
    return tokens


def _read_name(query, pos):
    start = pos
    while pos < len(query) and (query[pos].isalnum() or query[pos] == "_"):
        pos += 1
    if start == pos:
        raise JsonPathError("点号后面缺少字段名", pos + 1)
    return query[start:pos], pos


def _skip_ws(text, pos):
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def _read_bracket(query, pos):
    """读取从 pos 处的 [ 到配对 ] 的内容，引号内的 ] 不作为结束。"""
    column = pos + 1
    inner_start = pos + 1
    scan = inner_start
    quote = None
    while scan < len(query):
        ch = query[scan]
        if quote is not None:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "]":
            token = _parse_bracket(query[inner_start:scan], inner_start, column)
            return token, scan + 1
        scan += 1
    raise JsonPathError("方括号没有闭合", column)


def _parse_bracket(inner, base, bracket_column):
    """base 是 inner 第一个字符在整条查询中的 0 基位置。"""
    stripped = inner.strip()
    if not stripped:
        raise JsonPathError("方括号里不能为空", bracket_column)
    offset = len(inner) - len(inner.lstrip())

    def column(index):
        return base + offset + index + 1

    if stripped == "*":
        return ("wildcard",)
    if stripped.startswith("?(") and stripped.endswith(")"):
        middle = stripped[2:-1]
        expr = middle.strip()
        expr_column = column(2 + (len(middle) - len(middle.lstrip())))
        return ("filter", _parse_filter(expr, expr_column))
    if len(stripped) >= 2 and stripped[0] in "'\"" and stripped[-1] == stripped[0]:
        return ("key", stripped[1:-1])
    if _is_integer(stripped):
        return ("index", int(stripped))
    raise JsonPathError("方括号内容看不懂：%s" % stripped, bracket_column)


def _is_integer(text):
    body = text[1:] if text.startswith("-") else text
    return bool(body) and body.isdigit()


def _parse_filter(expr, col0):
    """解析过滤器表达式。col0 是 expr[0] 在整条查询中的 1 基列号。"""
    pos = _skip_ws(expr, 0)
    if pos >= len(expr) or expr[pos] != "@":
        raise JsonPathError("过滤器必须以 @.字段 开头", col0 + pos)
    pos = _skip_ws(expr, pos + 1)
    if pos >= len(expr) or expr[pos] != ".":
        raise JsonPathError("过滤器里 @ 后面应当是 .字段", col0 + min(pos, len(expr)))
    pos += 1
    name_start = pos
    while pos < len(expr) and (expr[pos].isalnum() or expr[pos] == "_"):
        pos += 1
    if name_start == pos:
        raise JsonPathError("过滤器缺少字段名", col0 + pos)
    name = expr[name_start:pos]

    pos = _skip_ws(expr, pos)
    if pos == len(expr):
        return ("exists", name)

    for operator in ("==", "!=", ">", "<"):
        if expr.startswith(operator, pos):
            break
    else:
        raise JsonPathError("过滤器只支持 >、<、==、!= 比较", col0 + pos)
    pos = _skip_ws(expr, pos + len(operator))

    literal, pos = _read_literal(expr, pos, col0)
    pos = _skip_ws(expr, pos)
    if pos != len(expr):
        raise JsonPathError("过滤器后缀无法识别", col0 + pos)
    return ("compare", name, operator, literal)


def _read_literal(expr, pos, col0):
    if pos >= len(expr):
        raise JsonPathError("过滤器比较缺少右值", col0 + pos)
    if expr[pos] in "'\"":
        quote = expr[pos]
        end = expr.find(quote, pos + 1)
        if end < 0:
            raise JsonPathError("过滤器字符串没有闭合", col0 + pos)
        return expr[pos + 1:end], end + 1

    start = pos
    if expr[pos] == "-":
        pos += 1
    digits_start = pos
    while pos < len(expr) and expr[pos].isdigit():
        pos += 1
    if pos == digits_start:
        raise JsonPathError("过滤器只支持数字或字符串字面量", col0 + start)
    is_float = False
    if pos < len(expr) and expr[pos] == ".":
        is_float = True
        pos += 1
        fraction_start = pos
        while pos < len(expr) and expr[pos].isdigit():
            pos += 1
        if pos == fraction_start:
            raise JsonPathError("数字字面量格式不正确", col0 + start)
    if pos < len(expr) and expr[pos] in "eE":
        exponent_end = pos + 1
        if exponent_end < len(expr) and expr[exponent_end] in "+-":
            exponent_end += 1
        exponent_digits = exponent_end
        while exponent_end < len(expr) and expr[exponent_end].isdigit():
            exponent_end += 1
        if exponent_end == exponent_digits:
            raise JsonPathError("数字字面量格式不正确", col0 + start)
        is_float = True
        pos = exponent_end

    raw = expr[start:pos]
    return (float(raw) if is_float else int(raw)), pos


def _iter_children(node):
    if isinstance(node, dict):
        return node.values()
    if isinstance(node, list):
        return node
    return ()


def _descend(root, name, out):
    """先序收集任意深度下键名为 name 的值。

    迭代栈实现（避免深文档触发递归上限）；展开子节点时按插入序逆序压栈，
    弹出顺序即插入序；命中的节点仍继续向下走，与先序语义一致。
    """
    stack = [(root, None)]
    while stack:
        value, key = stack.pop()
        if key == name:
            out.append(value)
        if isinstance(value, dict):
            items = list(value.items())
            for index in range(len(items) - 1, -1, -1):
                child_key, child_value = items[index]
                stack.append((child_value, child_key))
        elif isinstance(node_list_safe(value)):
            for index in range(len(value) - 1, -1, -1):
                stack.append((value[index], None))


def node_list_safe(value):
    return value if isinstance(value, list) else ()


def _match_filter(item, expr):
    if not isinstance(item, dict) or expr[1] not in item:
        return False
    name = expr[1]
    if expr[0] == "exists":
        return True

    operator, literal = expr[2], expr[3]
    value = item[name]
    if isinstance(literal, str):
        if not isinstance(value, str):
            return False
    else:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False

    if operator == "==":
        return value == literal
    if operator == "!=":
        return value != literal
    if operator == ">":
        return value > literal
    return value < literal


def _collect(node, token, out):
    kind = token[0]
    if kind == "key":
        if isinstance(node, dict):
            value = node.get(token[1], _MISSING)
            if value is not _MISSING:
                out.append(value)
    elif kind == "index":
        position = token[1]
        if isinstance(node, list) and -len(node) <= position < len(node):
            out.append(node[position])
    elif kind == "wildcard":
        out.extend(_iter_children(node))
    elif kind == "descend":
        _descend(node, token[1], out)
    elif kind == "filter":
        for item in _iter_children(node):
            if _match_filter(item, token[1]):
                out.append(item)
    else:
        raise JsonPathError("未知 token：%r" % (token,))


def evaluate(document, query):
    """按查询求值，结果严格按文档顺序返回，不去重、不排序、不复制文档。"""
    current = [document]
    for token in tokenize(query):
        nxt = []
        for node in current:
            _collect(node, token, nxt)
        current = nxt
    return current
