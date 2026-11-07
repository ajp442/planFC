(function () {
  "use strict";

  // The Notifications section of the profile page: turns push on or off for
  // this device. The server half is accounts/views.py (push_subscribe,
  // push_unsubscribe) and the worker half is the push handler in sw.js.

  const config = JSON.parse(document.getElementById("push_config").textContent);
  const status = document.getElementById("push_status");
  const toggle = document.getElementById("push_toggle");
  const iosHint = document.getElementById("push_ios_hint");
  const csrfToken = document.querySelector("input[name=csrfmiddlewaretoken]").value;
  let subscribed = false;

  function show(message, buttonLabel) {
    status.textContent = message;
    toggle.hidden = !buttonLabel;
    if (buttonLabel) toggle.textContent = buttonLabel;
  }

  // The VAPID public key is base64url text; subscribe() wants raw bytes.
  function keyBytes(base64url) {
    const base64 = base64url.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify(body),
    }).then((response) => {
      if (!response.ok) throw new Error("The server answered " + response.status);
    });
  }

  async function currentSubscription() {
    const registration = await navigator.serviceWorker.ready;
    return registration.pushManager.getSubscription();
  }

  async function refresh() {
    const supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
    if (!supported) {
      // iOS and iPadOS only offer push to an app on the home screen.
      if (window.planfc && window.planfc.isIOS && !window.planfc.isInstalled()) {
        show("Not available in the browser on this device.");
        iosHint.hidden = false;
      } else {
        show("This browser doesn't support notifications.");
      }
      return;
    }
    if (Notification.permission === "denied") {
      show("Notifications are blocked for this site. Allow them in your browser or phone settings, then reload.");
      return;
    }
    const subscription = await currentSubscription();
    subscribed = Boolean(subscription);
    if (subscription) {
      show("On for this device.", "Turn off on this device");
    } else {
      show("Off for this device.", "Turn on for this device");
    }
  }

  async function turnOn() {
    // Must run straight from the tap: iOS refuses a permission prompt that
    // isn't the direct result of a user gesture.
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      await refresh();
      return;
    }
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
      // Every message will be visible; browsers require this promise.
      userVisibleOnly: true,
      applicationServerKey: keyBytes(config.vapidPublicKey),
    });
    await post(config.subscribeUrl, subscription.toJSON());
  }

  async function turnOff() {
    const subscription = await currentSubscription();
    if (!subscription) return;
    await post(config.unsubscribeUrl, { endpoint: subscription.endpoint });
    await subscription.unsubscribe();
  }

  toggle.addEventListener("click", async () => {
    toggle.disabled = true;
    try {
      // Decided from state refresh() already found, not by asking again:
      // any await before requestPermission() could cost the user gesture.
      if (subscribed) {
        await turnOff();
      } else {
        await turnOn();
      }
      // The device list and test button are rendered by the server.
      window.location.reload();
    } catch (error) {
      show("Something went wrong: " + error.message, toggle.textContent);
    } finally {
      toggle.disabled = false;
    }
  });

  refresh().catch((error) => show("Couldn't check notifications: " + error.message));
})();
