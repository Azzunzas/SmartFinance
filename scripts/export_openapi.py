import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.main import app

output = Path(__file__).resolve().parent.parent / "web" / "openapi.json"
output.write_text(json.dumps(app.openapi(), indent=2))
print(f"OpenAPI schema escrito em {output}")
