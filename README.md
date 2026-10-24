# Hypermediator

Makes the correct, machine-operable path the default in HTML applications built for people and enhanced with htmx. See [docs/PRINCIPLES.md](docs/PRINCIPLES.md).

## Development

Requires [uv](https://docs.astral.sh/uv/). Python 3.14 and Django 6.1.

```bash
uv sync            # create .venv and install dependencies
uv run pytest      # tests
uv run ruff check  # lint
uv run ruff format # format
uv run mypy        # type-check
uv build           # build sdist and wheel
```
