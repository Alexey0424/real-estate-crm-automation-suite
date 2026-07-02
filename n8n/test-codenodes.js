/**
 * test-codenodes.js — execute the ACTUAL generated Code-node scripts (the shared
 * logic + the n8n entrypoint glue) against mock n8n inputs. This closes the gap
 * shared/lib/test.js doesn't cover: that the `$json` / `$('...')` wiring and the
 * returned item shape are correct in the built workflows.
 *
 * Run: `node n8n/test-codenodes.js`
 */
const assert = require('assert');
const path = require('path');

const partA = require('./workflows/partA-fub-slack.json');
const partB = require('./workflows/partB-form-fub.json');

const codeOf = (wf, nodeName) => wf.nodes.find((n) => n.name === nodeName).parameters.jsCode;

// Run a Code-node script with mocked n8n globals. The scripts end in `return`,
// so we wrap in a Function exposing $json and $ (the node-reference accessor).
function runNode(jsCode, $json, refs = {}) {
  const $ = (name) => ({ item: { json: refs[name] || {} } });
  return new Function('$json', '$', jsCode)($json, $);
}

let pass = 0;
const ok = (name, fn) => { fn(); pass++; console.log(`  ✓ ${name}`); };

const person = (over) => Object.assign({
  id: 10763, firstName: 'Tom', lastName: 'Minch', stage: 'Lead',
  source: 'Spring Absentee PA', assignedTo: '', customLeadManager: 'Jane Doe',
  addresses: [{ street: '322 S Broadway', city: 'Los Angeles', state: 'CA', code: '90003' }],
}, over);

console.log('Part A — Route + Build Message (generated Code node)');
const codeA = codeOf(partA, 'Route + Build Message');

ok('created @ Lead → notify newLeads (staging-aware)', () => {
  const out = runNode(codeA, person({ stage: 'Lead' }),
    { 'FUB Webhook': { body: { event: 'peopleCreated' } } });
  assert.equal(out.json.action, 'notify');
  assert.equal(out.json.channelKey, 'newLeads');           // env-independent
  assert.equal(out.json.channelName, 'staging-ahb-new-leads'); // current CHANNEL_ENV=staging
  assert.equal(out.json.channelId, 'C0PORTFOL11');
  assert.ok(Array.isArray(out.json.blocks));
  assert.ok(out.json.text.includes('New Seller Lead'));
});

ok('stage Pending Closer Contact + Reyes → closerReyes', () => {
  const out = runNode(codeA, person({ stage: 'Pending Closer Contact', assignedTo: 'Reyes Rivero' }),
    { 'FUB Webhook': { body: { event: 'peopleStageUpdated' } } });
  assert.equal(out.json.action, 'notify');
  assert.equal(out.json.channelKey, 'closerReyes');
  assert.equal(out.json.warnUnmappedCloser, false);
});

ok('stage Pending Closer Contact, no closer → catch-all leadManagers', () => {
  const out = runNode(codeA, person({ stage: 'Pending Closer Contact', assignedTo: '' }),
    { 'FUB Webhook': { body: { event: 'peopleStageUpdated' } } });
  assert.equal(out.json.action, 'catchall');
  assert.equal(out.json.channelKey, 'leadManagers');
  assert.ok(out.json.text.includes('no closer assigned'));
});

ok('no-notify stage → skip', () => {
  const out = runNode(codeA, person({ stage: 'Cold - Follow Up' }),
    { 'FUB Webhook': { body: { event: 'peopleStageUpdated' } } });
  assert.equal(out.json.action, 'skip');
});

console.log('Part B — Normalize form row (generated Code node)');
const codeB = codeOf(partB, 'Normalize form row');

ok('normalizes phone + splits name + hardcodes stage/tag', () => {
  const row = {
    'Seller Full Name': 'Maria De La Cruz',
    'Property Address(es)': '12 Oak St, Reading, PA 19601',
    'Seller Phone Number': '(215) 555 1234',
    'Seller Email Address': 'maria@example.com',
    'Lead Source / Campaign': 'Probate NJ Q2',
    'Market / State': 'PA',
    'Notes / Motivation / Reason for Selling': 'Inherited, wants quick close',
    'Property Type': 'SFH',
    'Submitted By': 'Agent B',
  };
  const out = runNode(codeB, row);
  assert.equal(out.json.firstName, 'Maria');
  assert.equal(out.json.lastName, 'De La Cruz');
  assert.equal(out.json.phone_e164, '+12155551234');
  assert.equal(out.json.stage, 'Lead');
  assert.equal(out.json.tag, 'Cold Lead - SMS');
  assert.ok(out.json.noteBody.includes('Submitted By: Agent B'));
  assert.ok(out.json.noteBody.includes('Probate NJ Q2') === false); // source isn't in note, campaign maps to FUB source
});

console.log(`\nAll ${pass} code-node assertions passed ✓`);
