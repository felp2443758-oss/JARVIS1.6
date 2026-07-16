// J.A.R.V.I.S. Autofill — content script
// Injects window.__jarvisFill(username, password) that intelligently finds
// username/email/password inputs on the current page and fills them.
(function () {
  if (window.__jarvisFillInstalled) return;
  window.__jarvisFillInstalled = true;

  function isVisible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function score(el, wants) {
    let s = 0;
    const attrs = [el.name, el.id, el.placeholder, el.autocomplete, el.getAttribute("aria-label")]
      .filter(Boolean).join(" ").toLowerCase();
    for (const w of wants) if (attrs.includes(w)) s += 2;
    if (el.type === "email" && wants.includes("email")) s += 3;
    if (el.type === "password" && wants.includes("password")) s += 5;
    if (isVisible(el)) s += 1;
    return s;
  }

  function findBest(selector, wants) {
    const candidates = Array.from(document.querySelectorAll(selector)).filter(isVisible);
    if (candidates.length === 0) return null;
    candidates.sort((a, b) => score(b, wants) - score(a, wants));
    return candidates[0];
  }

  function setValue(el, val) {
    if (!el || val == null) return false;
    const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(el, val);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  window.__jarvisFill = function (username, password) {
    const userWants = ["user", "username", "login", "email", "e-mail", "account", "usuario", "usuário"];
    const passWants = ["pass", "password", "senha", "pwd"];

    const userEl = findBest(
      'input[type="email"], input[type="text"], input[type="tel"], input:not([type])',
      userWants
    );
    const passEl = findBest('input[type="password"]', passWants);

    let filled = 0;
    if (userEl && username) { setValue(userEl, username); filled++; }
    if (passEl && password) { setValue(passEl, password); filled++; }

    // Small visual hint
    if (filled > 0) {
      try {
        const el = passEl || userEl;
        el.style.transition = "box-shadow 0.4s ease";
        el.style.boxShadow = "0 0 0 3px rgba(34, 211, 238, 0.6)";
        setTimeout(() => { el.style.boxShadow = ""; }, 1200);
      } catch (_) {}
    }
    return filled;
  };

  // Optional: react to messages if the extension chooses to postMessage instead of scripting.
  window.addEventListener("message", (ev) => {
    if (ev?.data?.type === "jarvis:fill" && ev.data.credential) {
      window.__jarvisFill(ev.data.credential.username, ev.data.credential.password);
    }
  });
})();
