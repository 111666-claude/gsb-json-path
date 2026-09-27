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

    def test_error_column_must_start_with_dollar(self):
        with self.assertRaises(JsonPathError) as caught:
            tokenize("a.b")
        self.assertEqual(caught.exception.column, 1)
        self.assertIn("1", str(caught.exception))

    def test_error_column_unclosed_bracket(self):
        with self.assertRaises(JsonPathError) as caught:
            tokenize("$.a[0")
        self.assertEqual(caught.exception.column, 4)
        self.assertIn("4", str(caught.exception))

    def test_error_column_dot_without_name(self):
        with self.assertRaises(JsonPathError) as caught:
            tokenize("$.a.")
        self.assertEqual(caught.exception.column, 5)
        self.assertIn("5", str(caught.exception))

    def test_error_column_descend_without_name(self):
        with self.assertRaises(JsonPathError) as caught:
            tokenize("$..")
        self.assertIsNotNone(caught.exception.column)

    def test_filter_token(self):
        self.assertEqual(
            tokenize("$.items[?(@.n > 1)]"),
            [("key", "items"), ("filter", "n", ">", 1)],
        )


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

    def test_wildcard_on_object(self):
        self.assertEqual(evaluate({"a": 1, "b": 2}, "$[*]"), [1, 2])

    def test_wildcard_on_scalar(self):
        self.assertEqual(evaluate(5, "$[*]"), [])

    def test_descend_any_depth(self):
        document = {"a": {"b": {"price": 1}}, "price": 2}
        self.assertEqual(evaluate(document, "$..price"), [1, 2])

    def test_descend_preorder_insertion_order(self):
        document = {"x": {"price": 1, "y": {"price": 2}}, "price": 3}
        self.assertEqual(evaluate(document, "$..price"), [1, 2, 3])

    def test_descend_keeps_duplicates(self):
        document = {"n": {"n": 1}}
        self.assertEqual(evaluate(document, "$..n"), [{"n": 1}, 1])

    def test_descend_through_lists(self):
        document = [{"price": 1}, [{"price": 2}]]
        self.assertEqual(evaluate(document, "$..price"), [1, 2])

    def test_results_in_document_order(self):
        document = {"items": [{"id": "b"}, {"id": "a"}]}
        self.assertEqual(evaluate(document, "$.items[*].id"), ["b", "a"])

    def test_filter_on_existing_field(self):
        document = {"items": [{"n": 1}, {"x": 2}]}
        self.assertEqual(evaluate(document, "$.items[?(@.n)]"), [{"n": 1}])

    def test_filter_gt_number(self):
        document = [{"n": 1}, {"n": 2}, {"n": 3}]
        self.assertEqual(evaluate(document, "$[?(@.n > 1)]"), [{"n": 2}, {"n": 3}])

    def test_filter_lt_number(self):
        document = [{"n": 1}, {"n": 2}, {"n": 3}]
        self.assertEqual(evaluate(document, "$[?(@.n < 3)]"), [{"n": 1}, {"n": 2}])

    def test_filter_eq_and_ne(self):
        document = [{"n": 1}, {"n": 2}]
        self.assertEqual(evaluate(document, "$[?(@.n == 1)]"), [{"n": 1}])
        self.assertEqual(evaluate(document, "$[?(@.n != 1)]"), [{"n": 2}])

    def test_filter_string_literal(self):
        document = [{"id": "a"}, {"id": "b"}]
        self.assertEqual(evaluate(document, "$[?(@.id == 'a')]"), [{"id": "a"}])
        self.assertEqual(evaluate(document, "$[?(@.id != 'a')]"), [{"id": "b"}])

    def test_filter_missing_field_is_false(self):
        document = [{"n": 2}, {"x": 3}]
        self.assertEqual(evaluate(document, "$[?(@.n > 1)]"), [{"n": 2}])

    def test_filter_type_mismatch_is_false(self):
        document = [{"n": "2"}, {"n": 2}, {"n": True}]
        self.assertEqual(evaluate(document, "$[?(@.n > 1)]"), [{"n": 2}])
        self.assertEqual(evaluate(document, "$[?(@.n != 1)]"), [{"n": 2}])
        self.assertEqual(evaluate([{"n": "2"}, {"n": True}], "$[?(@.n != 1)]"), [])

    def test_filter_unknown_syntax_raises(self):
        with self.assertRaises(JsonPathError):
            evaluate([], "$[?(1 + 1)]")
        with self.assertRaises(JsonPathError):
            evaluate([], "$[?(@.n >= 1)]")
        with self.assertRaises(JsonPathError):
            evaluate([], "$[?(@.n == x)]")

    def test_evaluation_is_deterministic(self):
        document = {"a": {"b": {"price": 1}}, "price": 2}
        self.assertEqual(
            evaluate(document, "$..price"), evaluate(document, "$..price")
        )

    def test_document_is_not_modified(self):
        document = {"a": [{"b": 1}]}
        before = copy.deepcopy(document)
        evaluate(document, "$.a[*]")
        self.assertEqual(document, before)

    def test_document_is_not_modified_by_descend_and_filter(self):
        document = {"a": [{"n": 1}, {"n": 2}], "n": 0}
        before = copy.deepcopy(document)
        evaluate(document, "$..n")
        evaluate(document, "$.a[?(@.n > 1)]")
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
