import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spendlite.storage")


class JSONStorage:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._lock = threading.Lock()
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Create parent directory and initialize empty JSON array file if missing."""
        dir_name = os.path.dirname(self.file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)
            logger.info("Initialized new JSON storage at %s", self.file_path)

    def get_all(self) -> List[Dict[str, Any]]:
        """Read and return all expenses from the JSON file."""
        with self._lock:
            self._ensure_file_exists()
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        return []
                    data = json.loads(content)
                    if isinstance(data, list):
                        return data
                    return []
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Error reading JSON file %s: %s", self.file_path, e)
                return []

    def save_all(self, expenses: List[Dict[str, Any]]) -> None:
        """Atomically save expenses list to the JSON file."""
        with self._lock:
            self._ensure_file_exists()
            temp_path = f"{self.file_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(expenses, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, self.file_path)

    def add(self, expense: Dict[str, Any]) -> Dict[str, Any]:
        """Append a new expense and persist to disk."""
        with self._lock:
            self._ensure_file_exists()
            expenses = []
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        expenses = json.loads(content)
            except Exception:
                expenses = []
            expenses.append(expense)
            temp_path = f"{self.file_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(expenses, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, self.file_path)
            return expense

    def delete(self, expense_id: str) -> bool:
        """Delete an expense by ID. Returns True if deleted, False if not found."""
        with self._lock:
            self._ensure_file_exists()
            expenses = []
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        expenses = json.loads(content)
            except Exception:
                expenses = []

            original_count = len(expenses)
            expenses = [item for item in expenses if str(item.get("id")) != str(expense_id)]
            if len(expenses) < original_count:
                temp_path = f"{self.file_path}.tmp"
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(expenses, f, indent=2, ensure_ascii=False)
                os.replace(temp_path, self.file_path)
                return True
            return False

    def calculate_total(self) -> float:
        """Calculate total amount from stored expenses."""
        expenses = self.get_all()
        total = sum(float(exp.get("amount", 0.0)) for exp in expenses)
        return round(total, 2)
