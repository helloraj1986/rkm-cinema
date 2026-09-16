/**
 * B4 — `window.__rkmOffline`, the page's side of the bridge (ADR-0009 §D6, ADR-0010).
 *
 * ⚠ This file is the ONLY place the injected global is touched, and that is a rule rather than
 * tidiness: the global is injected by `OfflineBridge.swift` at document-start, it is absent in every
 * desktop browser, and every call to it can REJECT. Five call sites each doing their own
 * `window.__rkmOffline && …` dance is five slightly different answers to "is offline available
 * here", and the one that gets it wrong renders a Download button that throws when pressed.
 *
 * ⚠ Everything is looked up at CALL TIME, never captured at module load: the script is injected
 * before the page's own bundles in the shell, but a module-level capture would freeze "no bridge"
 * into a page that later became the shell (and it is exactly what the harness's injected fake
 * needs to be able to do).
 */

import {
  OFFLINE_BRIDGE_VERSION,
  parseEvent,
  parseReply,
  type OfflineEvent,
  type OfflineReply,
} from "./lib";

/** The shape `OfflineBridge.swift` installs. Everything is optional: this describes a global we do
 *  not control, and a version of the app that installs a narrower one is not "broken". */
interface InjectedBridge {
  version?: number;
  available?: boolean;
  on?: (listener: (event: unknown) => void) => unknown;
  off?: (listener: (event: unknown) => void) => unknown;
  list?: () => Promise<unknown>;
  ping?: () => Promise<unknown>;
  play?: (itemId: string) => Promise<unknown>;
  cancel?: (itemId: string) => Promise<unknown>;
  remove?: (itemId: string) => Promise<unknown>;
  download?: (itemId: string, title: string, mode: string) => Promise<unknown>;
}

function injected(): InjectedBridge | null {
  try {
    const candidate = (globalThis as { __rkmOffline?: unknown }).__rkmOffline;
    if (!candidate || typeof candidate !== "object") return null;
    return candidate as InjectedBridge;
  } catch {
    return null;
  }
}

/**
 * ⚠ The version is checked on the GLOBAL, not only on replies. A build that injects a v2 object may
 * shape every payload differently, and the honest answer to "shall I draw a Download button?" is no
 * — the button would speak a contract this app does not.
 */
export function bridgeSpeaksOurVersion(): boolean {
  const bridge = injected();
  if (!bridge) return false;
  return bridge.version === undefined || bridge.version === OFFLINE_BRIDGE_VERSION;
}

/** Is there a usable bridge in this web view? The page draws NO offline affordance without it. */
export function bridgeAvailable(): boolean {
  const bridge = injected();
  if (!bridge) return false;
  if (bridge.version !== undefined && bridge.version !== OFFLINE_BRIDGE_VERSION) return false;
  return typeof bridge.list === "function" && typeof bridge.on === "function";
}

function noBridge(context: string, code = "noBridge"): OfflineReply {
  return {
    ok: false,
    unreadable: true,
    error: {
      code,
      message: bridgeSpeaksOurVersion()
        ? `This app cannot ${context} offline downloads.`
        : `This app speaks a different offline contract, so it cannot ${context} downloads.`,
    },
  };
}

async function command(
  context: string,
  run: (bridge: InjectedBridge) => Promise<unknown> | undefined,
): Promise<OfflineReply> {
  const bridge = injected();
  if (!bridge) return noBridge(context);
  if (bridge.version !== undefined && bridge.version !== OFFLINE_BRIDGE_VERSION) {
    return noBridge(context, "unsupportedVersion");
  }
  let promise: Promise<unknown> | undefined;
  try {
    promise = run(bridge);
  } catch {
    // ⚠ The injected `request()` throws for exactly one reason that is not the app's fault (a
    // handler that does not reply), so this reports rather than propagating: a button press must
    // never produce an unhandled rejection.
    return noBridge(context, "bridgeThrew");
  }
  if (!promise || typeof promise.then !== "function") return noBridge(context, "noReplyCapableHandler");
  try {
    return parseReply(await promise);
  } catch {
    return noBridge(context, "unreadableReply");
  }
}

export function listDownloads(): Promise<OfflineReply> {
  return command("read", (bridge) => bridge.list?.());
}

export function pingBridge(): Promise<OfflineReply> {
  return command("talk to", (bridge) => bridge.ping?.());
}

export function requestDownload(itemId: string, title: string, mode: string): Promise<OfflineReply> {
  return command("queue", (bridge) => bridge.download?.(itemId, title, mode));
}

/** ⚠ Cancel is the only stop the contract has (there is no `pause`): it leaves a resumable `.part`,
 *  which is why the row it produces reads "paused — resumable" and the Resume action re-sends
 *  `download` for the same title. */
export function requestCancel(itemId: string): Promise<OfflineReply> {
  return command("cancel", (bridge) => bridge.cancel?.(itemId));
}

export function requestDelete(itemId: string): Promise<OfflineReply> {
  return command("delete", (bridge) => bridge.remove?.(itemId));
}

export function requestPlay(itemId: string): Promise<OfflineReply> {
  return command("play", (bridge) => bridge.play?.(itemId));
}

/**
 * Subscribe to native events. Returns the unsubscribe function, and a no-op when there is no
 * bridge — so callers never have to branch.
 *
 * ⚠ Events that arrive before a listener exists are QUEUED by the injected script (a reload races
 * the React tree), so subscribing late loses nothing.
 */
export function subscribeOfflineEvents(listener: (event: OfflineEvent) => void): () => void {
  const bridge = injected();
  if (!bridge || typeof bridge.on !== "function") return () => {};
  const wrapped = (raw: unknown) => {
    const event = parseEvent(raw);
    // ⚠ Unreadable events are DROPPED, not coerced. The native planner only sends shapes it has
    // decided on; anything else is not this page's business to interpret.
    if (event) listener(event);
  };
  bridge.on(wrapped);
  return () => {
    try {
      bridge.off?.(wrapped);
    } catch {
      /* a bridge that cannot unsubscribe is not a reason to throw on unmount */
    }
  };
}
