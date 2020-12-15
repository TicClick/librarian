#!/usr/bin/env bash

set -e

SYSTEM_PYTHON=python3
VENV_DIR=venv
BIN_DIR="$VENV_DIR"/bin

while [[ $# -gt 0 ]]; do
    case "$1" in
        setup)
        [ -d "$VENV_DIR" ] || ( \
            "$SYSTEM_PYTHON" -m venv "$VENV_DIR" && \
            "$BIN_DIR"/pip install -r requirements.txt \
        )
        exit $?;;

        test)
        shift
        "$BIN_DIR"/pytest "$@"
        exit $?;;

        run)
        shift
        "$BIN_DIR"/python -m librarian.main "$@"
        exit $?;;

        coverage)
        shift
        "$BIN_DIR"/coverage run --source librarian -m pytest
        exit $?;;

        cov)
        shift
        "$BIN_DIR"/coverage report -m
        exit $?;;

        hcov)
        shift
        "$BIN_DIR"/coverage html && ((which xdg-open && xdg-open htmlcov/index.html) || open htmlcov/index.html)
        exit $?;;

        clean)
        shift
        for ITEM in {htmlcov,.coverage}; do rm -r "$ITEM"; done; \
        for ITEM in {.pytest_cache,__pycache__}; do find . -name "$ITEM" -exec rm -r {} +; done
        rm -r "$VENV_DIR"
        exit $?;;

    esac
done
