/**
 * test.js — fast, dependency-free assertions for the shared logic.
 * Run: `node shared/lib/test.js`  (exit 0 = all pass)
 *
 * This is the verification the n8n/Make builds inherit: the routing table,
 * closer resolution, catch-all, no-notify skips, phone normalization, and the
 * message templates are all proven here before they're embedded downstream.
 */
const assert = require('assert');
const { decide, resolveCloserChannel, isNoNotify } = require('./routing');
const { normalizeToE164 } = require('./phone');
const { buildMessage } = require('./format');
const { extractFields } = require('./fields');

let pass = 0;
const ok = (name, fn) => { fn(); pass++; console.log(`  ✓ ${name}`); };

console.log('routing — stage routes');
ok('route1 new lead (created at Lead) → newLeads', () => {
  const d = decide({ type: 'created', stage: 'Lead' });
  assert.equal(d.action, 'notify');
  assert.equal(d.channelKey, 'newLeads');
  assert.equal(d.template, 'newLead');
});
ok('route2 pending closer + Reyes → closerReyes', () => {
  const d = decide({ type: 'stage', stage: 'Pending Closer Contact', assignedTo: 'Reyes Smith' });
  assert.equal(d.action, 'notify');
  assert.equal(d.channelKey, 'closerReyes');
  assert.equal(d.template, 'prequalified');
});
ok('route2 pending closer, NO assignee → catch-all to leadManagers', () => {
  const d = decide({ type: 'stage', stage: 'Pending Closer Contact', assignedTo: '' });
  assert.equal(d.action, 'catchall');
  assert.equal(d.channelKey, 'leadManagers');
  assert.equal(d.template, 'catchall');
});
ok('route3 needs underwriting → underwriter', () => {
  assert.equal(decide({ type: 'stage', stage: 'Needs Underwriting' }).channelKey, 'underwriter');
});
ok('route4 make offer + Flora → closerFlora', () => {
  const d = decide({ type: 'stage', stage: 'Closer Needs To Make Offer', assignedTo: 'Flora R.' });
  assert.equal(d.channelKey, 'closerFlora');
  assert.equal(d.template, 'offerProvidedByUw');
});
ok('route5 offer submitted → closersChat', () => {
  assert.equal(decide({ type: 'stage', stage: 'Offer Submitted - Waiting to Hear Back' }).channelKey, 'closersChat');
});
ok('bare "Offer Rejected" stage does not exist → skip (only Future Follow Up exists)', () => {
  // Confirmed 2026-06-14: FUB has no bare "Offer Rejected" stage.
  assert.equal(decide({ type: 'stage', stage: 'Offer Rejected' }).action, 'skip');
});
ok('route5b offer rejected - future follow up → closersChat (Marco 2026-06-16)', () => {
  const d = decide({ type: 'stage', stage: 'Offer Rejected - Future Follow Up' });
  assert.equal(d.channelKey, 'closersChat');
  assert.equal(d.template, 'offerRejected');
});
ok('route6 needs contract → tc', () => {
  assert.equal(decide({ type: 'stage', stage: 'Needs Contract (Automatically Requested To TC)' }).channelKey, 'tc');
});
ok('route7 contract sent → closersChat (Marco 2026-06-16)', () => {
  assert.equal(decide({ type: 'stage', stage: 'Contract Sent' }).channelKey, 'closersChat');
});
ok('route8 under contract → dispo', () => {
  assert.equal(decide({ type: 'stage', stage: 'Under Contract' }).channelKey, 'dispo');
});
ok('route9 closed → teamWins', () => {
  assert.equal(decide({ type: 'stage', stage: 'Closed' }).channelKey, 'teamWins');
});

console.log('routing — closer resolution + fallback');
ok('case-insensitive + substring match (marco)', () => {
  assert.equal(resolveCloserChannel('MARCO DIAZ').channelKey, 'closerMarco');
});
ok('assigned to unmapped closer → fallback leadManagers (flagged)', () => {
  const d = decide({ type: 'stage', stage: 'Pending Closer Contact', assignedTo: 'Someone Else' });
  assert.equal(d.action, 'notify');
  assert.equal(d.channelKey, 'leadManagers');
  assert.equal(d.warnUnmappedCloser, true);
});

console.log('routing — skips');
ok('no-notify stage skipped', () => {
  assert.equal(isNoNotify('Cold - Follow Up'), true);
  assert.equal(decide({ type: 'stage', stage: 'Cold - Follow Up' }).action, 'skip');
});
ok('Offer Rejected - Future Follow Up now NOTIFIES closersChat (Marco 2026-06-16)', () => {
  assert.equal(decide({ type: 'stage', stage: 'Offer Rejected - Future Follow Up' }).action, 'notify');
});
ok('unknown/future stage falls through silently', () => {
  assert.equal(decide({ type: 'stage', stage: 'Brand New Stage 2027' }).action, 'skip');
});

console.log('phone — E.164 normalization');
ok('(215) 555 1234 → +12155551234', () => {
  assert.equal(normalizeToE164('(215) 555 1234').e164, '+12155551234');
});
ok('215-555-1234 → +12155551234', () => {
  assert.equal(normalizeToE164('215-555-1234').e164, '+12155551234');
});
ok('1 215 555 1234 → +12155551234', () => {
  assert.equal(normalizeToE164('1 215 555 1234').e164, '+12155551234');
});
ok('already +12155551234 stays', () => {
  assert.equal(normalizeToE164('+1 (215) 555-1234').e164, '+12155551234');
});
ok('garbage → invalid', () => {
  assert.equal(normalizeToE164('555-1234').valid, false);
});

console.log('fields — extraction from real FUB shape');
const sampleP = {
  id: 10763, firstName: 'Tom', lastName: 'Minch', stage: 'Lead', source: 'Spring Absentee PA',
  assignedTo: 'Reyes Smith', customLeadManager: 'Jane Doe',
  addresses: [{ street: '322 S Broadway', city: 'Los Angeles', state: 'CA', code: '90003' }],
};
ok('extract maps array address + custom field + link', () => {
  const f = extractFields(sampleP);
  assert.equal(f.sellerName, 'Tom Minch');
  assert.equal(f.address, '322 S Broadway, Los Angeles, CA 90003');
  assert.equal(f.leadManager, 'Jane Doe');
  assert.equal(f.closer, 'Reyes Smith');
  assert.ok(f.fubLink.endsWith('/10763'));
});

console.log('format — message templates');
ok('newLead text has heading + campaign + link', () => {
  const f = extractFields(sampleP);
  const m = buildMessage('newLead', f);
  assert.ok(m.text.includes('New Seller Lead'));
  assert.ok(m.text.includes('Marketing Campaign:'));
  assert.ok(m.text.includes('Open in FUB'));
  assert.ok(Array.isArray(m.blocks) && m.blocks.length >= 2);
});
ok('catchall renders stage + warning', () => {
  const f = extractFields(sampleP);
  f.stage = 'Pending Closer Contact';
  const m = buildMessage('catchall', f);
  assert.ok(m.text.includes('no closer assigned'));
  assert.ok(m.text.includes('Pending Closer Contact'));
});
ok('bold uses single asterisks, links use <url|text>', () => {
  const m = buildMessage('offerMade', extractFields(sampleP));
  assert.ok(!m.text.includes('**'));            // no markdown-style bold
  assert.ok(/<https?:\/\/[^|]+\|/.test(m.text)); // slack link form
});

console.log(`\nAll ${pass} assertions passed ✓`);
