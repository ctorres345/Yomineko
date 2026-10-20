#!/usr/bin/env python3
"""Write the JSON Schemas for the script and profile formats into src/yomineko/schemas/.

Run after changing src/yomineko/model.py or src/yomineko/profile/schema.py.
tests/test_schemas.py fails when the committed files differ from the models.
"""

import json
from pathlib import Path

from yomineko.model import Script
from yomineko.profile.schema import Profile

OUT = Path(__file__).resolve().parents[1] / "src" / "yomineko" / "schemas"


def render() -> dict[str, str]:
    """File name -> exact file content."""
    schemas = {
        "script.v4.schema.json": Script.model_json_schema(),
        "profile.v1.schema.json": Profile.model_json_schema(),
    }
    return {
        name: json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        for name, schema in schemas.items()
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in render().items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
