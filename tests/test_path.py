import copy
import io
import unittest
from contextlib import redirect_stdout

from jsonpathlite.cli import main
from jsonpathlite.path import JsonPathError, evaluate, tokenize


class TokenizeTest(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(tokenize("$.a.b"), [("key", "a"), ("key", "b")])

    def test_index_and_wildcard(self):
        self.assertEqual(tokenize("$[0][*]"), [("index", 0), ("wildcard",)])

    def test_quoted_key(self):
        self.assertEqual(tokenize("$['a b']"), [("key", "a b")])

    def test_must_start_with_dollar(self):
        with self.assertRaises(JsonPathError):
            tokenize("$.a".lstrip("$"))

    def test_unclosed_bracket(self):
        with self.assertRaises(JsonPathError):
            tokenize("$[0")


class EvaluateTest(unittest.TestCase):
    def test_key(self):
        self.assertEqual(evaluate({"a": 1}, "$.a"), [1])

    def test_missing_key(self):
        self.assertEqual(evaluate({"a": 1}, "$.b"), [])

    def test_index(self):
        self.assertEqual(evaluate({"a": [7, 8]}, "$.a[1]"), [8])

    def test_index_out_of_range(self):
        self.assertEqual(evaluate({"a": [7]}, "$.a[3]"), [])

    def test_wildcard_on_list(self):
        self.assertEqual(evaluate([1, 2], "$[*]"), [1, 2])

    def test_filter_on_existing_field(self):
        document = {"items": [{"n": 1}, {"x": 2}]}
        self.assertEqual(evaluate(document, "$.items[?(@.n)]"), [{"n": 1}])

    def test_document_is_not_modified(self):
        document = {"a": [{"b": 1}]}
        before = copy.deepcopy(document)
        evaluate(document, "$.a[*]")
        self.assertEqual(document, before)


class CliTest(unittest.TestCase):
    def test_prints_array(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["--json", '{"a": 1}', "--query", "$.a"])
        self.assertEqual(code, 0)
        self.assertEqual(buffer.getvalue().strip(), "[1]")

    def test_missing_query(self):
        self.assertEqual(main(["--json", "{}"]), 2)


if __name__ == "__main__":
    unittest.main()
