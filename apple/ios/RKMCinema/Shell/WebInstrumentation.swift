import Foundation
import WebKit

/// The JavaScript injected into the page at document start — `apple/LOGGING.md` §3's
/// "iOS shell — extra, because the WebView is otherwise opaque".
///
/// ⚠ **This is what makes "log every request" possible on iOS at all.** The shell makes no API
/// calls of its own: the *page* does. So the page is instrumented, each `fetch`/XHR gets a
/// correlation id of its own, and the event comes back to native — where the **native redactor**
/// formats it. That last part is deliberate: a second redaction implementation in JavaScript
/// would be a second call site, which is exactly what `LOGGING.md` §6 forbids.
///
/// Everything is wrapped in `try`/`catch` and never rethrows: instrumentation must not be able to
/// break the app it is watching.
enum WebInstrumentation {

    static let handlerName = "rkm"

    static func userScript() -> WKUserScript {
        WKUserScript(
            source: source,
            // ⚠ Before any page code runs — otherwise the first API calls (the ones that matter
            // most, on first paint) happen before `fetch` is wrapped.
            injectionTime: .atDocumentStart,
            // Main frame only: the app's own calls live there, and a third-party iframe's traffic
            // is not ours to log.
            forMainFrameOnly: true
        )
    }

    static let source: String = #"""
    (function () {
      if (window.__rkmBridgeInstalled) { return; }
      window.__rkmBridgeInstalled = true;

      var handler = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.rkm;
      if (!handler) { return; }

      function send(payload) {
        try { handler.postMessage(JSON.stringify(payload)); } catch (e) { /* never break the page */ }
      }

      // Six lowercase hex characters — the same shape the native side mints, so a HUD id can be
      // grepped out of the log file whatever produced it.
      function nextId() {
        try { return (Math.random().toString(16).slice(2) + '000000').slice(0, 6); }
        catch (e) { return '000000'; }
      }

      // Path + query. Native redacts it — see the note above about one redaction call site.
      function pathOf(input) {
        try {
          var raw = (typeof input === 'string') ? input : ((input && input.url) || '');
          var url = new URL(raw, window.location.href);
          return url.pathname + url.search;
        } catch (e) {
          return String(input || '').slice(0, 300);
        }
      }

      // ⚠ Header only. Cloning the body to measure it would buffer whole HLS segments and video
      // responses in memory — a real cost, paid for one log line.
      function bytesOf(response) {
        try {
          var header = response && response.headers && response.headers.get && response.headers.get('content-length');
          if (!header) { return null; }
          var value = parseInt(header, 10);
          return isNaN(value) ? null : value;
        } catch (e) { return null; }
      }

      // ---------------------------------------------------------------- fetch
      var originalFetch = window.fetch;
      if (originalFetch) {
        window.fetch = function (input, init) {
          var method = (init && init.method) || (input && input.method) || 'GET';
          var id = nextId();
          var started = Date.now();
          var promise = originalFetch.apply(this, arguments);
          try {
            promise.then(
              function (response) {
                send({ t: 'net', id: id, m: String(method).toUpperCase(), u: pathOf(input),
                       s: response.status, ms: Date.now() - started, b: bytesOf(response) });
              },
              function (error) {
                send({ t: 'net', id: id, m: String(method).toUpperCase(), u: pathOf(input),
                       ms: Date.now() - started, err: String((error && error.message) || error) });
              }
            );
          } catch (e) { /* ignore */ }
          // The caller gets the original promise, so its own error handling is untouched.
          return promise;
        };
      }

      // ---------------------------------------------------------------- XMLHttpRequest
      var XHR = window.XMLHttpRequest;
      if (XHR && XHR.prototype) {
        var originalOpen = XHR.prototype.open;
        var originalSend = XHR.prototype.send;

        XHR.prototype.open = function (method, url) {
          try { this.__rkm = { m: method, u: url }; } catch (e) { /* ignore */ }
          return originalOpen.apply(this, arguments);
        };

        XHR.prototype.send = function () {
          var xhr = this;
          var meta = xhr.__rkm || {};
          var id = nextId();
          var started = Date.now();
          try {
            xhr.addEventListener('loadend', function () {
              var bytes = null;
              try {
                var header = xhr.getResponseHeader && xhr.getResponseHeader('content-length');
                if (header) { bytes = parseInt(header, 10); }
              } catch (e) { /* ignore */ }
              send({ t: 'net', id: id, m: String(meta.m || 'GET').toUpperCase(), u: pathOf(meta.u),
                     s: xhr.status, ms: Date.now() - started, b: bytes });
            });
          } catch (e) { /* ignore */ }
          return originalSend.apply(xhr, arguments);
        };
      }

      // ---------------------------------------------------------------- console
      ['log', 'info', 'warn', 'error', 'debug'].forEach(function (level) {
        var original = console[level];
        console[level] = function () {
          try {
            var text = Array.prototype.map.call(arguments, function (value) {
              if (typeof value === 'string') { return value; }
              try { return JSON.stringify(value); } catch (e) { return String(value); }
            }).join(' ');
            send({ t: 'console', lv: level, m: text.slice(0, 1000) });
          } catch (e) { /* ignore */ }
          if (original) { return original.apply(console, arguments); }
        };
      });

      // ---------------------------------------------------------------- uncaught errors
      window.addEventListener('error', function (event) {
        send({ t: 'jserror',
               m: String((event && event.message) || 'error'),
               s: String((event && event.filename) || ''),
               ln: (event && event.lineno) || 0 });
      });

      window.addEventListener('unhandledrejection', function (event) {
        var reason = event && event.reason;
        var text = (reason && (reason.stack || reason.message)) || String(reason);
        send({ t: 'rejection', m: String(text).slice(0, 1500) });
      });

      // ⚠ No WKUIDelegate is installed, so these do nothing by default and `confirm()` would
      // leave the page waiting forever. Log them loudly and return a safe value instead.
      window.alert = function (message) {
        send({ t: 'dialog', k: 'alert', m: String(message) });
      };
      window.confirm = function (message) {
        send({ t: 'dialog', k: 'confirm', m: String(message) });
        return false;
      };
      window.prompt = function (message) {
        send({ t: 'dialog', k: 'prompt', m: String(message) });
        return null;
      };

      // ---------------------------------------------------------------- ready
      document.addEventListener('DOMContentLoaded', function () {
        send({ t: 'ready', hr: String(window.location.href),
               w: window.innerWidth, h: window.innerHeight,
               ua: String(navigator.userAgent) });
      });
    })();
    """#
}
