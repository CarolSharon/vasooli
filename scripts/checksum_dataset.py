import argparse
import hashlib
import json
from pathlib import Path


def canonical_bytes(path: Path) -> bytes:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    digest = hashlib.sha256(canonical_bytes(args.source)).hexdigest()
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(
        f"{digest}  {args.source.as_posix()}\n", encoding="utf-8"
    )
    print(f"Canonical SHA-256: {digest}")


if __name__ == "__main__":
    main()
