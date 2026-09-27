"""JSONPath 子集求值。只用标准库。

支持：$、.name、['name']、[0]、[*]、..name、[?(...)]。
结果按文档顺序给出，允许重复，不去重；求值不修改文档。
"""

import re


class JsonPathError(ValueError):
    """查询语法不合法，带列号（1 起）。"""

    def __init__(self, message, column=None):
        self.column = column
        if column is not None:
            message = "%s（第 %d 列）" % (message, column)
        super().__init__(message)
        self.message = message


def tokenize(query):
    """把查询拆成 token，语法错误抛出带列号的 JsonPathError。"""
    if not query.startswith("$"):
        raise JsonPathError("查询必须以 $ 开头", 1)
    tokens = []
    index = 1
    while index < len(query):
        if query.startswith("..", index):
            index += 2
            start = index
            while index < len(query) and (query[index].isalnum() or query[index] == "_"):
                index += 1
            if start == index:
                raise JsonPathError(".. 后面缺少字段名", index + 1)
            tokens.append(("descend", query[start:index]))
        elif query[index] == ".":
            index += 1
            start = index
            while index < len(query) and (query[index].isalnum() or query[index] == "_"):
                index += 1
            if start == index:
                raise JsonPathError(". 后面缺少字段名", index + 1)
            tokens.append(("key", query[start:index]))
        elif query[index] == "[":
            end = query.find("]", index)
            if end < 0:
                raise JsonPathError("方括号没有闭合", index + 1)
            tokens.append(_bracket_token(query[index + 1:end].strip(), index + 1))
            index = end + 1
        else:
            raise JsonPathError("看不懂的字符：%r" % query[index], index + 1)
    return tokens


_FILTER_RE = re.compile(r"^@\.([A-Za-z_][A-Za-z0-9_]*)\s*(?:(==|!=|>|<)\s*(.+?)\s*)?$")


def _parse_filter(expr, column):
    match = _FILTER_RE.match(expr)
    if not match:
        raise JsonPathError("过滤器语法看不懂：%s" % expr, column)
    field, op, raw = match.groups()
    if op is None:
        return ("filter", field, None, None)
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        literal = raw[1:-1]
    else:
        try:
            literal = int(raw)
        except ValueError:
            try:
                literal = float(raw)
            except ValueError:
                raise JsonPathError("过滤器字面量只支持数字或字符串：%s" % raw, column)
    return ("filter", field, op, literal)


def _bracket_token(inner, column):
    if inner == "*":
        return ("wildcard",)
    if inner.startswith("?(") and inner.endswith(")"):
        return _parse_filter(inner[2:-1].strip(), column)
    if len(inner) >= 2 and inner.startswith("'") and inner.endswith("'"):
        return ("key", inner[1:-1])
    if inner and inner.lstrip("-").isdigit():
        return ("index", int(inner))
    raise JsonPathError("方括号内容看不懂：%s" % inner, column)


def _children(node):
    if isinstance(node, dict):
        return list(node.values())
    if isinstance(node, list):
        return list(node)
    return []


def _descend(node, name):
    """先序递归下降：子节点按键的插入序处理，先判当前子节点是否命中，再进它的子节点。"""
    hits = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == name:
                hits.append(value)
            hits.extend(_descend(value, name))
    elif isinstance(node, list):
        for item in node:
            hits.extend(_descend(item, name))
    return hits


def _filter_match(item, field, op, literal):
    if not isinstance(item, dict) or field not in item:
        return False
    if op is None:
        return True
    value = item[field]
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)) and isinstance(literal, (int, float)):
        pass
    elif isinstance(value, str) and isinstance(literal, str):
        pass
    else:
        return False
    if op == ">":
        return value > literal
    if op == "<":
        return value < literal
    if op == "==":
        return value == literal
    return value != literal


def _apply(node, token):
    kind = token[0]
    if kind == "key":
        if isinstance(node, dict) and token[1] in node:
            return [node[token[1]]]
        return []
    if kind == "index":
        position = token[1]
        if isinstance(node, list) and -len(node) <= position < len(node):
            return [node[position]]
        return []
    if kind == "wildcard":
        if isinstance(node, dict):
            return list(node.values())
        if isinstance(node, list):
            return list(node)
        return []
    if kind == "descend":
        return _descend(node, token[1])
    if kind == "filter":
        _, field, op, literal = token
        return [item for item in _children(node) if _filter_match(item, field, op, literal)]
    raise JsonPathError("未知 token：%r" % (token,))


def evaluate(document, query):
    """按文档顺序求值，不排序、不去重、不修改文档。"""
    current = [document]
    for token in tokenize(query):
        nxt = []
        for node in current:
            nxt.extend(_apply(node, token))
        current = nxt
    return current
