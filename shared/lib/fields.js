/**
 * fields.js — pull the notification fields out of a raw FUB person record
 * (the object returned by GET /v1/people/{id}?fields=allFields).
 *
 * Reflects the REAL FUB schema confirmed in research:
 *  - names: firstName / lastName (or `name`)
 *  - addresses: ARRAY of { street, city, state, code(=ZIP), ... }  (NOT flat)
 *  - source: string (immutable after create)
 *  - assignedTo: display name string
 *  - custom fields: top-level `custom<CamelLabel>` key, only present with ?fields=allFields
 */
const { FUB } = require('./config');

function fullName(p) {
  if (p && p.name && String(p.name).trim()) return String(p.name).trim();
  const fn = (p && p.firstName) || '';
  const ln = (p && p.lastName) || '';
  return `${fn} ${ln}`.trim();
}

function primaryAddress(p) {
  const arr = (p && Array.isArray(p.addresses)) ? p.addresses : [];
  const a = arr[0];
  if (!a) return '';
  const line = [a.street, a.city, a.state].filter(Boolean).join(', ');
  return [line, a.code].filter(Boolean).join(' ').trim();
}

function fubLink(p) {
  const id = p && (p.id != null ? p.id : '');
  return id === '' ? '' : `${FUB.PERSON_URL_BASE}${id}`;
}

/** Build the field bag the message templates consume. */
function extractFields(p) {
  return {
    sellerName: fullName(p),
    address: primaryAddress(p),
    source: (p && p.source) || '',
    closer: (p && p.assignedTo) || '',
    leadManager: (p && p[FUB.LEAD_MANAGER_FIELD]) || '',
    fubLink: fubLink(p),
    stage: (p && p.stage) || '',
    personId: (p && p.id) || '',
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { extractFields, fullName, primaryAddress, fubLink };
}
