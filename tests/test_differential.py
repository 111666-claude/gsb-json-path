"""与「手写递归遍历」参考实现比对：随机 200 组文档与查询，差异必须为 0。"""

import random
import re
import unittest

from jsonpathlite.path import evaluate

KEYS = ["a", "b", "price", "id", "n", "name"]
SCALARS = [0, 1, 2, 7, "x", "y", "hello", True, None]


def random_document(rng, depth):
    if depth <= 0:
        return rng.choice(SCALARS)
    roll = rng.random()
    if roll < 0.4:
        keys = rng.sample(KEYS, rng.randint(0, 3))
        return {key: random_document(rng, depth - 1) for key in keys}
    if roll < 0.7:
        return [random_document(rng, depth - 1) for _ in range(rng.randint(0, 3))]
    return rng.choice(SCALARS)


def random_query(rng):
    parts = ["$"]
    for _ in range(rng.randint(1, 4)):
        roll = rng.random()
        if roll < 0.30:
            parts.append("." + rng.choice(KEYS))
        elif roll < 0.45:
            parts.append("[*]")
        elif roll < 0.60:
            parts.append(".." + rng.choice(KEYS))
        elif roll < 0.70:
            parts.append("[0]")
        elif roll < 0.80:
            parts.append("[?(@.%s)]" % rng.choice(KEYS))
        elif roll < 0.90:
            parts.append(
                "[?(@.%s %s %d)]"
                % (rng.choice(KEYS), rng.choice([">", "<", "==", "!="]), rng.randint(0, 3))
            )
        else:
            parts.append(
                "[?(@.%s %s '%s')]"
                % (rng.choice(KEYS), rng.choice(["==", "!="]), rng.choice(["x", "y"]))
            )
    return "".join(parts)


# ---- 手写递归遍历的参考实现（独立实现同一口径） ----


def _ref_children(node):
    if isinstance(node, dict):
        return list(node.values())
    if isinstance(node, list):
        return list(node)
    return []


def _ref_descend(node, name):
    hits = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == name:
                hits.append(value)
            hits.extend(_ref_descend(value, name))
    elif isinstance(node, list):
        for item in node:
            hits.extend(_ref_descend(item, name))
    return hits


def _ref_literal(raw):
    raw = raw.strip()
    if raw.startswith("'"):
        return raw[1:-1]
    return int(raw)


def _ref_match(item, expr):
    match = re.match(r"^@\.(\w+)\s*(?:(==|!=|>|<)\s*(.+?)\s*)?$", expr)
    field, op, raw = match.group(1), match.group(2), match.group(3)
    if not isinstance(item, dict) or field not in item:
        return False
    if op is None:
        return True
    value = item[field]
    if isinstance(value, bool):
        return False
    literal = _ref_literal(raw)
    if isinstance(value, str) != isinstance(literal, str):
        return False
    if op == ">":
        return value > literal
    if op == "<":
        return value < literal
    if op == "==":
        return value == literal
    return value != literal


def _ref_eval(nodes, query):
    """对查询串做递归下降解析，逐段求值。"""
    if not query:
        return nodes
    if query.startswith(".."):
        end = 2
        while end < len(query) and (query[end].isalnum() or query[end] == "_"):
            end += 1
        name = query[2:end]
        hits = []
        for node in nodes:
            hits.extend(_ref_descend(node, name))
        return _ref_eval(hits, query[end:])
    if query.startswith("."):
        end = 1
        while end < len(query) and (query[end].isalnum() or query[end] == "_"):
            end += 1
        name = query[1:end]
        hits = [node[name] for node in nodes if isinstance(node, dict) and name in node]
        return _ref_eval(hits, query[end:])
    if query.startswith("[*]"):
        hits = []
        for node in nodes:
            hits.extend(_ref_children(node))
        return _ref_eval(hits, query[3:])
    if query.startswith("[0]"):
        hits = [node[0] for node in nodes if isinstance(node, list) and node]
        return _ref_eval(hits, query[3:])
    if query.startswith("[?("):
        end = query.index(")]")
        expr = query[3:end]
        hits = []
        for node in nodes:
            hits.extend(child for child in _ref_children(node) if _ref_match(child, expr))
        return _ref_eval(hits, query[end + 2:])
    raise AssertionError("参考实现不认识的查询：%s" % query)


def reference_evaluate(document, query):
    assert query.startswith("$")
    return _ref_eval([document], query[1:])


class DifferentialTest(unittest.TestCase):
    def test_matches_reference_on_random_inputs(self):
        rng = random.Random(20240914)
        for case in range(200):
            document = random_document(rng, depth=4)
            query = random_query(rng)
            with self.subTest(case=case, query=query):
                self.assertEqual(
                    evaluate(document, query),
                    reference_evaluate(document, query),
                )


if __name__ == "__main__":
    unittest.main()
