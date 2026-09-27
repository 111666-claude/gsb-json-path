"""命令行入口：按查询求值并打印 JSON 数组。"""

import argparse
import json
import sys

from .path import JsonPathError, evaluate


def build_parser():
    parser = argparse.ArgumentParser(prog="json-path", description="JSONPath 子集求值")
    parser.add_argument("--json", dest="text", help="JSON 文本")
    parser.add_argument("--file", help="JSON 文件")
    parser.add_argument("--query", help="查询，例如 $..price")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.query or (args.text is None and not args.file):
        print("错误：需要 --query 以及 --json 或 --file", file=sys.stderr)
        return 2
    try:
        if args.text is not None:
            document = json.loads(args.text)
        else:
            with open(args.file, encoding="utf-8") as handle:
                document = json.load(handle)
        result = evaluate(document, args.query)
    except (JsonPathError, ValueError, OSError) as error:
        print("错误：%s" % error, file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
