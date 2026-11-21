(function () {
  "use strict";

  // The "Who paid" box on the payments page: suggests members whose name or
  // email contains what was typed, and links the payment to the one picked.
  // Without JavaScript it is a plain text box, and every payment is recorded
  // under the typed name with no account linked.

  const input = document.getElementById("id_payer_name");
  const hidden = document.getElementById("id_member");
  const list = document.getElementById("payer_suggestions");
  const status = document.getElementById("payer_status");
  const data = document.getElementById("payment_members");
  if (!input || !hidden || !list || !status || !data) return;

  const MAX_SHOWN = 8;
  const people = JSON.parse(data.textContent).map((person) => ({
    ...person,
    haystack: (person.name + " " + person.email).toLowerCase(),
  }));
  let shown = [];
  let active = -1;

  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-controls", list.id);
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-describedby", status.id);

  // Every word typed must appear somewhere in the name or email, in any
  // order: "ann sm", "smith" and "@gmail" all find Ann Smith.
  function matches(text) {
    const words = text.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return [];
    return people.filter((person) => words.every((word) => person.haystack.includes(word)));
  }

  function linkedPerson() {
    return people.find((person) => String(person.id) === hidden.value);
  }

  function showStatus() {
    const person = linkedPerson();
    if (person) {
      status.textContent = "Linked to " + person.name + "'s account" + (person.email ? " (" + person.email + ")" : "") + ".";
    } else if (input.value.trim()) {
      status.textContent = "Not linked to an account. It will be recorded under this name.";
    } else {
      status.textContent = "";
    }
  }

  function close() {
    list.hidden = true;
    list.replaceChildren();
    shown = [];
    active = -1;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  function highlight(index) {
    active = index;
    Array.from(list.children).forEach((item, i) => item.setAttribute("aria-selected", String(i === index)));
    if (index >= 0) {
      input.setAttribute("aria-activedescendant", list.children[index].id);
      list.children[index].scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function render() {
    const found = matches(input.value);
    shown = found.slice(0, MAX_SHOWN);
    if (!shown.length) {
      close();
      return;
    }
    list.replaceChildren(...shown.map((person, i) => {
      const item = document.createElement("li");
      item.id = "payer_option_" + person.id;
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", "false");
      const name = document.createElement("span");
      name.className = "suggestion-name";
      name.textContent = person.name + (person.active ? "" : " (deactivated)");
      const email = document.createElement("span");
      email.className = "suggestion-email";
      email.textContent = person.email;
      item.append(name, email);
      // pointerdown, not click: a click would blur the box first and close the list.
      item.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        choose(i);
      });
      return item;
    }));
    if (found.length > MAX_SHOWN) {
      const more = document.createElement("li");
      more.className = "suggestion-more";
      more.setAttribute("aria-hidden", "true");
      more.textContent = (found.length - MAX_SHOWN) + " more: keep typing to narrow it down";
      list.append(more);
    }
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    highlight(-1);
  }

  function choose(index) {
    const person = shown[index];
    if (!person) return;
    input.value = person.name;
    hidden.value = String(person.id);
    close();
    showStatus();
    const amount = document.getElementById("id_amount");
    if (amount && !amount.value) amount.focus();
  }

  input.addEventListener("input", () => {
    // Any edit unlinks: the name no longer says whose account it is. Unless
    // it now spells out exactly one member's name, in which case typing it in
    // full counts the same as picking it.
    const typed = input.value.trim().replace(/\s+/g, " ").toLowerCase();
    const exact = people.filter((person) => person.name.toLowerCase() === typed);
    hidden.value = exact.length === 1 ? String(exact[0].id) : "";
    render();
    showStatus();
  });

  input.addEventListener("keydown", (event) => {
    if (list.hidden) {
      if (event.key === "ArrowDown" && input.value.trim()) {
        render();
        event.preventDefault();
      }
      return;
    }
    if (event.key === "ArrowDown") {
      highlight((active + 1) % shown.length);
      event.preventDefault();
    } else if (event.key === "ArrowUp") {
      highlight(active <= 0 ? shown.length - 1 : active - 1);
      event.preventDefault();
    } else if (event.key === "Enter" && active >= 0) {
      // Picks the suggestion instead of submitting the form.
      choose(active);
      event.preventDefault();
    } else if (event.key === "Escape") {
      close();
      event.preventDefault();
    }
  });

  input.addEventListener("blur", close);

  // A form shown again with an error keeps the member it was linked to.
  showStatus();
})();
