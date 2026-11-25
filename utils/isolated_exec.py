"""Enter a mount namespace that hides private benchmark data, then exec."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 4:
        raise SystemExit(
            "usage: isolated_exec.py PRIVATE_BENCHMARK_ROOT WORKSPACE COMMAND [ARG ...]"
        )

    private_root = Path(sys.argv[1]).resolve()
    workspace = Path(sys.argv[2]).resolve()
    command = sys.argv[3:]
    if not private_root.is_dir():
        raise RuntimeError(f"Private benchmark root does not exist: {private_root}")

    empty_root = workspace / ".hidden-benchmark-root"
    empty_root.mkdir(mode=0o700, exist_ok=True)
    subprocess.run(
        ["mount", "--bind", str(empty_root), str(private_root)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if any(private_root.iterdir()):
        raise RuntimeError("Private benchmark mount is still visible inside agent namespace.")
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
