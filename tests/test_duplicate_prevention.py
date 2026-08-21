"""Tests for duplicate download prevention."""
import pytest
from unittest.mock import Mock, patch
from services.watchlist import WatchlistService, WatchlistEntry, WatchlistData, VALID_STATES, VALID_TRANSITIONS
from core.exceptions import DuplicateError, StateTransitionError


class TestDuplicatePrevention:
    """Test duplicate prevention in watchlist and download."""

    def setup_method(self):
        self.wl = WatchlistService("/tmp/test_watchlist.json")
        # Clean up any existing test file
        import os
        if os.path.exists("/tmp/test_watchlist.json"):
            os.remove("/tmp/test_watchlist.json")

    def teardown_method(self):
        import os
        if os.path.exists("/tmp/test_watchlist.json"):
            os.remove("/tmp/test_watchlist.json")

    def test_add_duplicate_imdb_id_raises(self):
        """Adding entry with same imdbId should raise DuplicateError."""
        entry1 = WatchlistEntry(
            title="The Matrix", year=1999, category="Action", lang="English",
            rt=88, imdb=8.7, isSeries=False, imdbId="tt0133093", tmdbId=603,
            cert="R", snippet="A hacker discovers reality is a simulation.",
            cast=["Keanu Reeves"], director="Lana Wachowski",
            poster="", trailerId="", trailerTitle="", added="2026-01-01"
        )
        entry2 = WatchlistEntry(
            title="The Matrix (Duplicate)", year=1999, category="Sci-Fi", lang="English",
            rt=88, imdb=8.7, isSeries=False, imdbId="tt0133093", tmdbId=603,
            cert="R", snippet="Duplicate entry.", cast=[], director="",
            poster="", trailerId="", trailerTitle="", added="2026-01-02"
        )

        self.wl.add_pending(entry1)
        with pytest.raises(DuplicateError):
            self.wl.add_pending(entry2)

    def test_find_by_imdb_finds_in_pending(self):
        """find_by_imdb should find entries in pending."""
        entry = WatchlistEntry(
            title="Inception", year=2010, category="Sci-Fi", lang="English",
            rt=87, imdb=8.8, isSeries=False, imdbId="tt1375666", tmdbId=27205,
            cert="PG-13", snippet="Dream heist.", cast=["Leonardo DiCaprio"], director="Christopher Nolan",
            poster="", trailerId="", trailerTitle="", added="2026-01-01"
        )
        self.wl.add_pending(entry)
        found = self.wl.find_by_imdb("tt1375666")
        assert found is not None
        assert found.title == "Inception"

    def test_find_by_imdb_finds_in_recommended(self):
        """find_by_imdb should find entries in recommended."""
        entry = WatchlistEntry(
            title="Inception", year=2010, category="Sci-Fi", lang="English",
            rt=87, imdb=8.8, isSeries=False, imdbId="tt1375666", tmdbId=27205,
            cert="PG-13", snippet="Dream heist.", cast=["Leonardo DiCaprio"], director="Christopher Nolan",
            poster="", trailerId="", trailerTitle="", added="2026-01-01",
            state="recommended", completed="2026-01-15"
        )
        # Manually add to recommended for test
        data = self.wl.load()
        data.recommended.append(entry)
        self.wl.save(data)

        found = self.wl.find_by_imdb("tt1375666")
        assert found is not None
        assert found.state == "recommended"

    def test_state_transitions_valid(self):
        """Valid state transitions should work."""
        entry = WatchlistEntry(
            title="Test", year=2020, category="Action", lang="English",
            rt=80, imdb=7.5, isSeries=False, imdbId="tt1234567", tmdbId=12345,
            cert="", snippet="", cast=[], director="",
            poster="", trailerId="", trailerTitle="", added="2026-01-01",
            state="pending"
        )
        self.wl.add_pending(entry)

        # pending -> requested
        assert self.wl.update_status("tt1234567", "requested") is True
        data = self.wl.load()
        assert data.pending[0].state == "requested"

        # requested -> downloading
        assert self.wl.update_status("tt1234567", "downloading") is True
        data = self.wl.load()
        assert data.pending[0].state == "downloading"

        # downloading -> downloaded
        assert self.wl.update_status("tt1234567", "downloaded") is True
        data = self.wl.load()
        assert data.pending[0].state == "downloaded"

        # downloaded -> available
        assert self.wl.update_status("tt1234567", "available") is True
        data = self.wl.load()
        assert data.pending[0].state == "available"

        # available -> recommended
        assert self.wl.update_status("tt1234567", "recommended") is True
        data = self.wl.load()
        # Should be moved to recommended
        assert len(data.pending) == 0
        assert len(data.recommended) == 1
        assert data.recommended[0].state == "recommended"

    def test_state_transitions_invalid_raises(self):
        """Invalid state transitions should raise StateTransitionError."""
        entry = WatchlistEntry(
            title="Test", year=2020, category="Action", lang="English",
            rt=80, imdb=7.5, isSeries=False, imdbId="tt1234567", tmdbId=12345,
            cert="", snippet="", cast=[], director="",
            poster="", trailerId="", trailerTitle="", added="2026-01-01",
            state="pending"
        )
        self.wl.add_pending(entry)

        # pending -> available (invalid, must go through requested/downloading/downloaded)
        with pytest.raises(StateTransitionError):
            self.wl.update_status("tt1234567", "available")

    def test_move_to_recommended_removes_from_pending(self):
        """move_to_recommended should move entry from pending to recommended."""
        entry = WatchlistEntry(
            title="Completed Movie", year=2020, category="Drama", lang="English",
            rt=90, imdb=8.5, isSeries=False, imdbId="tt7654321", tmdbId=54321,
            cert="", snippet="", cast=[], director="",
            poster="", trailerId="", trailerTitle="", added="2026-01-01",
            state="available"
        )
        self.wl.add_pending(entry)

        success = self.wl.move_to_recommended("tt7654321", "2026-01-15")
        assert success is True

        data = self.wl.load()
        assert len(data.pending) == 0
        assert len(data.recommended) == 1
        assert data.recommended[0].title == "Completed Movie"
        assert data.recommended[0].completed == "2026-01-15"
        assert data.recommended[0].state == "recommended"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])