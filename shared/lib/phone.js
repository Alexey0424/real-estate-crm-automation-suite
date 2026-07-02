/**
 * phone.js — normalize a free-text US phone into E.164 (+1XXXXXXXXXX).
 *
 * Why: FUB phone/email search is EXACT-match with no documented normalization
 * (research gotcha). If the form gives "(215) 555 1234" and FUB stores
 * "+12155551234", a naive search misses the dupe and creates a second record.
 * Canonicalize on BOTH the write and the search so dedupe actually works.
 */

function normalizeToE164(raw) {
  if (raw == null) return { e164: null, valid: false, reason: 'empty' };
  const hadPlus = String(raw).trim().startsWith('+');
  const digits = String(raw).replace(/\D/g, '');

  if (digits.length === 10) {
    return { e164: '+1' + digits, valid: true };
  }
  if (digits.length === 11 && digits.startsWith('1')) {
    return { e164: '+' + digits, valid: true };
  }
  // Already international (kept +) or longer than NANP — best-effort passthrough.
  if (hadPlus && digits.length >= 11 && digits.length <= 15) {
    return { e164: '+' + digits, valid: true };
  }
  return { e164: null, valid: false, reason: `unexpected length ${digits.length}` };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { normalizeToE164 };
}
