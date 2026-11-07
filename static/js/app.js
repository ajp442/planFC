(function () {
  "use strict";

  // Loaded on every page. The status card, install button and iOS hint exist
  // only on the home page, so each part below checks for its elements first.

  const swDot = document.getElementById("sw_dot");
  const swText = document.getElementById("sw_text");
  const modeDot = document.getElementById("mode_dot");
  const modeText = document.getElementById("mode_text");
  const installButton = document.getElementById("install_button");
  const iosHint = document.getElementById("ios_hint");

  function setStatus(dot, text, ok, message) {
    if (!dot || !text) return;
    dot.classList.add(ok ? "ok" : "bad");
    text.textContent = message;
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker
      .register("/sw.js")
      .then((reg) => setStatus(swDot, swText, true, "Service worker registered (scope " + reg.scope + ")"))
      .catch((err) => setStatus(swDot, swText, false, "Service worker failed: " + err.message));
  } else {
    setStatus(swDot, swText, false, "Service workers unsupported");
  }

  // Any mode other than "browser" means the app is running installed. Reporting
  // the mode by name matters: Chrome may pick minimal-ui or
  // window-controls-overlay over the manifest's standalone, and a bare
  // standalone check would call all of those "a browser tab".
  const DISPLAY_MODES = [
    "fullscreen",
    "standalone",
    "minimal-ui",
    "window-controls-overlay",
    "browser",
  ];

  function currentDisplayMode() {
    return (
      DISPLAY_MODES.find((mode) => window.matchMedia("(display-mode: " + mode + ")").matches) ||
      "unknown"
    );
  }

  function isInstalled() {
    const mode = currentDisplayMode();
    // navigator.standalone is the iOS-only equivalent; it has no media query.
    return window.navigator.standalone === true || (mode !== "browser" && mode !== "unknown");
  }

  function refreshDisplayMode() {
    const installed = isInstalled();
    if (modeDot) modeDot.classList.remove("ok", "bad");
    setStatus(
      modeDot,
      modeText,
      installed,
      (installed ? "Running installed" : "Running in a browser tab") + " (display-mode: " + currentDisplayMode() + ")"
    );
    return installed;
  }

  const standalone = refreshDisplayMode();

  // On first launch straight after install, the window can still be settling
  // when this script runs, so re-evaluate if the mode changes under us.
  DISPLAY_MODES.forEach((mode) => {
    window.matchMedia("(display-mode: " + mode + ")").addEventListener("change", refreshDisplayMode);
  });

  // Chrome/Android fires this when the app is installable; capturing it lets us
  // put the prompt behind our own button instead of the browser's mini-infobar.
  let deferredPrompt = null;
  if (installButton) {
    window.addEventListener("beforeinstallprompt", (event) => {
      event.preventDefault();
      deferredPrompt = event;
      installButton.hidden = false;
    });

    installButton.addEventListener("click", async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      // The event is single-use; a second prompt() on it throws.
      deferredPrompt = null;
      installButton.hidden = true;
    });

    window.addEventListener("appinstalled", () => {
      installButton.hidden = true;
    });
  }

  // iOS has no beforeinstallprompt and no programmatic install at all, so the
  // only option is telling the user where the menu item is.
  const isIOS = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
  if (iosHint && isIOS && !standalone) {
    iosHint.hidden = false;
  }

  // Exposed for profile.js, which needs the same answers.
  window.planfc = { isIOS: isIOS, isInstalled: isInstalled };

  // --- Signing out ------------------------------------------------------------
  // A push subscription belongs to the browser, not the member, so it outlives
  // the session. Signing out (or deleting the account) therefore turns this
  // device's notifications off first, or the next person to sign in on this
  // phone would receive the previous member's. Sign-out goes ahead whatever
  // happens here: it must never be blocked by a push service being slow.
  document.querySelectorAll("form.js-logout").forEach((form) => {
    let done = false;
    form.addEventListener("submit", (event) => {
      if (done || !("serviceWorker" in navigator)) return;
      event.preventDefault();
      const finish = () => {
        if (done) return;
        done = true;
        form.submit();
      };
      setTimeout(finish, 3000);
      forgetPushSubscription(form).catch(() => {}).finally(finish);
    });
  });

  async function forgetPushSubscription(form) {
    const registration = await navigator.serviceWorker.getRegistration();
    const subscription = registration && registration.pushManager && (await registration.pushManager.getSubscription());
    if (!subscription) return;
    const token = form.querySelector("input[name=csrfmiddlewaretoken]");
    await fetch("/push/unsubscribe/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token ? token.value : "" },
      body: JSON.stringify({ endpoint: subscription.endpoint }),
    }).catch(() => {});
    await subscription.unsubscribe().catch(() => {});
  }
})();
