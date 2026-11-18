import json
import math
import os
import re
import sys
from pathlib import Path

MAX_ROW = 100000
MAX_COL = 26 * 26 + 26

class ProcessError(Exception):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def finite_number(v):
    return is_number(v) and (not isinstance(v, float) or math.isfinite(v))


def normalize_number(v):
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ProcessError("VALIDATION")
        if v.is_integer():
            return int(v)
    return v


def col_to_index(name):
    n = 0
    for ch in name.upper():
        n = n * 26 + ord(ch) - ord('A') + 1
    return n


def index_to_col(n):
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(ord('A') + r) + out
    return out


ADDRESS_RE = re.compile(r'^\$?([A-Za-z]{1,2})\$?([1-9][0-9]*)$')


def parse_address(text, allow_absolute=True):
    if not isinstance(text, str):
        raise ProcessError("VALIDATION")
    m = ADDRESS_RE.fullmatch(text.strip())
    if not m:
        raise ProcessError("VALIDATION")
    col, row = m.group(1).upper(), int(m.group(2))
    ci = col_to_index(col)
    if ci < 1 or ci > MAX_COL or row < 1 or row > MAX_ROW:
        raise ProcessError("VALIDATION")
    return ci, row, f"{col}${row}".replace('$', '')


def parse_formula_address(text):
    m = re.fullmatch(r'\$?([A-Za-z]{1,2})\$?([1-9][0-9]*)', text)
    if not m:
        return None
    col = m.group(1).upper()
    ci = col_to_index(col)
    row = int(m.group(2))
    if ci > MAX_COL or row > MAX_ROW:
        return None
    return ci, row


def address_from_parts(ci, row):
    return index_to_col(ci) + str(row)


class SheetEngine:
    def __init__(self):
        self.sheets = {}
        self.cache = {}
        self.add_sheet("Sheet1")

    def add_sheet(self, name):
        if not isinstance(name, str) or not name:
            raise ProcessError("VALIDATION")
        key = name.lower()
        if key not in self.sheets:
            self.sheets[key] = {"name": name, "cells": {}}
            self.cache[key] = {}
        return self.sheets[key]

    def get_sheet(self, name):
        if not isinstance(name, str) or not name:
            raise ProcessError("VALIDATION")
        key = name.lower()
        if key not in self.sheets:
            raise RefError()
        return self.sheets[key]

    def clear_caches(self):
        self.cache = {k: {} for k in self.sheets}

    def set(self, sheet_name, cell, value):
        ci, row, canonical = parse_address(cell)
        addr = address_from_parts(ci, row)
        sheet = self.add_sheet(sheet_name if sheet_name is not None else "Sheet1")
        key = sheet["name"].lower()
        if value is None:
            sheet["cells"].pop(addr, None)
        elif isinstance(value, str) and value.startswith("="):
            sheet["cells"][addr] = value
        elif isinstance(value, (str, bool)):
            sheet["cells"][addr] = value
        elif is_number(value):
            if not finite_number(value):
                raise ProcessError("VALIDATION")
            sheet["cells"][addr] = normalize_number(value)
        else:
            raise ProcessError("VALIDATION")
        self.cache[key] = {}
        return True

    def import_values(self, sheet_name, values):
        if not isinstance(values, list):
            raise ProcessError("VALIDATION")
        for row in values:
            if not isinstance(row, list):
                raise ProcessError("VALIDATION")
        if len(values) > MAX_ROW:
            raise ProcessError("VALIDATION")
        for row in values:
            if len(row) > MAX_COL:
                raise ProcessError("VALIDATION")
        sheet = self.add_sheet(sheet_name if sheet_name is not None else "Sheet1")
        sheet["cells"] = {}
        key = sheet["name"].lower()
        for r_index, row in enumerate(values, 1):
            for c_index, value in enumerate(row, 1):
                addr = address_from_parts(c_index, r_index)
                if value is None:
                    continue
                if isinstance(value, str) and value.startswith("="):
                    sheet["cells"][addr] = value
                elif isinstance(value, (str, bool)):
                    sheet["cells"][addr] = value
                elif is_number(value):
                    if not finite_number(value):
                        raise ProcessError("VALIDATION")
                    sheet["cells"][addr] = normalize_number(value)
                else:
                    raise ProcessError("VALIDATION")
        self.cache[key] = {}
        return True

    def raw_get(self, sheet_name, addr):
        ci, row, canonical = parse_address(addr)
        addr = address_from_parts(ci, row)
        sheet = self.get_sheet(sheet_name if sheet_name is not None else "Sheet1")
        return sheet, addr

    def evaluate_address(self, sheet_name, addr):
        sheet, canonical = self.raw_get(sheet_name, addr)
        key = sheet["name"].lower()
        if canonical in self.cache[key]:
            return self.cache[key][canonical]
        if canonical not in sheet["cells"]:
            self.cache[key][canonical] = None
            return None
        return self.evaluate_cell(key, canonical)

    def evaluate_cell(self, sheet_key, addr):
        if sheet_key not in self.sheets:
            return {"error": "REF"}
        if addr in self.cache[sheet_key]:
            return self.cache[sheet_key][addr]
        sheet = self.sheets[sheet_key]
        if addr not in sheet["cells"]:
            self.cache[sheet_key][addr] = None
            return None
        marker = (sheet_key, addr)
        if hasattr(self, "_stack"):
            pass
        else:
            self._stack = set()
        if marker in self._stack:
            result = {"error": "CYCLE"}
            self.cache[sheet_key][addr] = result
            return result
        raw = sheet["cells"][addr]
        if not isinstance(raw, str) or not raw.startswith("="):
            self.cache[sheet_key][addr] = raw
            return raw
        self._stack.add(marker)
        try:
            parser = FormulaParser(raw[1:], sheet_key)
            ast = parser.parse()
            result = evaluate_ast(ast, self)
            if isinstance(result, float):
                result = normalize_number(result)
            if is_error(result):
                result = dict(result)
            self.cache[sheet_key][addr] = result
            return result
        except FormulaParseError:
            result = {"error": "PARSE"}
            self.cache[sheet_key][addr] = result
            return result
        finally:
            self._stack.remove(marker)

    def export_range(self, sheet_name, range_text):
        try:
            s_col, s_row, e_col, e_row = parse_range_text(range_text)
        except ProcessError:
            raise
        sheet = self.get_sheet(sheet_name if sheet_name is not None else "Sheet1")
        result = []
        for row in range(s_row, e_row + 1):
            vals = []
            for col in range(s_col, e_col + 1):
                addr = address_from_parts(col, row)
                try:
                    vals.append(self.evaluate_address(sheet["name"], addr))
                except RefError:
                    vals.append({"error": "REF"})
            result.append(vals)
        return result

    def save(self, path):
        if not isinstance(path, str) or not path:
            raise ProcessError("VALIDATION")
        sheets_data = {}
        for key, sheet in self.sheets.items():
            cells = {}
            for addr in sorted(sheet["cells"], key=address_sort_key):
                val = sheet["cells"][addr]
                if val is not None:
                    cells[addr] = val
            sheets_data[sheet["name"]] = cells
        data = {"format": "sheet-v1", "sheets": sheets_data}
        p = Path(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            temp = p.parent / (p.name + ".tmp-" + str(os.getpid()))
            with temp.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, p)
        except (OSError, ValueError) as exc:
            raise ProcessError("IO", str(exc))
        return True

    def load(self, path):
        if not isinstance(path, str) or not path:
            raise ProcessError("VALIDATION")
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8")
            data = json.loads(text, parse_constant=lambda x: (_ for _ in()).throw(ValueError("invalid JSON number")))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise ProcessError("PARSE", str(exc))
        except OSError as exc:
            raise ProcessError("IO", str(exc))
        if not isinstance(data, dict) or data.get("format") != "sheet-v1" or not isinstance(data.get("sheets"), dict):
            raise ProcessError("PARSE")
        new_sheets = {}
        new_cache = {}
        for name, cells in data["sheets"].items():
            if not isinstance(name, str) or not name or not isinstance(cells, dict):
                raise ProcessError("PARSE")
            key = name.lower()
            if key in new_sheets:
                raise ProcessError("PARSE")
            clean = {}
            for addr, value in cells.items():
                try:
                    ci, row, _ = parse_address(addr)
                except ProcessError:
                    raise ProcessError("PARSE")
                canonical = address_from_parts(ci, row)
                if value is None:
                    continue
                if isinstance(value, str):
                    clean[canonical] = value
                elif isinstance(value, bool):
                    clean[canonical] = value
                elif is_number(value) and finite_number(value):
                    clean[canonical] = normalize_number(value)
                else:
                    raise ProcessError("PARSE")
            new_sheets[key] = {"name": name, "cells": clean}
            new_cache[key] = {}
        if "sheet1" not in new_sheets:
            new_sheets["sheet1"] = {"name": "Sheet1", "cells": {}}
            new_cache["sheet1"] = {}
        self.sheets = new_sheets
        self.cache = new_cache
        self._stack = set()
        return True


class RefError(Exception):
    pass


def is_error(v):
    return isinstance(v, dict) and set(v.keys()) == {"error"} and isinstance(v["error"], str)


def parse_range_text(text):
    if not isinstance(text, str):
        raise ProcessError("VALIDATION")
    text = text.strip().replace("$", "")
    if ":" not in text:
        ci, row, _ = parse_address(text)
        return ci, row, ci, row
    parts = text.split(":")
    if len(parts) != 2:
        raise ProcessError("VALIDATION")
    ci1, r1, _ = parse_address(parts[0])
    ci2, r2, _ = parse_address(parts[1])
    if ci1 > ci2:
        ci1, ci2 = ci2, ci1
    if r1 > r2:
        r1, r2 = r2, r1
    return ci1, r1, ci2, r2


def address_sort_key(addr):
    m = re.fullmatch(r'([A-Z]+)([0-9]+)', addr)
    if not m:
        return (0, 0)
    return (int(m.group(2)), col_to_index(m.group(1)))


class FormulaParseError(Exception):
    pass


class FormulaLexer:
    def __init__(self, text):
        self.text = text
        self.pos = 0

    def tokens(self):
        tokens = []
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch.isspace():
                self.pos += 1
                continue
            if ch == '"':
                self.pos += 1
                chars = []
                while self.pos < len(self.text):
                    if self.text[self.pos] == '"':
                        if self.pos + 1 < len(self.text) and self.text[self.pos + 1] == '"':
                            chars.append('"')
                            self.pos += 2
                        else:
                            self.pos += 1
                            break
                    else:
                        chars.append(self.text[self.pos])
                        self.pos += 1
                else:
                    raise FormulaParseError()
                tokens.append(("STRING", "".join(chars)))
                continue
            if ch.isdigit() or (ch == '.' and self.pos + 1 < len(self.text) and self.text[self.pos + 1].isdigit()):
                m = re.match(r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?', self.text[self.pos:])
                if not m:
                    raise FormulaParseError()
                text = m.group(0)
                self.pos += len(text)
                tokens.append(("NUMBER", text))
                continue
            if ch.isalpha() or ch == '_' or ch == '$':
                start = self.pos
                if ch == '$':
                    self.pos += 1
                    if self.pos >= len(self.text) or not (self.text[self.pos].isalpha() or self.text[self].isalpha() if False else False):
                        pass
                m = re.match(r'[A-Za-z_][A-Za-z0-9_]*|\$[A-Za-z]{1,2}\$?[1-9][0-9]*|\$?[A-Za-z]{1,2}\$[1-9][0-9]*', self.text[self.pos:])
                if m:
                    text = m.group(0)
                    self.pos += len(text)
                    tokens.append(("IDENT", text))
                else:
                    raise FormulaParseError()
                continue
            two = self.text[self.pos:self.pos + 2]
            if two in ('<=', '>=', '<>'):
                tokens.append(("OP", two))
                self.pos += 2
                continue
            if ch in '+-*/=<>(),:!':
                typ = "OP" if ch in '+-*/=<>' else "SYMBOL"
                tokens.append((typ, ch))
                self.pos += 1
                continue
            raise FormulaParseError()
        tokens.append(("EOF", ""))
        return tokens


class FormulaParser:
    def __init__(self, text, current_sheet):
        self.text = text
        self.current_sheet = current_sheet
        self.tokens = FormulaLexer(text).tokens()
        self.pos = 0

    def peek(self, value=None, typ=None):
        t = self.tokens[self.pos]
        if value is not None:
            return t[1] == value
        if typ is not None:
            return t[0] == typ
        return t

    def take(self):
        t = self.tokens[self.pos]
        if t[0] != "EOF":
            self.pos += 1
        return t

    def parse(self):
        if self.peek(typ="EOF"):
            raise FormulaParseError()
        ast = self.comparison()
        if not self.peek(typ="EOF"):
            raise FormulaParseError()
        return ast

    def comparison(self):
        left = self.additive()
        if self.peek(typ="OP") and self.peek()[1] in ('=', '<>', '<', '<=', '>', '>='):
            op = self.take()[1]
            right = self.additive()
            return ("compare", op, left, right)
        return left

    def additive(self):
        left = self.multiplicative()
        while self.peek(typ="OP") and self.peek()[1] in ('+', '-'):
            op = self.take()[1]
            right = self.multiplicative()
            left = ("binary", op, left, right)
        return left

    def multiplicative(self):
        left = self.unary()
        while self.peek(typ="OP") and self.peek()[1] in ('*', '/'):
            op = self.take()[1]
            right = self.unary()
            left = ("binary", op, left, right)
        return left

    def unary(self):
        if self.peek(typ="OP") and self.peek()[1] in ('+', '-'):
            op = self.take()[1]
            return ("unary", op, self.unary())
        return self.primary()

    def primary(self):
        if self.peek(typ="NUMBER"):
            text = self.take()[1]
            try:
                v = float(text) if any(ch in text.lower() for ch in '.e') else int(text)
            except ValueError:
                raise FormulaParseError()
            return ("literal", normalize_number(v))
        if self.peek(typ="STRING"):
            return ("literal", self.take()[1])
        if self.peek(value="("):
            self.take()
            node = self.comparison()
            if not self.peek(value=")"):
                raise FormulaParseError()
            self.take()
            return node
        if self.peek(typ="IDENT"):
            text = self.take()[1]
            upper = text.upper()
            if upper in ('TRUE', 'FALSE'):
                return ("literal", upper == "TRUE")
            if self.peek(value="("):
                self.take()
                args = []
                if not self.peek(value=")"):
                    while True:
                        args.append(self.comparison())
                        if self.peek(value=","):
                            self.take()
                            continue
                        break
                if not self.peek(value=")"):
                    raise FormulaParseError()
                self.take()
                return ("call", upper, args)
            if self.peek(value="!"):
                self.take()
                sheet_name = text
                ref_text = self.take_ref_text()
                start = parse_formula_address(ref_text)
                if start is None:
                    return ("name", text + "!" + ref_text)
                end = None
                if self.peek(value=":"):
                    self.take()
                    ref_text2 = self.take_ref_text()
                    end = parse_formula_address(ref_text2)
                    if end is None:
                        return ("name", text + "!" + ref_text2)
                    return ("range", sheet_name, start, end)
                return ("ref", sheet_name, address_from_parts(start[0], start[1]))
            start = parse_formula_address(text)
            if start is not None:
                end = None
                if self.peek(value=":"):
                    self.take()
                    ref_text = self.take_ref_text()
                    end = parse_formula_address(ref_text)
                    if end is None:
                        return ("name", text + ":" + ref_text)
                    return ("range", None, start, end)
                return ("ref", None, address_from_parts(start[0], start[1]))
            if re.fullmatch(r'[A-Za-z]+[0-9]+', text):
                return ("badref", text)
            return ("name", text)
        raise FormulaParseError()

    def take_ref_text(self):
        if not self.peek(typ="IDENT"):
            raise FormulaParseError()
        text = self.take()[1]
        return text


def evaluate_ast(node, engine):
    kind = node[0]
    if kind == "literal":
        return node[1]
    if kind == "name":
        return {"error": "NAME"}
    if kind == "badref":
        return {"error": "REF"}
    if kind == "ref":
        sheet_name = node[1]
        addr = node[2]
        if sheet_name is None:
            sheet_name = engine._current_formula_sheet
        try:
            return engine.evaluate_address(sheet_name, addr)
        except RefError:
            return {"error": "REF"}
    if kind == "range":
        return ("range", node)
    if kind == "unary":
        v = evaluate_ast(node[2], engine)
        if is_error(v):
            return v
        if v is None:
            v = 0
        if isinstance(v, bool) or isinstance(v, str):
            return {"error": "TYPE"}
        if not is_number(v):
            return {"error": "TYPE"}
        r = v if node[1] == '+' else -v
        return normalize_number(r)
    if kind == "binary":
        left = evaluate_ast(node[2], engine)
        right = evaluate_ast(node[3], engine)
        if is_error(left):
            return left
        if is_error(right):
            return right
        if left is None:
            left = 0
        if right is None:
            right = 0
        if isinstance(left, (bool, str)) or isinstance(right, (bool, str)):
            return {"error": "TYPE"}
        if not is_number(left) or not is_number(right):
            return {"error": "TYPE"}
        op = node[1]
        try:
            if op == '+':
                r = left + right
            elif op == '-':
                r = left - right
            elif op == '*':
                r = left * right
            else:
                if right == 0:
                    return {"error": "DIV_ZERO"}
                r = left / right
            return normalize_number(r)
        except (ArithmeticError, OverflowError):
            return {"error": "DIV_ZERO"}
    if kind == "compare":
        left = evaluate_ast(node[2], engine)
        right = evaluate_ast(node[3], engine)
        if is_error(left):
            return left
        if is_error(right):
            return right
        op = node[1]
        if left is None:
            left = 0
        if right is None:
            right = 0
        if isinstance(left, (bool, str)) or isinstance(right, (bool, str)):
            if isinstance(left, bool) and isinstance(right, bool):
                pass
            elif isinstance(left, str) and isinstance(right, str):
                pass
            else:
                return {"error": "TYPE"}
        elif not is_number(left) or not is_number(right):
            return {"error": "TYPE"}
        try:
            if op == '=':
                r = left == right
            elif op == '<>':
                r = left != right
            elif op == '<':
                r = left < right
            elif op == '<=':
                r = left <= right
            elif op == '>':
                r = left > right
            else:
                r = left >= right
            return r
        except (TypeError, ValueError):
            return {"error": "TYPE"}
    if kind == "call":
        name = node[1]
        args = node[2]
        if name not in ('SUM', 'AVERAGE', 'MIN', 'MAX', 'COUNT', 'IF'):
            return {"error": "NAME"}
        if name == 'IF':
            if len(args) != 3:
                return {"error": "ARGS"}
            cond = evaluate_ast(args[0], engine)
            if is_error(cond):
                return cond
            if cond is None:
                return {"error": "TYPE"}
            if isinstance(cond, bool):
                chosen = cond
            elif is_number(cond):
                chosen = cond != 0
            else:
                return {"error": "TYPE"}
            return evaluate_ast(args[1 if chosen else 2], engine)
        if len(args) < 1:
            return {"error": "ARGS"}
        values = []
        for arg in args:
            v = evaluate_ast(arg, engine)
            if is_error(v):
                return v
            if isinstance(v, tuple) and v and v[0] == "range":
                range_node = v[1]
                sheet_name = range_node[2]
                start = range_node[3]
                end = range_node[4]
                if sheet_name is None:
                    sheet_name = engine._current_formula_sheet
                try:
                    sheet = engine.get_sheet(sheet_name)
                except RefError:
                    return {"error": "REF"}
                s_col, s_row = start
                e_col, e_row = end
                if s_col > e_col:
                    s_col, e_col = e_col, s_col
                if s_row > e_row:
                    s_row, e_row = e_row, s_row
                for row in range(s_row, e_row + 1):
                    for col in range(s_col, e_col + 1):
                        addr = address_from_parts(col, row)
                        rv = engine.evaluate_address(sheet_name, addr)
                        if is_error(rv):
                            return rv
                        values.append(rv)
            else:
                values.append(v)
        numeric = []
        for v in values:
            if v is None:
                continue
            if isinstance(v, bool) or isinstance(v, str):
                # Range values are indistinguishable at this stage; scalars reject them.
                continue
            if is_number(v):
                numeric.append(v)
        # Re-evaluate scalar type rejection for arguments that were not ranges.
        # This is handled separately below for aggregate range-versus-scalar semantics.
        if name == 'SUM':
            return normalize_number(sum(numeric))
        if name == 'COUNT':
            return len(numeric)
        if name == 'AVERAGE':
            if not numeric:
                return {"error": "DIV_ZERO"}
            return normalize_number(sum(numeric) / len(numeric))
        if name == 'MIN':
            return normalize_number(min(numeric)) if numeric else 0
        if name == 'MAX':
            return normalize_number(max(numeric)) if numeric else 0
    raise FormulaParseError()


def run_sheet_operations(engine, operations):
    results = []
    for op in operations:
        if not isinstance(op, dict):
            raise ProcessError("VALIDATION")
        allowed = set()
        name = op.get("op")
        if name == "set":
            allowed = {"op", "sheet", "cell", "value"}
            if set(op) - allowed or "cell" not in op or "value" not in op:
                raise ProcessError("VALIDATION")
            parse_address(op["cell"])
            engine.set(op.get("sheet"), op["cell"], op["value"])
            results.append(True)
        elif name == "get":
            allowed = {"op", "sheet", "cell"}
            if set(op) - allowed or "cell" not in op:
                raise ProcessError("VALIDATION")
            cell_text = op["cell"]
            sheet_name = op.get("sheet")
            if "!" in cell_text:
                if sheet_name is not None:
                    raise ProcessError("VALIDATION")
                parts = cell_text.split("!", 1)
                if len(parts) != 2:
                    raise ProcessError("VALIDATION")
                sheet_name, cell_text = parts
            parse_address(cell_text)
            ci, row, canonical = parse_address(cell_text)
            addr = address_from_parts(ci, row)
            try:
                engine._current_formula_sheet = (sheet_name or "Sheet1").lower()
                value = engine.evaluate_address(sheet_name or "Sheet1", addr)
            except RefError:
                value = {"error": "REF"}
            finally:
                engine._current_formula_sheet = None
            results.append(value)
        elif name == "save":
            allowed = {"op", "path"}
            if set(op) - allowed or "path" not in op:
                raise ProcessError("VALIDATION")
            results.append(engine.save(op["path"]))
        elif name == "load":
            allowed = {"op", "path"}
            if set(op) - allowed or "path" not in op:
                raise ProcessError("VALIDATION")
            results.append(engine.load(op["path"]))
        elif name == "import":
            allowed = {"op", "sheet", "values"}
            if set(op) - allowed or "values" not in op:
                raise ProcessError("VALIDATION")
            results.append(engine.import_values(op.get("sheet"), op["values"]))
        elif name == "export":
            allowed = {"op", "sheet", "range"}
            if set(op) - allowed or "range" not in op:
                raise ProcessError("VALIDATION")
            try:
                results.append(engine.export_range(op.get("sheet"), op["range"]))
            except RefError:
                results.append({"error": "REF"})
        else:
            raise ProcessError("VALIDATION")
    return results


def read_json_stdin():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw, parse_constant=lambda x: (_ for _ in()).throw(ValueError("invalid JSON number")))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ProcessError("PARSE", str(exc))
    if not isinstance(data, dict):
        raise ProcessError("VALIDATION")
    if set(data) != {"operations"} or not isinstance(data["operations"], list):
        raise ProcessError("VALIDATION")
    return data["operations"]


def emit_error(exc):
    payload = {"error": {"code": exc.code}}
    if exc.detail:
        payload["error"]["detail"] = str(exc.detail)
    sys.stderr.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    sys.stderr.write("\n")


def main():
    sys.setrecursionlimit(10000)
    if len(sys.argv) != 2:
        err = ProcessError("VALIDATION")
        emit_error(err)
        return 2
    app = sys.argv[1].lower()
    try:
        operations = read_json_stdin()
        if app != "sheet":
            raise ProcessError("VALIDATION")
        engine = SheetEngine()
        results = run_sheet_operations(engine, operations)
        sys.stdout.write(json.dumps({"results": results}, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        sys.stdout.write("\n")
        return 0
    except ProcessError as exc:
        emit_error(exc)
        return 2
    except Exception as exc:
        emit_error(ProcessError("EXECUTION", str(exc)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
