(function () {
  "use strict";

  const swDot = document.getElementById("sw_dot");
  const swText = document.getElementById("sw_text");
  const modeDot = document.getElementById("mode_dot");
  const modeText = document.getElementById("mode_text");
  const installButton = document.getElementById("install_button");
  const iosHint = document.getElementById("ios_hint");

  function setStatus(dot, text, ok, message) {
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

  function refreshDisplayMode() {
    const mode = currentDisplayMode();
    // navigator.standalone is the iOS-only equivalent; it has no media query.
    const installed = window.navigator.standalone === true || (mode !== "browser" && mode !== "unknown");

    modeDot.classList.remove("ok", "bad");
    setStatus(
      modeDot,
      modeText,
      installed,
      (installed ? "Running installed" : "Running in a browser tab") + " (display-mode: " + mode + ")"
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

  // iOS has no beforeinstallprompt and no programmatic install at all, so the
  // only option is telling the user where the menu item is.
  const isIOS = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
  if (isIOS && !standalone) {
    iosHint.hidden = false;
  }
})();
