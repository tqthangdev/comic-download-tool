import pathlib
import sys

default = r".venv\Lib\site-packages\nodriver"
root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else default)

if not root.is_dir():
    print("fix_nodriver: directory not found:", root.resolve())
    sys.exit(0)

count = 0
for p in root.rglob("*.py"):
    data = p.read_bytes()
    try:
        data.decode("utf-8")
        continue
    except UnicodeDecodeError:
        pass
    # byte 0xB1 (+/- in latin-1) -> ASCII
    p.write_bytes(data.replace(b"\xb1", b"+/-"))
    print("fix_nodriver: patched", p)
    count += 1

# Stay quiet when there is nothing to do: this runs on every app launch, so an
# unconditional summary would print on every start after the first patch.
if count:
    print("fix_nodriver: done,", count, "file(s) patched")