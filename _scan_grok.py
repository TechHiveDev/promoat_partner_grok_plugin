import re

data = open(r"C:\Users\LENOVO\.grok\bin\grok.exe", "rb").read()
needles = [b"userConfig", b"user_config"]
for n in needles:
    idxs = []
    start = 0
    while len(idxs) < 20:
        i = data.find(n, start)
        if i < 0:
            break
        idxs.append(i)
        start = i + len(n)
    print("NEEDLE", n, "hits", len(idxs))
    for i in idxs:
        a = max(0, i - 70)
        b = min(len(data), i + 160)
        s = re.sub(rb"[^\x20-\x7e]", b" ", data[a:b]).decode()
        print(" ", " ".join(s.split())[:260])
