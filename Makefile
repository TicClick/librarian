SYSTEM_PYTHON = python3

.PHONY = setup test run coverage cov hcov

RUNTIME_DIR = runtime
VENV_DIR = ${RUNTIME_DIR}/venv
BIN_DIR = ${VENV_DIR}/bin
VENV_PYTHON = ${BIN_DIR}/python

JUNK = htmlcov .coverage
RECURSIVE_JUNK = .pytest_cache __pycache__

setup:
	[ -d runtime ] || ( \
		${SYSTEM_PYTHON} -m venv ${VENV_DIR} && \
		${VENV_PYTHON} -m pip install -r requirements.txt \
	)

test: setup
	${BIN_DIR}/pytest $(args)

run: setup
	${VENV_PYTHON} -m librarian.main

coverage: setup
	${BIN_DIR}/coverage run --source librarian -m pytest

cov: coverage
	${BIN_DIR}/coverage report -m

hcov: coverage
	${BIN_DIR}/coverage html && ((which xdg-open && xdg-open htmlcov/index.html) || open htmlcov/index.html)

clean:
	for ITEM in ${JUNK}; do rm -r $${ITEM}; done; \
	for ITEM in ${RECURSIVE_JUNK}; do find . -name $${ITEM} -exec rm -r {} +; done
