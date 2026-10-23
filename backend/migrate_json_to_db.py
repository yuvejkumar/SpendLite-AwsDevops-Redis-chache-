import json
import logging
import os
import shutil
from datetime import datetime, timezone
import uuid

import config
from database import SessionLocal, init_db
from models import ExpenseDB

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("spendlite.migrate")


def migrate_json_to_database(json_path: str = None) -> int:
    """Migrates existing expense records from expenses.json to PostgreSQL.

    Returns the number of migrated records.
    """
    if json_path is None:
        json_path = config.DATA_FILE_PATH

    if not os.path.exists(json_path):
        logger.info("No legacy JSON file found at '%s'. Nothing to migrate.", json_path)
        return 0

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                logger.info("JSON file '%s' is empty. Nothing to migrate.", json_path)
                return 0
            records = json.loads(content)
    except Exception as e:
        logger.error("Failed to read JSON file '%s': %s", json_path, e)
        return 0

    if not isinstance(records, list) or len(records) == 0:
        logger.info("No expense entries found in '%s'.", json_path)
        return 0

    # Ensure tables exist
    init_db()

    migrated_count = 0
    db = SessionLocal()
    try:
        for item in records:
            item_id = str(item.get("id", uuid.uuid4()))
            existing = db.query(ExpenseDB).filter(ExpenseDB.id == item_id).first()
            if not existing:
                expense = ExpenseDB(
                    id=item_id,
                    title=item.get("title", "Untitled"),
                    amount=float(item.get("amount", 0.0)),
                    category=item.get("category", "Other"),
                    date=item.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                    created_at=item.get("created_at", datetime.now(timezone.utc).isoformat()),
                )
                db.add(expense)
                migrated_count += 1

        db.commit()
        logger.info(
            "Successfully migrated %d record(s) from JSON to PostgreSQL database.",
            migrated_count,
        )

        # Create a backup of the migrated file so data is preserved
        backup_path = f"{json_path}.migrated_backup"
        shutil.copy2(json_path, backup_path)
        logger.info("Created backup of legacy data at '%s'.", backup_path)
        return migrated_count
    except Exception as e:
        db.rollback()
        logger.error("Error during migration to database: %s", e)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("Running manual SpendLite JSON to PostgreSQL migration...")
    migrated = migrate_json_to_database()
    logger.info("Migration complete: %d records transferred.", migrated)
