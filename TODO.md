# TODO

- README's "Dependencies" and "Makefile Pipeline" sections both say `make install` installs `requirements.txt` — that file doesn't exist. The repo migrated to `uv`/`pyproject.toml` (`install: uv sync`) but the README text wasn't updated to match.
- No CI — `make test` exists and there's a real `tests/` suite, but nothing runs it on push.
- `scripts/get-points.py` accepts `start_lat`/`start_lon` args that the README itself flags as "not used internally" — either wire them in or drop them from the CLI.
