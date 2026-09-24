// Telling a barcode scanner from a person typing.
//
// A scanner is a keyboard that types a whole code in a few milliseconds and
// ends with Enter. When the focus sat in the till's quantity or price box,
// that burst was typed INTO the box — a quantity of 6290000123456 — and the
// item was never added. The detector watches the keys that land in any
// field: characters arriving at most `gapMs` apart, at least `minLength`
// of them, ending in Enter, are a scan. Nobody types six characters at
// 50 ms each and presses Enter inside that rhythm.
export const SCAN_GAP_MS = 50;
export const SCAN_MIN_LENGTH = 6;

export function createBurstDetector({ gapMs = SCAN_GAP_MS, minLength = SCAN_MIN_LENGTH } = {}) {
  let burst = null; // { target, before, chars, last }
  return {
    // A printable key is about to land in `target`, whose value is `value`.
    key(target, char, at, value) {
      if (!burst || burst.target !== target || at - burst.last > gapMs) {
        burst = { target, before: value, chars: "", last: at };
      }
      burst.chars += char;
      burst.last = at;
    },
    // Enter pressed in `target`: the scanned code and the value the field
    // had before the burst, or null when this was a person typing.
    enter(target, at) {
      const found = burst && burst.target === target && at - burst.last <= gapMs * 2
        && burst.chars.length >= minLength
        ? { code: burst.chars, before: burst.before } : null;
      burst = null;
      return found;
    },
    reset() { burst = null; },
  };
}
