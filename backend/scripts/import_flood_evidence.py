"""Import the flood evidence register CSV: python -m scripts.import_flood_evidence [path.csv]

Without a path it loads every CSV in datasets/flood_evidence/. Safe to re-run: rows update by record_id.
"""

import sys
from pathlib import Path

from app.database import SessionLocal
from app.services import flood_evidence


def main() -> None:
    paths = [Path(sys.argv[1])] if len(sys.argv) > 1 else flood_evidence.bundled_files()
    with SessionLocal() as db:
        for path in paths:
            result = flood_evidence.import_text(db, path.read_text(encoding="utf-8-sig"))
            print(f"{path.name}: added {result['added']}, updated {result['updated']}, adjusted/skipped {result['skipped_or_adjusted']}")
            for line in result["problems"]:
                print("  -", line)
        db.commit()


if __name__ == "__main__":
    main()
