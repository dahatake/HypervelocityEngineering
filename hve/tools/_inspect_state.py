import json, sys
s = json.load(open(sys.argv[1], encoding='utf-8'))
print('keys:', list(s.keys())[:30])
for k in ('workflows','steps','dag','dag_plan','active_steps'):
    v = s.get(k)
    if v is None: continue
    print('---', k)
    if isinstance(v, dict):
        for kk, vv in v.items():
            print(kk, '->', type(vv).__name__, str(vv)[:200])
    else:
        print(str(v)[:500])
