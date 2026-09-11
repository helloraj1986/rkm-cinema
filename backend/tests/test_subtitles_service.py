"""Subtitle delivery tests (SUBTITLES_OPENSUBTITLES_PLAN Phase 2).

No network and no real media drive: the OpenSubtitles client and the library are both
fakes, and the "media folder" is a ``tmp_path`` directory. What is asserted here is
the behaviour the plan calls out as the riskiest part of the feature:

* the sidecar is written atomically, in UTF-8, next to the media file, and a
  half-written file can never be seen by Jellyfin's scanner;
* an existing same-language sidecar is REUSED — no download, no quota, and the user's
  own subtitle file is not touched;
* the ITEM is refreshed and a library-wide scan is NEVER triggered (that is what
  cancels an in-flight scan and leaves the library half-indexed for hours);
* when no sidecar can be written, the bytes are uploaded to the server instead of the
  request failing;
* a payload that is not a subtitle (an HTML error page) is refused rather than written;
* stream indices are POSITIONAL, so a stored identity resolves to whatever index the
  track now has — or to nothing, never to a different subtitle.
"""
from pathlib import Path

import pytest

from services.opensubtitles import DownloadedSubtitle, OpenSubtitlesError, UnsupportedFormatError
from services.subtitles import (AttachResult, SubtitleService, decode_subtitle,
                                looks_like_subtitle_text, normalise_language,
                                resolve_active_track, sidecar_path_for, write_atomic)

SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n\n2\n00:00:03,000 --> 00:00:04,000\nWorld\n"
MOVIE = "Movie.2019.1080p.WEB-DL.srt"


class FakeClient:
    """Records downloads; returns scripted bytes. No network."""

    def __init__(self, content: bytes = SRT, file_name: str = MOVIE, remaining=4,
                 error: Exception = None):
        self.content, self.file_name, self.remaining, self.error = content, file_name, remaining, error
        self.downloads = []
        self._quota = None

    def download(self, file_id, **kw):
        self.downloads.append(file_id)
        if self.error:
            raise self.error
        self._quota = self.remaining
        return DownloadedSubtitle(file_id=file_id, file_name=self.file_name,
                                  content=self.content, remaining=self.remaining,
                                  reset_time_utc="2026-09-13T00:00:00Z")

    def last_quota(self):
        return self._quota


class FakeLibrary:
    """Records the calls the service is allowed (and not allowed) to make."""

    def __init__(self, path="/data/Movies/Movie.2019.1080p.WEB-DL.mp4", tracks=None,
                 refresh_ok=True, upload_ok=True, write_blocked=False):
        self.path = path
        self.tracks = tracks if tracks is not None else [
            {"index": 2, "name": "English", "language": "eng"}]
        self.refresh_ok, self.upload_ok = refresh_ok, upload_ok
        self.item_refreshes = []
        self.library_scans = 0
        self.uploads = []
        self.playback_reads = 0

    # the read-only surface the service uses
    def item_path(self, item_id):
        return self.path

    def refresh_item(self, item_id):
        self.item_refreshes.append(item_id)
        return self.refresh_ok

    def upload_subtitle(self, item_id, file_name, content, language="", format=""):
        self.uploads.append((item_id, file_name, content))
        return self.upload_ok

    def playback_info(self, item_id):
        self.playback_reads += 1
        return {"subtitles": list(self.tracks), "media_source_id": "ms1"}

    # the one call that must NEVER happen from this service
    def refresh_library(self):  # pragma: no cover - asserted against
        self.library_scans += 1
        return True


def service(tmp_path, *, content=SRT, file_name=MOVIE, tracks=None, path=None,
            refresh_ok=True, upload_ok=True, error=None):
    media = tmp_path / "Movies"
    media.mkdir(exist_ok=True)
    video = path if path is not None else str(media / "Movie.2019.1080p.WEB-DL.mp4")
    client = FakeClient(content=content, file_name=file_name, error=error)
    library = FakeLibrary(path=video, tracks=tracks, refresh_ok=refresh_ok, upload_ok=upload_ok)
    return SubtitleService(client=client, library=library), client, library, video


# --------------------------------------------------------------------- pure helpers
class TestSidecarNaming:
    def test_basic_name(self):
        assert sidecar_path_for("/data/Movies/Film.2009.mp4", "en") == "/data/Movies/Film.2009.en.srt"

    def test_language_is_lowercased_and_short(self):
        assert sidecar_path_for("/data/Movies/Film.mkv", "EN") == "/data/Movies/Film.en.srt"
        assert sidecar_path_for("/data/Movies/Film.mkv", "eng") == "/data/Movies/Film.eng.srt"

    def test_a_stem_that_already_carries_the_tag_is_not_doubled(self):
        assert sidecar_path_for("/data/Film.2009.en.mp4", "en") == "/data/Film.2009.en.srt"

    def test_a_different_extension_can_be_asked_for(self):
        assert sidecar_path_for("/data/Film.mp4", "en", ext="vtt") == "/data/Film.en.vtt"

    def test_paths_with_spaces_survive(self):
        assert sidecar_path_for("/media2/TV Shows/Show/Episode 1.mkv", "en") \
            == "/media2/TV Shows/Show/Episode 1.en.srt"


class TestDecode:
    def test_utf8_passthrough(self):
        text, enc = decode_subtitle(SRT)
        assert enc == "utf-8" and text.startswith("1\n00:00:01,000")

    def test_a_utf8_bom_is_removed(self):
        text, enc = decode_subtitle(b"\xef\xbb\xbf" + SRT)
        assert enc == "utf-8-sig" and text.startswith("1\n")

    def test_utf16_is_detected_and_decoded(self):
        text, enc = decode_subtitle(SRT.decode().encode("utf-16"))
        assert enc == "utf-16" and "Hello" in text

    def test_cp1252_fallback_for_an_old_rip(self):
        """A latin-1 'smart quote' is not valid UTF-8 — it must still decode."""
        text, enc = decode_subtitle("1\n00:00:01,000 --> 00:00:02,000\nIt’s here\n".encode("cp1252"))
        assert enc in ("cp1252", "latin-1") and "It’s here" in text

    def test_crlf_is_normalised_and_the_file_is_terminated(self):
        text, _ = decode_subtitle(b"1\r\n00:00:01,000 --> 00:00:02,000\r\nHi")
        assert "\r" not in text and text.endswith("\n")

    def test_a_real_download_shape_is_accepted(self):
        text, _ = decode_subtitle(SRT)
        assert looks_like_subtitle_text(text)

    def test_an_html_error_page_is_not_a_subtitle(self):
        assert not looks_like_subtitle_text("<!DOCTYPE html><html><body>403</body></html>")

    def test_ass_files_are_recognised(self):
        assert looks_like_subtitle_text("[Script Info]\nTitle: x\nDialogue: 0,0:00:01.00,...")


class TestAtomicWrite:
    def test_writes_utf8_and_leaves_no_temp_file(self, tmp_path):
        target = tmp_path / "Film.en.srt"
        write_atomic(str(target), "1\n00:00:01,000 --> 00:00:02,000\ncafé\n")
        assert target.read_text(encoding="utf-8").endswith("café\n")
        assert list(tmp_path.glob("*.rkm-tmp")) == []

    def test_replaces_an_existing_file(self, tmp_path):
        target = tmp_path / "Film.en.srt"
        target.write_text("old", encoding="utf-8")
        write_atomic(str(target), "new")
        assert target.read_text(encoding="utf-8") == "new"


class TestResolveActiveTrack:
    """Indices are positional; identity is what we store (§3.6)."""

    TRACKS = [
        {"index": 0, "name": "English", "language": "eng"},
        {"index": 1, "name": "English (SDH)", "language": "eng"},
        {"index": 2, "name": "Movie.2019.1080p.WEB-DL", "language": "en"},
    ]

    def test_an_exact_title_match_wins(self):
        assert resolve_active_track(self.TRACKS, display_title="Movie.2019.1080p.WEB-DL") == 2

    def test_a_moved_index_still_resolves_by_identity(self):
        """The whole point: indices shift when tracks are added or removed."""
        moved = [{"index": 7, "name": "Movie.2019.1080p.WEB-DL", "language": "en"}]
        assert resolve_active_track(moved, display_title="Movie.2019.1080p.WEB-DL") == 7

    def test_same_language_is_the_second_choice(self):
        assert resolve_active_track(self.TRACKS, language="en") == 0

    def test_no_match_applies_nothing_rather_than_a_different_subtitle(self):
        assert resolve_active_track(self.TRACKS, display_title="Some.Other.Release",
                                    language="fr") is None

    def test_no_tracks(self):
        assert resolve_active_track([], display_title="x") is None

    def test_language_normalisation_helper(self):
        """OpenSubtitles speaks 639-1, a media server reports 639-2/B."""
        assert normalise_language("EN") == "en"
        assert normalise_language("eng") == "en"
        assert normalise_language("hin") == "hi"
        assert normalise_language("tam") == "ta"
        assert normalise_language("pt-BR") == "pt"
        assert normalise_language("GER") == "de"          # prefix would give "ge"
        assert normalise_language("fre") == "fr"
        assert normalise_language("") == ""


# ------------------------------------------------------------------------- attach
class TestAttach:
    def test_sidecar_is_written_beside_the_media_and_the_item_is_refreshed(self, tmp_path):
        svc, client, library, video = service(tmp_path)
        res = svc.attach(item_id="ITEM1", file_id=111, language="en",
                         display_title=MOVIE)
        sidecar = Path(video).with_name("Movie.2019.1080p.WEB-DL.en.srt")
        assert sidecar.exists()
        assert sidecar.read_text(encoding="utf-8").startswith("1\n00:00:01,000")
        assert res.delivered == "sidecar" and res.ok and not res.reused
        assert res.sidecar_path == str(sidecar)
        assert library.item_refreshes == ["ITEM1"]
        assert client.downloads == [111]
        assert res.remaining == 4
        assert res.tracks == library.tracks          # refreshed tracks come back

    def test_a_library_scan_is_never_triggered(self, tmp_path):
        svc, _, library, _ = service(tmp_path)
        svc.attach(item_id="ITEM1", file_id=111, language="en")
        assert library.library_scans == 0, "attach() must never rescan the library"

    def test_the_result_carries_the_identity_the_store_persists(self, tmp_path):
        svc, _, _, _ = service(tmp_path)
        res = svc.attach(item_id="ITEM1", file_id=111, language="en",
                         display_title="Movie.2019.1080p.WEB-DL", subtitle_id="os:111")
        payload = res.to_dict()
        assert payload["subtitle_id"] == "os:111"
        assert payload["display_title"] == "Movie.2019.1080p.WEB-DL"
        assert payload["language"] == "en"
        assert payload["subtitles"] == svc.library.tracks

    def test_an_existing_sidecar_is_reused_without_spending_a_download(self, tmp_path):
        svc, client, library, video = service(tmp_path)
        existing = Path(video).with_name("Movie.2019.1080p.WEB-DL.en.srt")
        existing.write_text("1\n00:00:01,000 --> 00:00:02,000\nmine\n", encoding="utf-8")
        res = svc.attach(item_id="ITEM1", file_id=111, language="en")
        assert res.reused is True and res.delivered == "sidecar"
        assert client.downloads == [], "a repeat request must not spend a download"
        assert "mine" in existing.read_text(encoding="utf-8"), "the user's file was touched"

    def test_replace_existing_overwrites_the_same_language_sidecar(self, tmp_path):
        svc, client, _, video = service(tmp_path)
        existing = Path(video).with_name("Movie.2019.1080p.WEB-DL.en.srt")
        existing.write_text("old subtitle\n", encoding="utf-8")
        res = svc.attach(item_id="ITEM1", file_id=222, language="en", replace_existing=True)
        assert res.reused is False and client.downloads == [222]
        assert "Hello" in existing.read_text(encoding="utf-8")

    def test_a_different_language_gets_its_own_sidecar(self, tmp_path):
        svc, _, _, video = service(tmp_path)
        svc.attach(item_id="ITEM1", file_id=111, language="en")
        svc.attach(item_id="ITEM1", file_id=222, language="hi")
        names = sorted(p.name for p in Path(video).parent.glob("*.srt"))
        assert names == ["Movie.2019.1080p.WEB-DL.en.srt", "Movie.2019.1080p.WEB-DL.hi.srt"]

    def test_attach_without_an_item_id_is_a_programming_error(self):
        with pytest.raises(ValueError):
            SubtitleService(client=FakeClient(), library=FakeLibrary()).attach(
                item_id="", file_id=1, language="en")


class TestDeliveryFallback:
    @staticmethod
    def _block_sidecar(video_path: str) -> None:
        """Make the SIDECAR path unwritable by putting a directory where it belongs.

        A real-world stand-in: media outside the api's mounts, or a read-only bind.
        """
        Path(sidecar_path_for(video_path, "en")).mkdir()

    def test_without_a_resolvable_path_the_bytes_are_uploaded_to_the_server(self, tmp_path):
        svc, client, library, _ = service(tmp_path, path=None)
        library.path = None                       # the server cannot report a file path
        res = svc.attach(item_id="ITEM1", file_id=111, language="en")
        assert res.delivered == "upload"
        assert library.uploads == [("ITEM1", MOVIE, SRT)]
        assert client.downloads == [111]

    def test_an_unwritable_sidecar_falls_back_to_the_upload(self, tmp_path):
        """Media outside the api's mounts is a real state — degrade, don't fail."""
        svc, _, library, video = service(tmp_path)
        Path(video).unlink(missing_ok=True)
        self._block_sidecar(video)                # the sidecar path is unwritable
        res = svc.attach(item_id="ITEM1", file_id=111, language="en")
        assert res.delivered == "upload" and library.uploads

    def test_no_delivery_route_at_all_is_a_clear_error(self, tmp_path):
        svc, _, library, video = service(tmp_path, upload_ok=False)
        Path(video).unlink(missing_ok=True)
        self._block_sidecar(video)
        with pytest.raises(UnsupportedFormatError) as e:
            svc.attach(item_id="ITEM1", file_id=111, language="en")
        assert "could not deliver" in str(e.value)

    def test_upload_can_be_disabled_by_the_caller(self, tmp_path):
        svc, _, library, video = service(tmp_path)
        Path(video).unlink(missing_ok=True)
        self._block_sidecar(video)
        with pytest.raises(UnsupportedFormatError):
            svc.attach(item_id="ITEM1", file_id=111, language="en", allow_upload=False)
        assert library.uploads == []

    def test_a_refresh_failure_still_leaves_the_sidecar_in_place(self, tmp_path):
        """The file is the delivery; a refresh is best-effort."""
        svc, _, _, video = service(tmp_path, refresh_ok=False)
        res = svc.attach(item_id="ITEM1", file_id=111, language="en")
        assert res.delivered == "sidecar"
        assert Path(video).with_name("Movie.2019.1080p.WEB-DL.en.srt").exists()


class TestRefusals:
    def test_an_html_error_page_is_never_written_beside_the_media(self, tmp_path):
        svc, _, _, video = service(tmp_path, content=b"<!DOCTYPE html><html>403</html>")
        with pytest.raises(UnsupportedFormatError):
            svc.attach(item_id="ITEM1", file_id=111, language="en")
        assert not Path(video).with_name("Movie.2019.1080p.WEB-DL.en.srt").exists()

    def test_a_client_failure_propagates_untouched(self, tmp_path):
        svc, _, _, video = service(tmp_path, error=OpenSubtitlesError("quota gone"))
        with pytest.raises(OpenSubtitlesError):
            svc.attach(item_id="ITEM1", file_id=111, language="en")
        assert not Path(video).with_name("Movie.2019.1080p.WEB-DL.en.srt").exists()

    def test_an_unsupported_extension_never_becomes_a_sidecar(self, tmp_path):
        svc, _, _, video = service(tmp_path, file_name="Movie.idx", content=b"\x00\x01binary")
        with pytest.raises(UnsupportedFormatError):
            svc.attach(item_id="ITEM1", file_id=111, language="en")


    def test_a_stale_empty_track_read_is_retried_before_giving_up(self, tmp_path):
        """MEASURED LIVE: the track list can lag the upload by a moment.

        Right after a delivery, PlaybackInfo can still report the OLD (empty) list.
        Accepting that as the answer is what made the first live run report
        ``tracks: []`` for a subtitle it had just successfully uploaded.
        """
        svc, _, library, _ = service(tmp_path)
        calls = {"n": 0}
        real = library.playback_info

        def lagging(item_id):
            calls["n"] += 1
            tracks = real(item_id)["subtitles"]
            return {"subtitles": [] if calls["n"] <= 2 else tracks}

        library.playback_info = lagging
        res = svc.attach(item_id="ITEM1", file_id=111, language="en")
        assert calls["n"] == 3, "should have re-read until the track appeared"
        assert res.tracks == library.tracks

    def test_a_permanently_empty_track_list_is_still_reported_honestly(self, tmp_path):
        """Never fake a track: after the bounded retries, report what the server says."""
        svc, _, library, _ = service(tmp_path)
        library.playback_info = lambda item_id: {"subtitles": []}
        res = svc.attach(item_id="ITEM1", file_id=111, language="en")
        assert res.delivered == "sidecar" and res.tracks == []


class TestLocalTracks:
    def test_local_tracks_are_readable_without_touching_opensubtitles(self, tmp_path):
        svc, client, library, _ = service(tmp_path)
        assert svc.local_tracks("ITEM1") == library.tracks
        assert client.downloads == []
        assert library.item_refreshes == []

    def test_a_provider_error_reads_as_empty_not_as_a_crash(self, tmp_path):
        svc, _, library, _ = service(tmp_path)
        def boom(_):
            raise RuntimeError("jellyfin down")
        library.playback_info = boom
        assert svc.local_tracks("ITEM1") == []
