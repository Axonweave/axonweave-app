"""Export OpenAPI schema to openapi.json for frontend type generation."""

import json
import sys
from pathlib import Path

# Ensure the backend directory is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

output_path = Path(__file__).resolve().parent.parent / "openapi.json"
schema = app.openapi()

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(schema, f, indent=2)

print(f"OpenAPI schema written to {output_path}")
