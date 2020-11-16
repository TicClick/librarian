#!/usr/bin/env bash

BASE="."

source "${BASE}/runtime/venv/bin/activate"
PYTHONPATH="." "${BASE}/runtime/venv/bin/python" "${BASE}/librarian/main.py"
