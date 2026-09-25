"""signature_extractor JS/TS 类体提取回归（SE4 + 行级签名截断）。"""
from app.agent.signature_extractor import extract_signatures


def test_ts_class_methods_and_modifier_fields_are_extracted():
    """SE4: JS/TS 类方法与带访问修饰符的字段此前完全不提取。"""
    ts = """export class Service {
  private name: string;
  static count: number = 0;
  constructor(name: string) {
    this.name = name;
  }
  run(): void {
    console.log("hi");
  }
  async fetch(id: number): Promise<string> {
    return "";
  }
  get label(): string { return this.name; }
}
"""

    signatures = extract_signatures("service.ts", ts)

    assert signatures is not None
    assert "export class Service {" in signatures
    assert "private name: string;" in signatures
    assert "static count: number = 0;" in signatures
    assert "constructor(name: string)" in signatures
    assert "run(): void" in signatures
    assert "async fetch(id: number): Promise<string>" in signatures
    assert "get label(): string" in signatures


def test_js_method_body_calls_are_not_treated_as_signatures():
    """方法体内的调用/控制流不应进入签名列表。"""
    js = """class Service {
  run() {
    if (this.name) { return 1; }
    for (let i = 0; i < 3; i++) { go(i); }
  }
  count = 0;
}
"""

    signatures = extract_signatures("service.js", js)

    assert signatures is not None
    assert "run()" in signatures
    assert "count = 0;" in signatures
    assert "go(i)" not in signatures
    assert "for (" not in signatures
    assert "if (" not in signatures


def test_js_one_line_methods_are_extracted():
    js = "class S {\n  run() { return 1; }\n  stop() {}\n}\n"

    signatures = extract_signatures("s.js", js)

    assert signatures is not None
    assert "run()" in signatures
    assert "stop()" in signatures
    assert "return 1" not in signatures


def test_signature_ends_at_closing_paren_without_extra_char():
    """行级签名不再多带闭括号后的一个字符，并保留同行返回类型。"""
    ts = "class S {\n  run(): void { return; }\n}\n"

    signatures = extract_signatures("s.ts", ts)

    assert signatures is not None
    assert "run(): void" in signatures
    assert "run() : void" not in signatures


def test_nested_class_does_not_swallow_outer_methods():
    """SE6: 嵌套类覆盖 class_indent 后，外层方法此前被误判为顶层而丢弃。"""
    js = """class Outer {
  name = "outer";
  class Inner {
    id = 1;
    run() {}
  }
  outerMethod() {}
  outerField = 2;
}
"""

    signatures = extract_signatures("nested.js", js)

    assert signatures is not None
    assert "class Outer {" in signatures
    assert 'name = "outer";' in signatures
    assert "class Inner {" in signatures
    assert "id = 1;" in signatures
    assert "run()" in signatures
    # 外层类的方法与字段必须在嵌套类结束后恢复收集
    assert "outerMethod()" in signatures
    assert "outerField = 2;" in signatures


def test_two_sibling_classes_both_keep_their_methods():
    """退出一个类后，下一个同级类的方法归属不受前一个类影响。"""
    js = """class A {
  first() {}
}
class B {
  second() {}
}
"""

    signatures = extract_signatures("siblings.js", js)

    assert signatures is not None
    assert "class A {" in signatures
    assert "first()" in signatures
    assert "class B {" in signatures
    assert "second()" in signatures


def test_ts_multiline_method_params_are_preserved():
    """SE5 剩余：TS 类方法多行参数此前只取到首行 ``async fetch(``。"""
    ts = """export class Service {
  async fetch(
    id: number,
    retries: string,
  ): Promise<string> {
    return doThing(id);
  }
}
"""

    signatures = extract_signatures("service.ts", ts)

    assert signatures is not None
    assert "id: number" in signatures
    assert "retries: string" in signatures
    assert "Promise<string>" in signatures
    assert "doThing" not in signatures


def test_js_multiline_function_params_are_preserved():
    """SE5 剩余：顶层 JS 多行函数签名此前只取到首行。"""
    js = """function longFunc(
  a,
  b,
) {
  return a + b;
}
"""

    signatures = extract_signatures("util.js", js)

    assert signatures is not None
    assert "function longFunc(" in signatures
    assert "a," in signatures
    assert "b," in signatures
    assert "return a + b" not in signatures


def test_js_multiline_arrow_signature_is_preserved():
    js = """const handler = (
  req,
  res,
) => {
  return res.send(req);
};
"""

    signatures = extract_signatures("route.js", js)

    assert signatures is not None
    assert "handler" in signatures
    assert "req" in signatures
    assert "res" in signatures
    assert "res.send" not in signatures


def test_long_signature_truncation_is_marked():
    """SE7: 超长签名被截断时附可见标记，下游可感知。"""
    long_params = ", ".join(f"param{i}: int" for i in range(40))
    ts = f"class S {{\n  run({long_params}): void {{}}\n}}\n"

    signatures = extract_signatures("s.ts", ts)

    assert signatures is not None
    assert "...[truncated]" in signatures


def test_short_signature_has_no_truncation_marker():
    ts = "class S {\n  run(): void {}\n}\n"

    signatures = extract_signatures("s.ts", ts)

    assert signatures is not None
    assert "...[truncated]" not in signatures
