import Choices from "choices.js";

/**
 * Turn a <select name="sire_id"> (or dam_id) into a searchable picker over herd members, using
 * Choices.js. The select itself carries the value, so the form submits the picked animal's id
 * (or "" when nothing is picked) with no extra plumbing, and Choices resets it with the form.
 *
 * `loadCandidates()` resolves to the animals to offer. It's called each time the dropdown opens
 * and must return the same promise until the data changes, so the list is only rebuilt when it has.
 * Only animals of `sex` are offered.
 */
export function setupParentPicker(select, { sex, loadCandidates }) {
  const choices = new Choices(select, {
    searchPlaceholderValue: "Search by number",
    noResultsText: "No matching animals",
    noChoicesText: "No animals to choose from",
    itemSelectText: "",
    // Keep the API's order (by number), and show every match, not Choices' default of four.
    shouldSort: false,
    searchResultLimit: -1,
    // Search the visible number only (not the id), and as a substring: Choices' default fuzzy
    // match would offer #201 for "202".
    searchFields: ["label"],
    fuseOptions: { includeScore: true, threshold: 0, ignoreLocation: true },
  });

  const placeholder = (selected) => ({ value: "", label: "None", placeholder: true, selected });

  function toChoices(animals) {
    const current = select.value;

    return [
      placeholder(current === ""),
      ...animals
        .filter((animal) => animal.sex === sex)
        .map((animal) => ({
          value: animal.id,
          label: `#${animal.number}`,
          labelDescription: `${animal.status} · born ${animal.date_of_birth ?? "unknown"}`,
          selected: animal.id === current,
        })),
    ];
  }

  let shownFor = null; // the loadCandidates() promise the list was last built from

  function refresh() {
    const pending = loadCandidates();
    if (pending === shownFor) return;
    shownFor = pending;

    // Choices shows its loading state while this runs. Replacing items as well as choices avoids
    // a duplicate of the selected animal; toChoices marks the current pick as selected again.
    choices.setChoices(
      () =>
        pending.then(toChoices, (error) => {
          shownFor = null; // try again the next time it opens
          return [
            placeholder(select.value === ""),
            { value: "error", label: `Could not load animals. ${error.message}`, disabled: true },
          ];
        }),
      "value",
      "label",
      true,
      false,
      true,
    );
  }

  select.addEventListener("showDropdown", refresh);
}
