import gen_schemas  # importable because pyproject.toml puts tools/ on pytest's pythonpath


def test_committed_schemas_match_the_models():
    for name, expected in gen_schemas.render().items():
        committed = (gen_schemas.OUT / name).read_text(encoding="utf-8")
        assert committed == expected, (
            f"{name} is out of date: run `python tools/gen_schemas.py` and commit the result"
        )
