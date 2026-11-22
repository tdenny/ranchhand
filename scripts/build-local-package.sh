#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PIP=backend/.venv/bin/pip
[ -x "$PIP" ] || PIP=pip

rm -rf .aws-sam/local-package
"$PIP" install -r backend/requirements.txt \
    --target .aws-sam/local-package \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.13 \
    --only-binary=:all:
cp -r backend/src/. .aws-sam/local-package

# On SELinux hosts the container can't read the package unless it is labelled
# (otherwise the invoke fails with "No module named 'ranchhand'").
if command -v selinuxenabled >/dev/null 2>&1 && selinuxenabled; then
    chcon -R -t container_file_t .aws-sam/local-package
fi
