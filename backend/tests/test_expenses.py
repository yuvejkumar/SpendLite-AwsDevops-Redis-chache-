import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from cache import RedisCacheManager
from main import app, get_cache, get_storage
from storage import JSONStorage


class InMemoryMockRedis:
    """A lightweight in-memory mock of the Redis client for isolated testing."""

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
    def setUp(self):
        # 1. Create a dedicated temporary directory for test storage
        self.test_dir = tempfile.mkdtemp()
        self.test_storage_path = os.path.join(self.test_dir, "test_expenses.json")
        self.storage = JSONStorage(self.test_storage_path)

        # 2. Setup mock Redis cache manager
        self.mock_redis = InMemoryMockRedis()
        self.cache_manager = RedisCacheManager(
            host="mock-redis",
            port=6379,
            ttl=60,
            key="spendlite:total_expenses",
            client=self.mock_redis,
        )

        # 3. Override FastAPI dependencies so tests use the isolated storage and cache
        app.dependency_overrides[get_storage] = lambda: self.storage
        app.dependency_overrides[get_cache] = lambda: self.cache_manager

        self.client = TestClient(app)

    def tearDown(self):
        # Clear FastAPI dependency overrides
        app.dependency_overrides.clear()
        # Clean up temporary test files
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_health_check(self):
        """Test GET /health returns 200 and healthy status."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["storage"], "ok")
        self.assertTrue(data["redis_connected"])

    def test_add_expense_valid(self):
        """Test POST /expenses successfully creates an expense."""
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

        # Verify it was persisted in isolated storage
        all_expenses = self.storage.get_all()
        self.assertEqual(len(all_expenses), 1)
        self.assertEqual(all_expenses[0]["id"], data["id"])

    def test_add_expense_validation(self):
        """Test POST /expenses rejects invalid payload (e.g., negative amount, empty title, invalid date)."""
        # Negative amount
        bad_amount = {
            "title": "Invalid",
            "amount": -50,
            "category": "Food",
            "date": "2026-10-23",
        }
        res = self.client.post("/expenses", json=bad_amount)
        self.assertEqual(res.status_code, 422)

        # Empty title
        empty_title = {
            "title": "   ",
            "amount": 100,
            "category": "Food",
            "date": "2026-10-23",
        }
        res = self.client.post("/expenses", json=empty_title)
        self.assertEqual(res.status_code, 422)

        # Invalid date format
        bad_date = {
            "title": "Movie",
            "amount": 250,
            "category": "Entertainment",
            "date": "23/10/2026",
        }
        res = self.client.post("/expenses", json=bad_date)
        self.assertEqual(res.status_code, 422)

    def test_list_expenses(self):
        """Test GET /expenses lists all stored expenses."""
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
        # Should be sorted latest first
        self.assertEqual(data[0]["title"], "Bus Pass")
        self.assertEqual(data[1]["title"], "Coffee")

    def test_delete_expense(self):
        """Test DELETE /expenses/{id} deletes the item and handles not found."""
        create_res = self.client.post(
            "/expenses",
            json={"title": "Book", "amount": 500.0, "category": "Education", "date": "2026-10-20"},
        )
        exp_id = create_res.json()["id"]

        # Delete the expense
        del_res = self.client.delete(f"/expenses/{exp_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["id"], exp_id)

        # Verify expense no longer in list
        list_res = self.client.get("/expenses")
        self.assertEqual(len(list_res.json()), 0)

        # Deleting again should return 404
        del_again = self.client.delete(f"/expenses/{exp_id}")
        self.assertEqual(del_again.status_code, 404)

    def test_calculate_total_and_redis_caching(self):
        """Test GET /expenses/total checks Redis, sets cache on miss, and hits cache on repeat call."""
        # Add 2 expenses
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
        self.assertFalse(data1["cached"])  # Cache Miss!
        self.assertEqual(self.mock_redis.store.get("spendlite:total_expenses"), "1000.0")

        # 2. Second call: Cache Hit
        second_call = self.client.get("/expenses/total")
        self.assertEqual(second_call.status_code, 200)
        data2 = second_call.json()
        self.assertEqual(data2["total"], 1000.00)
        self.assertTrue(data2["cached"])  # Cache Hit!

    def test_cache_invalidation_on_add_expense(self):
        """Test adding an expense invalidates the cached total in Redis."""
        # Prepopulate cache
        self.mock_redis.setex("spendlite:total_expenses", 60, "500.0")
        self.assertIn("spendlite:total_expenses", self.mock_redis.store)

        # Add a new expense
        self.client.post(
            "/expenses",
            json={"title": "Snack", "amount": 50.0, "category": "Food", "date": "2026-10-23"},
        )

        # Redis key should have been deleted (invalidated)
        self.assertNotIn("spendlite:total_expenses", self.mock_redis.store)
        self.assertIn("spendlite:total_expenses", self.mock_redis.delete_calls)

    def test_cache_invalidation_on_delete_expense(self):
        """Test deleting an expense invalidates the cached total in Redis."""
        # Create an expense
        create_res = self.client.post(
            "/expenses",
            json={"title": "Gym", "amount": 1200.0, "category": "Health", "date": "2026-10-23"},
        )
        exp_id = create_res.json()["id"]

        # Populate cache
        self.mock_redis.setex("spendlite:total_expenses", 60, "1200.0")
        self.assertIn("spendlite:total_expenses", self.mock_redis.store)

        # Delete the expense
        self.client.delete(f"/expenses/{exp_id}")

        # Redis key should have been deleted (invalidated)
        self.assertNotIn("spendlite:total_expenses", self.mock_redis.store)
        self.assertIn("spendlite:total_expenses", self.mock_redis.delete_calls)


if __name__ == "__main__":
    unittest.main()
