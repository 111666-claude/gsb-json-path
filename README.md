# json-path

JSONPath 子集求值（递归下降、通配符、过滤器），只用 Python 标准库。

```
python3 -m jsonpathlite.cli --json '{"a":{"b":{"price":1}},"price":2}' --query '$..price'
python3 -m jsonpathlite.cli --json '{"items":[{"id":"b"},{"id":"a"}]}' --query '$.items[*].id'
python3 -m unittest discover -s tests -v
```

## 口径（README 为准）

- **递归下降要走到任意深度**：`$..price` 在 `{"a":{"b":{"price":1}},"price":2}` 上按口径是 `[1, 2]`
  （先序：当前节点先、再按插入序进子节点），现在只在当前层和直接子节点找，给 `[2]`。
- **结果按文档顺序**：不许排序。`{"items":[{"id":"b"},{"id":"a"}]}` 配 `$.items[*].id` 按口径是 `["b", "a"]`，
  现在按 JSON 文本排序后给 `["a", "b"]`。
- **通配符**：`[*]` 对列表给全部元素，对对象给全部值（按插入序）。现在对对象直接给空。
- **过滤器**：`[?(...)]` 支持 `@.字段` 的存在性，以及和数字/字符串字面量的 `>`、`<`、`==`、`!=`；
  字段缺失或两边类型不同判为 false。现在除了存在性之外一律报错。
- 支持的语法：`$`、`.name`、`['name']`、`[0]`、`[*]`、`..name`、`[?(...)]`；结果允许重复，不去重。
- 不变量：求值不修改文档；同一文档与查询重复求值结果相同。
- 错误：查询不以 `$` 开头、方括号不闭合、点后面缺字段名都要报错并带列号；字段不存在给空数组，不算错误。
- 规模：1 MB 的 JSON、10 万元素数组，求值时间与节点数、结果数成正比，不许 deepcopy 整份文档。
- 对照自证：与「手写递归遍历」的参考实现比对随机 200 组文档与查询，差异必须为 0。

## 现在的行为

- `descend` token 只看当前节点和它的直接子节点：`$..price` 在嵌套两层以上时漏结果。
- `evaluate` 最后 `sorted(..., key=json.dumps)`：文档顺序全丢，`$.items[*].id` 给 `["a","b"]`。
- `wildcard` token 只认列表，对象给空。
- `filter` token 只认 `@.字段`，`@.n > 1` 直接抛 `JsonPathError`。

## 计划新增的能力

```
--json 文本     JSON 文本
--file 文件     从文件读 JSON
--query 查询    例如 $..price
```

## 输出

```
[1, 2]
```

## 目录

```
jsonpathlite/path.py   token 化与求值
jsonpathlite/cli.py    命令行入口
tests/                 unittest 用例
```
