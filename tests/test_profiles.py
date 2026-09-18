"""Unit tests for sensitivity profiles."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from profiles import (
    DEFAULT_PROFILE,
    delete_profile,
    get_profile_names,
    load_profile,
    save_profile,
)


class TestProfiles(unittest.TestCase):
    """Tests for the profile management system."""

    def setUp(self):
        # Use a temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        # Patch the PROFILES_DIR in the module
        import profiles
        self.original_dir = profiles.PROFILES_DIR
        profiles.PROFILES_DIR = self.temp_path

    def tearDown(self):
        # Restore original directory
        import profiles
        profiles.PROFILES_DIR = self.original_dir
        # Clean up temp directory
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_profile(self):
        """Default profile should have all required keys."""
        self.assertEqual(DEFAULT_PROFILE["name"], "default")
        self.assertIn("SWIPE_THRESHOLD", DEFAULT_PROFILE)
        self.assertIn("GESTURE_COOLDOWN_SEC", DEFAULT_PROFILE)

    def test_load_default_profile(self):
        """load_profile('default') should return default profile."""
        result = load_profile("default")
        self.assertEqual(result["name"], "default")
        self.assertEqual(result["SWIPE_THRESHOLD"], DEFAULT_PROFILE["SWIPE_THRESHOLD"])

    def test_save_and_load_profile(self):
        """save_profile should persist, load_profile should restore."""
        settings = dict(DEFAULT_PROFILE)
        settings["SWIPE_THRESHOLD"] = 0.08
        save_profile("custom", settings)

        loaded = load_profile("custom")
        self.assertEqual(loaded["name"], "custom")
        self.assertEqual(loaded["SWIPE_THRESHOLD"], 0.08)

    def test_get_profile_names(self):
        """get_profile_names should return default plus saved profiles."""
        names = get_profile_names()
        self.assertIn("default", names)

        save_profile("test_profile", DEFAULT_PROFILE)
        names = get_profile_names()
        self.assertIn("test_profile", names)

    def test_delete_profile(self):
        """delete_profile should remove a saved profile."""
        save_profile("to_delete", DEFAULT_PROFILE)
        self.assertTrue(delete_profile("to_delete"))
        self.assertFalse(delete_profile("to_delete"))  # Already deleted

    def test_delete_default_profile_fails(self):
        """delete_profile should not allow deleting 'default'."""
        self.assertFalse(delete_profile("default"))

    def test_load_nonexistent_profile_returns_default(self):
        """Loading a nonexistent profile should return default."""
        result = load_profile("nonexistent")
        self.assertEqual(result["SWIPE_THRESHOLD"], DEFAULT_PROFILE["SWIPE_THRESHOLD"])


class TestProfileEndpoints(unittest.TestCase):
    """Tests for the profile API endpoints."""

    def setUp(self):
        from runtime import config
        config.reset()

        from web.server import app
        self.app = app.test_client()

    def test_get_profiles(self):
        """GET /api/profiles should return list of profiles."""
        response = self.app.get("/api/profiles")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertIn("profiles", data)
        self.assertIn("default", data["profiles"])

    def test_get_profile(self):
        """GET /api/profiles/<name> should return profile details."""
        response = self.app.get("/api/profiles/default")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertIn("profile", data)
        self.assertEqual(data["profile"]["name"], "default")

    def test_create_profile(self):
        """POST /api/profiles/<name> should create a new profile."""
        new_profile = {
            "settings": {
                "SWIPE_THRESHOLD": 0.06,
                "GESTURE_COOLDOWN_SEC": 1.2,
            }
        }
        response = self.app.post(
            "/api/profiles/test",
            data=json.dumps(new_profile),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "ok")

    def test_activate_profile(self):
        """POST /api/profiles/<name>/activate should apply profile settings."""
        # First create a profile
        new_profile = {
            "settings": {
                "SWIPE_THRESHOLD": 0.07,
            }
        }
        self.app.post(
            "/api/profiles/activate_test",
            data=json.dumps(new_profile),
            content_type="application/json"
        )

        # Activate it
        response = self.app.post("/api/profiles/activate_test/activate")
        self.assertEqual(response.status_code, 200)

        # Check that runtime config was updated
        from runtime import config
        self.assertAlmostEqual(config.get("SWIPE_THRESHOLD", 0.04), 0.07)

    def test_delete_profile_endpoint(self):
        """DELETE /api/profiles/<name> should delete a profile."""
        # Create a profile first
        self.app.post(
            "/api/profiles/to_delete",
            data=json.dumps({"settings": {}}),
            content_type="application/json"
        )

        # Delete it
        response = self.app.delete("/api/profiles/to_delete")
        self.assertEqual(response.status_code, 200)

        # Verify it's gone
        response = self.app.get("/api/profiles/to_delete")
        data = json.loads(response.data)
        # Should return default since profile doesn't exist
        self.assertEqual(data["profile"]["name"], "default")


if __name__ == "__main__":
    unittest.main()
