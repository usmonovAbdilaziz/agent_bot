#!/bin/sh
cd "$(dirname "$0")" || exit 1
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3,11))' 2>/dev/null; then
    "$candidate" run.py
    exit $?
  fi
done
echo 'Python 3.11+ kerak. python.org dan Python 3.12 yoki 3.13 o‘rnating.'
exit 1
