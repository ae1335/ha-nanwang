"""Full syntax + import check for csg_power integration."""
import ast
import json
import pathlib
import re
from typing import Any

base = pathlib.Path("custom_components/csg_power")
errors = []

# 1. Check all Python files parse correctly
py_files = list(base.rglob("*.py"))
for f in py_files:
    try:
        ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        print(f"[OK] {f.relative_to(base)} - syntax OK")
    except SyntaxError as e:
        errors.append(f"[FAIL] {f.relative_to(base)} - {e}")
        print(f"[FAIL] {f.relative_to(base)} - {e}")

# 2. Check all JSON files
json_files = list(base.rglob("*.json"))
for f in json_files:
    try:
        json.loads(f.read_text(encoding="utf-8"))
        print(f"[OK] {f.relative_to(base)} - valid JSON")
    except json.JSONDecodeError as e:
        errors.append(f"[FAIL] {f.relative_to(base)} - {e}")
        print(f"[FAIL] {f.relative_to(base)} - {e}")

# 2.5 Manifest integrity
manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
manifest_errors = []

REQUIRED_MANIFEST_KEYS = (
    "domain",
    "name",
    "version",
    "documentation",
    "issue_tracker",
    "codeowners",
    "iot_class",
    "requirements",
    "config_flow",
)
for key in REQUIRED_MANIFEST_KEYS:
    if key not in manifest:
        manifest_errors.append(f"missing required key: {key}")

if not re.fullmatch(r"\d+\.\d+\.\d+", str(manifest.get("version", ""))):
    manifest_errors.append(f"version is not semantic (x.y.z): {manifest.get('version')}")

if manifest.get("domain") != base.name:
    manifest_errors.append(
        f"domain {manifest.get('domain')!r} does not match directory name {base.name!r}"
    )

VALID_IOT_CLASSES = {
    "assumed_state",
    "cloud_polling",
    "cloud_push",
    "local_polling",
    "local_push",
}
if manifest.get("iot_class") not in VALID_IOT_CLASSES:
    manifest_errors.append(f"unknown iot_class: {manifest.get('iot_class')}")

for req in manifest.get("requirements", []):
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+(==|>=|<=|~=|!=|>|<)?[A-Za-z0-9_.]*", req):
        manifest_errors.append(f"malformed requirement: {req}")

if manifest_errors:
    for err in manifest_errors:
        print(f"[FAIL] manifest.json - {err}")
    errors.append(f"manifest.json: {manifest_errors}")
else:
    print(f"[OK] manifest.json integrity (version {manifest.get('version')})")

# 3. Check step_ids in config_flow.py vs strings.json
strings = json.loads((base / "strings.json").read_text(encoding="utf-8"))
config_flow_src = (base / "config_flow.py").read_text(encoding="utf-8")

# Collect STEP_* constant values from const.py so step_id=STEP_XXX names
# can be resolved to their string values.
const_tree = ast.parse((base / "const.py").read_text(encoding="utf-8"))
step_consts: dict[str, str] = {}
for node in ast.walk(const_tree):
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.startswith("STEP_"):
                step_consts[target.id] = str(node.value.value)

# AST-based analysis: only steps that actually render a form/menu
# (async_show_form / async_show_menu) need a strings.json entry. Steps that
# only delegate (e.g. async_step_reauth -> reauth_confirm) or act as menu
# options (covered by user.menu_options) do not.
tree = ast.parse(config_flow_src)
form_steps = set()


def step_id_value(node: ast.expr):
    """Resolve a step_id expression to a string value, or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in step_consts:
        return step_consts[node.id]
    return None


for node in ast.walk(tree):
    if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr in ("async_show_form", "async_show_menu")
            ):
                for kw in sub.keywords:
                    if kw.arg == "step_id":
                        value = step_id_value(kw.value)
                        if value:
                            form_steps.add(value)

all_steps = form_steps

strings_steps = set(strings.get("config", {}).get("step", {}).keys())
strings_steps |= set(strings.get("options", {}).get("step", {}).keys())

missing = all_steps - strings_steps
extra = strings_steps - all_steps

print(f"\nStep IDs rendering forms in config_flow.py: {sorted(all_steps)}")
print(f"Step IDs in strings.json:                   {sorted(strings_steps)}")
if missing:
    print(f"[WARN] Missing in strings.json: {sorted(missing)}")
    errors.append(f"Missing in strings.json: {sorted(missing)}")
else:
    print("[OK] All config_flow step_ids have strings.json entries")
if extra:
    print(f"[INFO] Extra in strings.json (unused): {sorted(extra)}")

# 4. Check OptionsFlow __init__
print("\n=== OptionsFlow check ===")
opt_idx = config_flow_src.find("class CSGOptionsFlowHandler")
if opt_idx >= 0:
    opt_section = config_flow_src[opt_idx:]
    init_match = re.search(r'def __init__\s*\([^)]*\)[^:]*:.*?(?=\n    async def|\nclass|\Z)', opt_section, re.DOTALL)
    if init_match:
        init_text = init_match.group(0)[:500]
        print(init_text[:400])
        if "super().__init__" in init_text:
            print("[OK] super().__init__() called")
        else:
            print("[WARN] No super().__init__() found")
    else:
        print("[WARN] No __init__ found in OptionsFlowHandler")
else:
    print("[FAIL] CSGOptionsFlowHandler not found")
    errors.append("CSGOptionsFlowHandler not found")

# 5. Check abort reasons in strings.json vs config_flow.py
abort_reasons = set(re.findall(r'async_abort\s*\(\s*reason\s*=\s*["\']([^"\']+)["\']', config_flow_src))
strings_aborts = set(strings.get("config", {}).get("abort", {}).keys())
strings_aborts |= set(strings.get("options", {}).get("abort", {}).keys())
missing_aborts = abort_reasons - strings_aborts
if missing_aborts:
    print(f"\n[WARN] Missing abort reasons in strings.json: {sorted(missing_aborts)}")
    errors.append(f"Missing abort reasons: {sorted(missing_aborts)}")
else:
    print("\n[OK] All abort reasons present in strings.json")

# 6. Check error keys
error_keys = set(re.findall(r'errors\["base"\]\s*=\s*["\']([^"\']+)["\']', config_flow_src))
strings_errors = set(strings.get("config", {}).get("error", {}).keys())
missing_errors = error_keys - strings_errors
if missing_errors:
    print(f"[WARN] Missing error keys in strings.json: {sorted(missing_errors)}")
    errors.append(f"Missing error keys: {sorted(missing_errors)}")
else:
    print("[OK] All error keys present in strings.json")

# 7. Translation parity: strings.json / zh-Hans.json / en.json must share
#    the exact same key structure, otherwise some languages silently fall
#    back to untranslated strings.
def _flatten_keys(obj: Any, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for k, v in obj.items():
        path = f"{prefix}.{k}" if prefix else str(k)
        keys.add(path)
        if isinstance(v, dict):
            keys |= _flatten_keys(v, path)
    return keys

strings_key_set = _flatten_keys(strings)
for trans_name in ("zh-Hans.json", "en.json"):
    trans = json.loads(
        (base / "translations" / trans_name).read_text(encoding="utf-8")
    )
    trans_keys = _flatten_keys(trans)
    miss = strings_key_set - trans_keys
    extra = trans_keys - strings_key_set
    if miss or extra:
        print(f"[FAIL] Translation structure mismatch in {trans_name}")
        if miss:
            print(f"       missing keys: {sorted(miss)}")
        if extra:
            print(f"       extra keys:   {sorted(extra)}")
        errors.append(f"Translation mismatch in {trans_name}")
    else:
        print(f"[OK] {trans_name} key structure matches strings.json")

# 7. Cross-check: every SUFFIX_*/ATTR_KEY_* referenced in sensor.py must be
#    written by the coordinator, i.e. appear as the inner key of an
#    assignment to self._gathered_data[...][KEY] = ... . This catches
#    "sensor entity added but its data is never produced" mistakes.
sensor_tree = ast.parse((base / "sensor.py").read_text(encoding="utf-8"))
referenced_keys = set()
filled_keys = set()
for node in ast.walk(sensor_tree):
    if isinstance(node, ast.Name) and (
        node.id.startswith("SUFFIX_") or node.id.startswith("ATTR_KEY_")
    ):
        referenced_keys.add(node.id)
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Subscript) and isinstance(
                target.value, ast.Subscript
            ):
                inner = target.slice
                if isinstance(inner, ast.Name):
                    filled_keys.add(inner.id)
                elif isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    filled_keys.add(inner.value)

missing_fill = referenced_keys - filled_keys
if missing_fill:
    print(
        f"[FAIL] Keys referenced in sensor.py but never filled by the "
        f"coordinator: {sorted(missing_fill)}"
    )
    errors.append(f"Keys missing data source: {sorted(missing_fill)}")
else:
    print(
        f"[OK] All {len(referenced_keys)} SUFFIX_/ATTR_KEY_ keys referenced "
        f"in sensor.py are filled by the coordinator"
    )

# 8. Summary
print(f"\n=== Summary: {len(errors)} errors ===")
for e in errors:
    print(f"  {e}")
if not errors:
    print("  All checks passed!")
