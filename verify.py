import ast, json

print("=== Final Verification ===")
print()

files = ['__init__.py', 'config_flow.py', 'sensor.py', 'const.py', 'api/__init__.py', 'api/const.py', 'api/exceptions.py']
for f in files:
    with open(f, encoding='utf-8') as fh:
        ast.parse(fh.read())
    print(f"[OK] Syntax: {f}")

for jf in ['manifest.json', 'strings.json', 'translations/zh-Hans.json', 'translations/en.json']:
    with open(jf, encoding='utf-8') as fh:
        json.load(fh)
    print(f"[OK] JSON: {jf}")

with open('../../hacs.json', encoding='utf-8') as fh:
    json.load(fh)
print("[OK] JSON: hacs.json")

def get_names(filepath):
    with open(filepath, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name): names.add(t.id)
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            names.add(n.target.id)
        elif isinstance(n, ast.ClassDef): names.add(n.name)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)): names.add(n.name)
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                names.add(a.asname or a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                names.add(a.asname or a.name)
    return names

const_names = get_names('const.py')
api_names = get_names('api/__init__.py')

print()
print(f"const.py has {len(const_names)} names")
print(f"api/__init__.py has {len(api_names)} names")
print(f"  LOGIN_TYPE_TO_QR_APP_NAME in api: {'LOGIN_TYPE_TO_QR_APP_NAME' in api_names}")
print(f"  LOGIN_TYPE_TO_QR_CODE_TYPE in api: {'LOGIN_TYPE_TO_QR_CODE_TYPE' in api_names}")
print(f"  InvalidCredentials in api: {'InvalidCredentials' in api_names}")
print(f"  LoginType in api: {'LoginType' in api_names}")
print(f"  CSGAPIError in api: {'CSGAPIError' in api_names}")
print(f"  NotLoggedIn in api: {'NotLoggedIn' in api_names}")

all_ok = True
for pyf in ['__init__.py', 'config_flow.py', 'sensor.py']:
    with open(pyf, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.level == 1:
            imported = [a.name for a in n.names]
            target = const_names if n.module == 'const' else api_names if n.module == 'api' else set()
            for name in imported:
                if target and name not in target:
                    print(f"[FAIL] {pyf} imports {name} from .{n.module} - NOT DEFINED")
                    all_ok = False

print()
print("=== Manifest ===")
with open('manifest.json', encoding='utf-8') as f:
    m = json.load(f)
for k in ['domain', 'name', 'codeowners', 'config_flow', 'documentation', 'issue_tracker', 'requirements', 'iot_class', 'version']:
    print(f"  {k}: {m.get(k)}")

print()
if all_ok:
    print("=== ALL CHECKS PASSED ===")
else:
    print("=== ISSUES FOUND ===")
