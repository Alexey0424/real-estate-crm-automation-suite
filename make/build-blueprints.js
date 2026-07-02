/**
 * build-blueprints.js — generate DRAFT Make.com blueprints from shared config.
 *
 * NOTE: DRAFTS, NOT GUARANTEED IMPORTS. Make has no public blueprint schema; module
 * slugs (`follow-up-boss:*`, `slack:*`) + filter operator codes vary by the app
 * versions installed in YOUR org. Use these to SEE the structure / pre-fill the
 * stage+channel+message tables, then build per make/README.md, export the real
 * blueprint, and diff. The data baked in here (stages, channels, message text) is
 * the same single source of truth as the n8n build.
 *
 * Run: `node make/build-blueprints.js`
 */
const fs = require('fs');
const path = require('path');
const { ROUTES, chan, CLOSER_ROUTING } = require('../shared/lib/config');
const { buildMessage } = require('../shared/lib/format');

// Closer-routing switch() for the Slack Channel field (exact assignedTo full names).
const CLOSER_NAMES = { closerReyes: 'Reyes Rivero', closerFlora: 'Flora Stefoni', closerMarco: 'Marco Diaz' };
const closerSwitch = 'switch({{2.assignedTo}}; '
  + CLOSER_ROUTING.map((c) => `"${CLOSER_NAMES[c.channelKey]}"; "${chan(c.channelKey).id}"`).join('; ')
  + `; "${chan('leadManagers').id}")`; // else → lead-managers

// Placeholder field bag → message text with {{token}}s for Make to map.
const PH = {
  sellerName: '{{seller_name}}', address: '{{address}}', source: '{{source}}',
  closer: '{{closer}}', leadManager: '{{lead_manager}}', fubLink: '{{fub_link}}',
  stage: '{{stage}}',
};

let nid = 0;
const id = () => ++nid;

function slackModule(channelLabel, templateKey) {
  const msg = buildMessage(templateKey, PH);
  return {
    id: id(),
    module: 'slack:CreateMessage', // CONFIRM slug/version from a real export
    version: 1,
    parameters: { __IMTCONN__: 'REPLACE_SLACK_CONNECTION' },
    mapper: {
      channel: channelLabel, // prefer the channel ID once known (see fetch_slack_channels.py)
      text: msg.text,
      blocks: JSON.stringify({ blocks: msg.blocks }),
    },
    metadata: { designer: { x: 600, y: nid * 120 } },
  };
}

function stageRoute(route) {
  const channelLabel = route.channel === 'BY_CLOSER'
    ? closerSwitch
    : (chan(route.channel).id || `#${chan(route.channel).name}`);
  const slack = slackModule(channelLabel, route.template);
  slack.filter = {
    name: `${route.stage}`,
    conditions: [[{ a: '{{stage}}', o: 'text:equal:ci', b: route.stage }]], // CONFIRM operator code
  };
  if (route.requiresCloser) {
    slack.filter.name += ' (needs Assigned To; if empty → catch-all route)';
  }
  return { flow: [slack] };
}

function buildPartA() {
  const trigger = {
    id: id(),
    module: 'follow-up-boss:watchContactStageUpdated', // + a 'watch new contact' scenario for Route 1
    version: 1,
    parameters: { __IMTCONN__: 'REPLACE_FUB_CONNECTION', limit: 2 },
    mapper: {},
    metadata: { designer: { x: 0, y: 0 } },
  };
  const router = {
    id: id(), module: 'builtin:BasicRouter', version: 1, mapper: null,
    metadata: { designer: { x: 300, y: 0 } },
    routes: [],
  };
  // one route per stage-triggered ROUTE
  ROUTES.filter((r) => r.trigger === 'stage').forEach((r) => router.routes.push(stageRoute(r)));
  // catch-all / fallback route → lead-managers
  const fallback = slackModule(chan('leadManagers').id || '#lead-managers', 'catchall');
  fallback.filter = { name: 'Fallback — no closer / unmatched', conditions: [] };
  router.routes.push({ flow: [fallback] });

  return {
    name: 'AHB — Part A: FUB stage → Slack (DRAFT)',
    flow: [trigger, router],
    metadata: { instant: false, version: 1, zone: 'us1.make.com',
      scenario: { roundtrips: 1, maxErrors: 3, autoCommit: true, sequential: false, dlq: true },
      designer: { orphans: [] },
      notes: 'DRAFT scaffold. Add a second scenario (Watch new contact, filter Stage=Lead) for Route 1. Confirm module slugs + operator codes by exporting a real scenario.' },
  };
}

function buildPartB() {
  let bid = 0; const bI = () => ++bid;
  const watch = { id: bI(), module: 'google-sheets:watchRows', version: 1,
    parameters: { __IMTCONN__: 'REPLACE_GOOGLE_CONNECTION', spreadsheetId: 'REPLACE_SHEET_ID', sheetId: 'Form Responses 1', includesHeaders: true, limit: 25 },
    mapper: {}, metadata: { designer: { x: 0, y: 0 } } };
  const search = { id: bI(), module: 'follow-up-boss:searchContacts', version: 1,
    parameters: { __IMTCONN__: 'REPLACE_FUB_CONNECTION' },
    mapper: { phone: '{{normalized_phone_e164}}' }, metadata: { designer: { x: 300, y: 0 } } };
  const router = { id: bI(), module: 'builtin:BasicRouter', version: 1, mapper: null,
    metadata: { designer: { x: 600, y: 0 } }, routes: [
      { flow: [{ id: bI(), module: 'follow-up-boss:createNote', version: 1,
        parameters: { __IMTCONN__: 'REPLACE_FUB_CONNECTION' },
        filter: { name: 'Exists (dup) — add note only', conditions: [[{ a: '{{search.total}}', o: 'number:greater', b: '0' }]] },
        mapper: { contactId: '{{matched_contact_id}}', body: '{{cold_lead_note}}' },
        metadata: { designer: { x: 900, y: -120 } } }] },
      { flow: [{ id: bI(), module: 'follow-up-boss:createContact', version: 1,
        parameters: { __IMTCONN__: 'REPLACE_FUB_CONNECTION' },
        filter: { name: 'Fallback — new contact', conditions: [] },
        mapper: { stage: 'Lead', source: '{{source_campaign}}', tags: ['Cold Lead - SMS'],
          firstName: '{{first_name}}', lastName: '{{last_name}}',
          'emails[].value': '{{email}}', 'phones[].value': '{{normalized_phone_e164}}' },
        metadata: { designer: { x: 900, y: 120 } } }] },
    ] };
  return {
    name: 'AHB — Part B: Cold-lead form → FUB (DRAFT)',
    flow: [watch, search, router],
    metadata: { instant: false, version: 1, zone: 'us1.make.com',
      scenario: { roundtrips: 1, maxErrors: 3, autoCommit: true, sequential: false, dlq: true },
      designer: { orphans: [] },
      notes: 'DRAFT. Add phone-normalize (Set variable) before search; add Create-note after Create-contact; stage/tag are constants. No Slack here — Part A Route 1 fires on the created contact.' },
  };
}

const OUT = path.join(__dirname, 'blueprints');
fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(path.join(OUT, 'partA-fub-slack.blueprint.draft.json'), JSON.stringify(buildPartA(), null, 2));
fs.writeFileSync(path.join(OUT, 'partB-form-fub.blueprint.draft.json'), JSON.stringify(buildPartB(), null, 2));
console.log('Wrote draft blueprints to', OUT);
