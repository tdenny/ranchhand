// How the API's breeding states and event types read on screen; keep in sync with the `BreedingState`
// and `EventType` literals in backend/src/ranchhand/models.py.
export const BREEDING_LABELS = { unbred: "Not yet bred", bred: "Bred", pregnant: "Pregnant", open: "Open" };

// Keep in sync with the `Status` literal.
export const STATUS_LABELS = { active: "Active", deceased: "Deceased", processed: "Processed", sold: "Sold", external: "External" };

const EVENT_LABELS = {
  confirmed_pregnant: "Confirmed pregnant",
  confirmed_open: "Confirmed open",
  lost: "Lost pregnancy",
};

export function eventLabel(type) {
  return EVENT_LABELS[type] ?? type[0].toUpperCase() + type.slice(1);
}
