(function () {
  "use strict";

  // Recording a payment, step by step (payments/wizard.py). Everything here
  // is an improvement on pages that work without it: the search box
  // searches on the server, and the list of steps is plain links.

  const root = document.documentElement;
  const topbar = document.querySelector(".topbar");
  const head = document.querySelector(".wizard-head");

  // The steps (and on the first step, the search box) stay pinned under the
  // site's header, whose height depends on the device's safe area.
  function measure() {
    if (topbar) root.style.setProperty("--topbar-h", topbar.offsetHeight + "px");
    if (head) root.style.setProperty("--wizard-head-h", head.offsetHeight + "px");
  }
  measure();
  window.addEventListener("resize", measure);

  // Leaving a step through the list of steps (or a "Change" link) submits
  // the step's form first, so a value typed but not yet saved isn't lost.
  // form.submit() skips the browser's checks: an unfinished value is simply
  // not kept (wizard._step).
  const form = document.getElementById("wizard_form");
  if (form && form.elements.goto) {
    document.querySelectorAll("[data-goto]").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        form.elements.goto.value = link.dataset.goto;
        form.submit();
      });
    });
  }

  // The step's main field (the amount, the method) is focused every time
  // the step is shown. `autofocus` alone is skipped when the browser brings
  // the page back from its cache (Back, switching apps), and the amount is
  // selected so typing replaces it.
  const first = form && form.querySelector("[autofocus]");
  if (first) {
    const focusFirst = () => {
      first.focus();
      if (first.select && first.value) first.select();
    };
    focusFirst();
    window.addEventListener("pageshow", focusFirst);
  }

  // --- Step 1: who paid ----------------------------------------------------

  const search = document.getElementById("who_search");
  const list = document.getElementById("who_list");
  if (!search || !list) return;

  const searchForm = document.getElementById("who_search_form");
  const add = document.getElementById("who_add");
  const addName = document.getElementById("who_add_name");
  const count = document.getElementById("who_count");
  const empty = document.getElementById("who_empty");
  const rows = Array.from(list.querySelectorAll("li[data-search]"));
  const total = rows.length;
  let active = null;

  search.setAttribute("role", "combobox");
  search.setAttribute("aria-autocomplete", "list");
  search.setAttribute("aria-expanded", "true");

  function cleaned() {
    return search.value.trim().replace(/\s+/g, " ");
  }

  // Every word typed must appear in the name or email, in any order:
  // "ann sm", "smith" and "@gmail" all find Ann Smith.
  function visibleButtons() {
    const buttons = rows.filter((row) => !row.hidden).map((row) => row.querySelector("button"));
    if (!add.hidden) buttons.push(add);
    return buttons;
  }

  function highlight(button, scroll) {
    if (active) active.classList.remove("active");
    active = button;
    if (button) {
      button.classList.add("active");
      search.setAttribute("aria-activedescendant", button.id);
      if (scroll) button.scrollIntoView({ block: "nearest" });
    } else {
      search.removeAttribute("aria-activedescendant");
    }
  }

  function filter() {
    const text = cleaned();
    const words = text.toLowerCase().split(" ").filter(Boolean);
    let shown = 0;
    rows.forEach((row) => {
      const match = words.every((word) => row.dataset.search.includes(word));
      row.hidden = !match;
      if (match) shown += 1;
    });
    add.hidden = !text;
    add.value = text;
    addName.textContent = text;
    empty.hidden = shown > 0;
    count.textContent = text ? shown + " of " + total + " match" : total + " member" + (total === 1 ? "" : "s");
    measure();
    // With something typed, Enter picks the first match, or adds the name
    // when nobody matches. With nothing typed, Enter does nothing.
    highlight(text ? visibleButtons()[0] || null : null, false);
    if (text) window.scrollTo({ top: 0 });
  }

  search.addEventListener("input", filter);

  search.addEventListener("keydown", (event) => {
    const buttons = visibleButtons();
    const index = buttons.indexOf(active);
    if (event.key === "ArrowDown") {
      highlight(buttons[Math.min(index + 1, buttons.length - 1)] || null, true);
      event.preventDefault();
    } else if (event.key === "ArrowUp") {
      highlight(index > 0 ? buttons[index - 1] : buttons[0] || null, true);
      event.preventDefault();
    } else if (event.key === "Enter") {
      // Never the server-side search: the list is already filtered.
      event.preventDefault();
      if (active) active.click();
    } else if (event.key === "Escape" && search.value) {
      search.value = "";
      filter();
      event.preventDefault();
    }
  });

  searchForm.addEventListener("submit", (event) => event.preventDefault());

  // Coming back to this step: show who was picked before.
  const chosen = list.querySelector(".who-pick.chosen");
  if (chosen && !cleaned()) chosen.scrollIntoView({ block: "center" });
  if (cleaned()) filter();

  // Focused and ready to type, even when the browser restored the page from
  // its cache and ignored autofocus.
  search.focus();
  window.addEventListener("pageshow", () => search.focus());
})();
