"""Jellyfin API-key provisioning (the shapes are version-specific and silent).

Live-probed on Jellyfin 10.11.11 (2026-09-10), after a real provisioning run fell
back to the admin session token without anyone noticing:

    create : POST /Auth/Keys?app=<name>  with an EMPTY body   (a JSON body -> 400)
    list   : items carry ``AppName`` + ``AccessToken``         (NOT ``App``/``Key``)

Both mistakes are invisible from the outside — each one looks exactly like "no key
exists yet" — so the tests below pin the wire format, the field names, the refusal
to call an empty create a success, and the documented fallback.
"""
import sys
from pathlib import Path

_PROV_DIR = Path(__file__).resolve().parent.parent / "provisioner"
if str(_PROV_DIR) not in sys.path:
    sys.path.insert(0, str(_PROV_DIR))

import provision  # noqa: E402

KEY_VALUE = "5011e1c3c53646108c84dab2733a415a"
MODERN_LIST = {"Items": [{"Id": 0, "AccessToken": KEY_VALUE, "AppName": "RKM Cinema",
                          "DeviceId": "", "IsActive": False}], "TotalRecordCount": 1}
LEGACY_LIST = {"Items": [{"App": "RKM Cinema", "Key": KEY_VALUE}], "TotalRecordCount": 1}
EMPTY_LIST = {"Items": [], "TotalRecordCount": 0}


class TestRequestEmptyBody:
    def test_empty_body_is_sent_as_content_length_zero(self, monkeypatch):
        """The query form needs an explicit empty body — absent body 400s on 10.11."""
        captured = {}

        class FakeResponse:
            status = 204

            def read(self):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None):
            captured["data"] = req.data
            captured["method"] = req.get_method()
            captured["url"] = req.full_url
            captured["auth_header"] = req.headers.get("X-emby-authorization")
            return FakeResponse()

        monkeypatch.setattr(provision.urllib.request, "urlopen", fake_urlopen)
        code, _ = provision._request("POST", "/Auth/Keys", q={"app": "RKM Cinema"}, body="")
        assert code == 204
        assert captured["data"] == b"", "an empty body must be sent on purpose"
        assert captured["method"] == "POST"
        assert "app=RKM+Cinema" in captured["url"] or "app=RKM%20Cinema" in captured["url"]
        assert captured["auth_header"], "Jellyfin rejects auth without a client header"


class TestEnsureApiKey:
    def test_reuses_an_existing_key_using_the_modern_field_names(self, monkeypatch):
        calls = []
        monkeypatch.setattr(provision, "_request",
                            lambda *a, **k: (calls.append(a) or (200, MODERN_LIST)))
        assert provision.ensure_api_key("tok") == KEY_VALUE
        assert len(calls) == 1, "no create attempt when a key already exists"

    def test_reuses_an_existing_key_with_legacy_field_names(self, monkeypatch):
        monkeypatch.setattr(provision, "_request", lambda *a, **k: (200, LEGACY_LIST))
        assert provision.ensure_api_key("tok") == KEY_VALUE

    def test_creates_via_the_query_form_first(self, monkeypatch):
        seen = []

        def fake_request(method, path, *, token=None, q=None, body=None, timeout=15):
            seen.append({"method": method, "path": path, "q": q, "body": body})
            if method == "GET":
                # empty until the query-form POST has happened, then the key exists
                created = any(s["method"] == "POST" and s.get("q") for s in seen)
                return 200, (MODERN_LIST if created else EMPTY_LIST)
            return 204, None

        monkeypatch.setattr(provision, "_request", fake_request)
        assert provision.ensure_api_key("tok") == KEY_VALUE
        posts = [s for s in seen if s["method"] == "POST"]
        assert len(posts) == 1
        assert posts[0]["q"] == {"app": "RKM Cinema"}, "must use the verified query form"
        assert posts[0]["body"] == "", "and an empty body"

    def test_a_204_that_registers_nothing_is_not_success(self, monkeypatch):
        """Every create returns 204 but the list stays empty -> fall back, loudly."""
        posts = []

        def fake_request(method, path, *, token=None, q=None, body=None, timeout=15):
            if method == "GET":
                return 200, EMPTY_LIST
            posts.append(body)
            return 204, None

        monkeypatch.setattr(provision, "_request", fake_request)
        assert provision.ensure_api_key("admin-token") == "admin-token"
        assert len(posts) == 3, "all three shapes should have been attempted"

    def test_falls_back_to_the_admin_token_and_says_so(self, monkeypatch, capsys):
        monkeypatch.setattr(provision, "_request",
                            lambda method, path, **k: (200, EMPTY_LIST) if method == "GET" else (400, None))
        assert provision.ensure_api_key("admin-token") == "admin-token"
        out = capsys.readouterr().out
        assert "fallback" in out
        assert "admin AccessToken" in out

    def test_legacy_versions_still_work(self, monkeypatch):
        """An older Jellyfin that only accepts the JSON body must still yield a key."""
        def fake_request(method, path, *, token=None, q=None, body=None, timeout=15):
            if method == "GET":
                created = any(k for k in state if k)
                return 200, (LEGACY_LIST if created else EMPTY_LIST)
            state.append(body)
            return 200 if body and body.get("App") else 400, None

        state = []
        monkeypatch.setattr(provision, "_request", fake_request)
        assert provision.ensure_api_key("tok") == KEY_VALUE
        assert state and state[0] == "", "the query form is tried first"
        assert any(isinstance(b, dict) and b.get("App") for b in state), \
            "then the legacy JSON body"
