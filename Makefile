.PHONY: install uninstall test test-q lint lint-fix format format-check typecheck check validate clean precommit test-auth test-integration test-rekordbox

install:
	uv tool install -e "." --quiet

uninstall:
	uv tool uninstall djdl

test:
	uv run pytest tests/ -v

test-q:
	uv run pytest tests/ -q

lint:
	uv run ruff check dj_dl/ tests/

lint-fix:
	uv run ruff check --fix dj_dl/ tests/

format:
	uv run ruff format dj_dl/ tests/

format-check:
	uv run ruff format --check dj_dl/ tests/

typecheck:
	uv run ty check dj_dl/ tests/

check: lint format-check typecheck

validate: lint-fix format typecheck test

clean:
	rm -rf tests/results/*.m4a
	rm -rf tests/results/*/
	rm -rf gamdl_temp_*/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

precommit:
	uv run pre-commit install

test-auth:
	uv run pytest tests/test_auth.py -v

test-integration:
	uv run pytest tests/test_integration.py -v

test-rekordbox:
	uv run pytest tests/test_rekordbox_xml.py tests/test_rekordbox_integration.py -v