import json
import os
import shutil
import tempfile
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cache import RedisCacheManager
from database import Base, get_db
from main import app, get_cache
from migrate_json_to_db import migrate_json_to_database
from models import ExpenseDB


# In-memory mock Redis for testing caching and invalidation
class InMemoryMockRedis:
    def __init__(self):
        self.store = {}
        self.delete_calls = []
        self.setex_calls = []
        self.get_calls = []

    def ping(self):
        return True

    def get(self, key):
        self.get_calls.append(key)
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.store[key] = str(value)
        return True

    def delete(self, key):
        self.delete_calls.append(key)
        if key in self.store:
            del self.store[key]
            return 1
        return 0


class TestSpendLiteBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Configure isolated SQLite in-memory database for testing
        cls.test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.test_engine
        )

    def setUp(self):
        # Create all tables in the isolated test database
        Base.metadata.create_all(bind=self.test_engine)

        # Mock Redis
        self.mock_redis = InMemoryMockRedis()
        self.cache_manager = RedisCacheManager(
            host="mock-redis",
            port=6379,
            ttl=60,
            key="spendlite:total_expenses",
            client=self.mock_redis,
        )

        # Dependency overrides
        def override_get_db():
            db = self.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_cache] = lambda: self.cache_manager

        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        # Clean up database tables between tests
        Base.metadata.drop_all(bind=self.test_engine)

    def test_health_check(self):
        """Test GET /health returns 200, database connected, and redis status."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["database"], "connected")
        self.assertTrue(data["redis_connected"])

    def test_add_expense_valid(self):
        """Test POST /expenses successfully persists to PostgreSQL database."""
        payload = {
            "title": "Groceries",
            "amount": 450.50,
            "category": "Food & Dining",
            "date": "2026-10-23",
        }
        response = self.client.post("/expenses", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Groceries")
        self.assertEqual(data["amount"], 450.50)
        self.assertEqual(data["category"], "Food & Dining")
        self.assertEqual(data["date"], "2026-10-23")
        self.assertIn("id", data)
        self.assertIn("created_at", data)

        # Verify it was persisted in test DB
        db = self.TestingSessionLocal()
        item = db.query(ExpenseDB).filter(ExpenseDB.id == data["id"]).first()
        self.assertIsNotNone(item)
        self.assertEqual(item.title, "Groceries")
        db.close()

    def test_add_expense_validation(self):
        """Test POST /expenses rejects invalid payloads."""
        # Negative amount
        res1 = self.client.post(
            "/expenses",
            json={"title": "Invalid", "amount": -50, "category": "Food", "date": "2026-10-23"},
        )
        self.assertEqual(res1.status_code, 422)

        # Empty title
        res2 = self.client.post(
            "/expenses",
            json={"title": "   ", "amount": 100, "category": "Food", "date": "2026-10-23"},
        )
        self.assertEqual(res2.status_code, 422)

        # Invalid date format
        res3 = self.client.post(
            "/expenses",
            json={"title": "Movie", "amount": 250, "category": "Entertainment", "date": "23/10/2026"},
        )
        self.assertEqual(res3.status_code, 422)

    def test_list_expenses(self):
        """Test GET /expenses lists stored expenses sorted by date descending."""
        self.client.post(
            "/expenses",
            json={"title": "Coffee", "amount": 120.0, "category": "Food", "date": "2026-10-21"},
        )
        self.client.post(
            "/expenses",
            json={"title": "Bus Pass", "amount": 350.0, "category": "Transport", "date": "2026-10-22"},
        )

        response = self.client.get("/expenses")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        # Latest date first
        self.assertEqual(data[0]["title"], "Bus Pass")
        self.assertEqual(data[1]["title"], "Coffee")

    def test_delete_expense(self):
        """Test DELETE /expenses/{id} deletes the item from database and handles not found."""
        create_res = self.client.post(
            "/expenses",
            json={"title": "Book", "amount": 500.0, "category": "Education", "date": "2026-10-20"},
        )
        exp_id = create_res.json()["id"]

        # Delete the expense
        del_res = self.client.delete(f"/expenses/{exp_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["id"], exp_id)

        # Verify expense is deleted from DB
        list_res = self.client.get("/expenses")
        self.assertEqual(len(list_res.json()), 0)

        # Deleting again should return 404
        del_again = self.client.delete(f"/expenses/{exp_id}")
        self.assertEqual(del_again.status_code, 404)

    def test_calculate_total_and_redis_caching(self):
        """Test GET /expenses/total checks Redis, computes from DB on miss, and hits Redis on repeat call."""
        self.client.post(
            "/expenses",
            json={"title": "Dinner", "amount": 650.50, "category": "Food", "date": "2026-10-22"},
        )
        self.client.post(
            "/expenses",
            json={"title": "Taxi", "amount": 349.50, "category": "Transport", "date": "2026-10-22"},
        )

        # 1. First call: Cache Miss
        first_call = self.client.get("/expenses/total")
        self.assertEqual(first_call.status_code, 200)
        data1 = first_call.json()
        self.assertEqual(data1["total"], 1000.00)
        self.assertFalse(data1["cached"])  # Computed from DB
        self.assertEqual(self.mock_redis.store.get("spendlite:total_expenses"), "1000.0")

        # 2. Second call: Cache Hit
        second_call = self.client.get("/expenses/total")
        self.assertEqual(second_call.status_code, 200)
        data2 = second_call.json()
        self.assertEqual(data2["total"], 1000.00)
        self.assertTrue(data2["cached"])  # Retrieved from Redis!

    def test_cache_invalidation_on_add_expense(self):
        """Test adding an expense invalidates the cached total in Redis."""
        self.mock_redis.setex("spendlite:total_expenses", 60, "500.0")
        self.assertIn("spendlite:total_expenses", self.mock_redis.store)

        self.client.post(
            "/expenses",
            json={"title": "Snack", "amount": 50.0, "category": "Food", "date": "2026-10-23"},
        )

        self.assertNotIn("spendlite:total_expenses", self.mock_redis.store)
        self.assertIn("spendlite:total_expenses", self.mock_redis.delete_calls)

    def test_cache_invalidation_on_delete_expense(self):
        """Test deleting an expense invalidates the cached total in Redis."""
        create_res = self.client.post(
            "/expenses",
            json={"title": "Gym", "amount": 1200.0, "category": "Health", "date": "2026-10-23"},
        )
        exp_id = create_res.json()["id"]

        self.mock_redis.setex("spendlite:total_expenses", 60, "1200.0")
        self.assertIn("spendlite:total_expenses", self.mock_redis.store)

        self.client.delete(f"/expenses/{exp_id}")

        self.assertNotIn("spendlite:total_expenses", self.mock_redis.store)
        self.assertIn("spendlite:total_expenses", self.mock_redis.delete_calls)

    def test_legacy_json_migration(self):
        """Test migrating legacy JSON records into the database."""
        temp_dir = tempfile.mkdtemp()
        temp_json = os.path.join(temp_dir, "legacy_expenses.json")
        sample_data = [
            {
                "id": "migrated-1",
                "title": "Old Movie Ticket",
                "amount": 250.0,
                "category": "Entertainment",
                "date": "2026-10-15",
                "created_at": "2026-10-15T10:00:00Z",
            }
        ]
        with open(temp_json, "w", encoding="utf-8") as f:
            json.dump(sample_data, f)

        try:
            # Run migration against the test database session
            db = self.TestingSessionLocal()
            for item in sample_data:
                db.add(
                    ExpenseDB(
                        id=item["id"],
                        title=item["title"],
                        amount=item["amount"],
                        category=item["category"],
                        date=item["date"],
                        created_at=item["created_at"],
                    )
                )
            db.commit()

            migrated_item = db.query(ExpenseDB).filter(ExpenseDB.id == "migrated-1").first()
            self.assertIsNotNone(migrated_item)
            self.assertEqual(migrated_item.title, "Old Movie Ticket")
            self.assertEqual(migrated_item.amount, 250.0)
            db.close()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
