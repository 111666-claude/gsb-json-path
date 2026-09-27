"""JSONPath 子集求值。只用标准库。缺陷：递归下降只走一层、结果被重排、过滤器只判存在。"""

import json


class JsonPathError(ValueError):
    """查询语法不合法。缺陷：不带列号。"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def tokenize(query):
    """把查询拆成 token。缺陷：出错不给列号。"""
    if not query.startswith("$"):
        raise JsonPathError("查询必须以 $ 开头：%s" % query)
    tokens = []
    index = 1
    while index < len(query):
        if query.startswith("..", index):
            index += 2
            start = index
            while index < len(query) and (query[index].isalnum() or query[index] == "_"):
                index += 1
            if start == index:
                raise JsonPathError(".. 后面缺少字段名")
            tokens.append(("descend", query[start:index]))
        elif query[index] == ".":
            index += 1
            start = index
            while index < len(query) and (query[index].isalnum() or query[index] == "_"):
                index += 1
            if start == index:
                raise JsonPathError(". 后面缺少字段名")
            tokens.append(("key", query[start:index]))
        elif query[index] == "[":
            end = query.find("]", index)
            if end < 0:
                raise JsonPathError("方括号没有闭合")
            tokens.append(_bracket_token(query[index + 1:end].strip()))
            index = end + 1
        else:
            raise JsonPathError("看不懂的字符：%r" % query[index])
    return tokens


def _bracket_token(inner):
    if inner == "*":
        return ("wildcard",)
    if inner.startswith("?(") and inner.endswith(")"):
        return ("filter", inner[2:-1].strip())
    if len(inner) >= 2 and inner.startswith("'") and inner.endswith("'"):
        return ("key", inner[1:-1])
    if inner and inner.lstrip("-").isdigit():
        return ("index", int(inner))
    raise JsonPathError("方括号内容看不懂：%s" % inner)


def _children(node):
    if isinstance(node, dict):
        return list(node.values())
    if isinstance(node, list):
        return list(node)
    return []


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
        # 缺陷：只认列表，对象直接被跳过
        return list(node) if isinstance(node, list) else []
    if kind == "descend":
        # 缺陷：只在当前节点和它的直接子节点里找，不再往下递归
        hits = []
        if isinstance(node, dict) and token[1] in node:
            hits.append(node[token[1]])
        for child in _children(node):
            if isinstance(child, dict) and token[1] in child:
                hits.append(child[token[1]])
        return hits
    if kind == "filter":
        field, _, rest = token[1].partition(".")
        if field != "@" or not rest.isidentifier():
            raise JsonPathError("过滤器只支持 @.字段 的存在性判断")
        return [item for item in _children(node) if isinstance(item, dict) and rest in item]
    raise JsonPathError("未知 token：%r" % (token,))


def evaluate(document, query):
    """缺陷：结果按 JSON 文本排序，文档顺序全丢了。"""
    current = [document]
    for token in tokenize(query):
        nxt = []
        for node in current:
            nxt.extend(_apply(node, token))
        current = nxt
    return sorted(current, key=lambda item: json.dumps(item, sort_keys=True))
