import os
import shutil
import subprocess
import sys

def main():
    binary = shutil.which("skillloader")
    if not binary or os.path.realpath(binary) == os.path.realpath(sys.argv[0]):
        raise SystemExit("skillloader binary not found; install with: go install github.com/voodoosim/skillloader@latest")
    raise SystemExit(subprocess.call([binary, *sys.argv[1:]]))
