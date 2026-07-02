/**
 * build-workflows.js — assemble the importable n8n workflow JSON for Part A and
 * Part B from the EXACT node shapes verified against n8n master (June 2026) and
 * the SAME tested logic in shared/lib (concatenated into the Code nodes, so the
 * n8n build can't drift from the unit-tested routing/format/phone code).
 *
 * Run: `node n8n/build-workflows.js`  → writes n8n/workflows/*.json
 */
const fs = require('fs');
const path = require('path');

const LIB = path.join(__dirname, '..', 'shared', 'lib');
const OUT = path.join(__dirname, 'workflows');

// Concatenate the shared logic into one self-contained script for a Code node.
// Strip the `const {..} = require('./x')` lines (config consts are already in
// scope once config.js is first). The `module.exports` guards are inert in n8n
// (where `module` is undefined) so they can stay.
function loadLib(name) {
  const src = fs.readFileSync(path.join(LIB, `${name}.js`), 'utf8');
  // Remove the whole `const X = require(...)` / `const { ... } = require(...)`
  // statement — multi-line-safe (the destructure braces can span lines). The
  // destructured names already exist from config.js's top-level consts.
  return src.replace(/const\s+(?:\{[^}]*\}|[\w$]+)\s*=\s*require\([^)]*\);?/g, '');
}
const SHARED = ['config', 'phone', 'fields', 'format', 'routing']
  .map(loadLib)
  .join('\n\n// ----------------------------------------\n\n');

// ── Part A Code node: decide route + build message from the GET'd person ──────
const CODE_A = SHARED + `

// ===== n8n entrypoint (Part A) =====
const person = $json;                       // FUB GET /v1/people/{id}?fields=allFields
const ev = (($('FUB Webhook').item.json.body) || {}).event || '';
const type = ev === 'peopleCreated' ? 'created' : (ev === 'peopleStageUpdated' ? 'stage' : 'unknown');
const decision = decide({ type: type, stage: person.stage, assignedTo: person.assignedTo });
if (decision.action === 'skip') {
  return { json: { action: 'skip', reason: decision.reason, stage: person.stage } };
}
const f = extractFields(person);
f.stage = person.stage;
const msg = buildMessage(decision.template, f);
const ch = chan(decision.channelKey); // staging/prod aware (CHANNEL_ENV in config)
return { json: {
  action: decision.action,
  routeKey: decision.routeKey,
  channelKey: decision.channelKey,
  channelId: ch.id || '',
  channelName: ch.name,
  text: msg.text,
  blocks: msg.blocks,
  warnUnmappedCloser: !!decision.warnUnmappedCloser,
  reason: decision.reason,
} };
`;

// ── Part B Code node: normalize a form row into FUB fields ────────────────────
const CODE_B_NORMALIZE = SHARED + `

// ===== n8n entrypoint (Part B — normalize form row) =====
const row = $json;                          // Google Sheets Trigger row (keyed by header)
const g = (k) => (row[k] == null ? '' : String(row[k])).trim();
const name = g('Seller Full Name');
const parts = name.split(/\\s+/).filter(Boolean);
const firstName = parts.shift() || '';
const lastName = parts.join(' ');
const ph = normalizeToE164(g('Seller Phone Number'));
const email = g('Seller Email Address');
const source = g('Lead Source / Campaign');
const market = g('Market / State');
const address = g('Property Address(es)');
const propertyType = g('Property Type');
const notes = g('Notes / Motivation / Reason for Selling');
const submittedBy = g('Submitted By');
const noteBody = [
  'Cold SMS lead via Google Form',
  submittedBy ? 'Submitted By: ' + submittedBy : '',
  market ? 'Market: ' + market : '',
  propertyType ? 'Property Type: ' + propertyType : '',
  address ? 'Address(es): ' + address : '',
  notes ? 'Notes: ' + notes : '',
].filter(Boolean).join('\\n');
return { json: {
  firstName: firstName, lastName: lastName, name: name,
  phone_e164: ph.e164 || '', phone_valid: ph.valid,
  email: email, source: source, market: market, address: address,
  propertyType: propertyType, submittedBy: submittedBy, noteBody: noteBody,
  stage: INTAKE.HARDCODED_STAGE, tag: INTAKE.HARDCODED_TAG,
} };
`;

// ── Part B Code node: pick the matched person id from the two searches ────────
const CODE_B_MATCH = `
// ===== n8n entrypoint (Part B — decide match) =====
function firstId(r) { const a = r && r.people; return (Array.isArray(a) && a.length) ? a[0].id : null; }
const byPhone = $('Search by phone').item.json;
const byEmail = $('Search by email').item.json;
const matchedId = firstId(byPhone) || firstId(byEmail) || '';
const data = $('Normalize form row').item.json;
return { json: Object.assign({}, data, { matchedId: matchedId }) };
`;

// ── node factory helpers ──────────────────────────────────────────────────────
let _id = 0;
const uid = () => `node-${String(++_id).padStart(4, '0')}-0000-4000-8000-000000000000`;

function node(name, type, typeVersion, parameters, pos, extra = {}) {
  return Object.assign(
    { parameters, id: uid(), name, type, typeVersion, position: pos },
    extra
  );
}

// Sticky-note documentation node (renders as a colored markdown box behind a
// group of real nodes). Node names must be unique → pass a unique `name`.
function sticky(name, content, pos, width, height, color) {
  return {
    parameters: { content, height, width, color },
    id: uid(),
    name,
    type: 'n8n-nodes-base.stickyNote',
    typeVersion: 1,
    position: pos,
  };
}
const FUB_CRED = { httpBasicAuth: { id: 'REPLACE_FUB_BASIC', name: 'FUB Basic Auth' } };
const SLACK_CRED = { slackApi: { id: 'REPLACE_SLACK', name: 'Slack (AHB bot)' } };
const SHEETS_CRED = { googleSheetsTriggerOAuth2Api: { id: 'REPLACE_SHEETS', name: 'Google Sheets (AHB)' } };

function wrap(nodes, connections, name, active = false, id = undefined) {
  return {
    id,
    name,
    nodes,
    connections,
    settings: { executionOrder: 'v1', saveDataErrorExecution: 'all', saveDataSuccessExecution: 'all' },
    active,
    pinData: {},
    meta: { templateId: 'ahb-fub-slack' },
  };
}

// ============================== PART A ========================================
function buildPartA() {
  const webhook = node('FUB Webhook', 'n8n-nodes-base.webhook', 2.1, {
    httpMethod: 'POST', path: 'fub-events', responseMode: 'onReceived', options: {},
  }, [240, 300], { webhookId: 'fub-events' });

  const getPerson = node('FUB Get Person', 'n8n-nodes-base.httpRequest', 4.2, {
    method: 'GET',
    url: '=https://api.followupboss.com/v1/people/{{ $json.body.resourceIds[0] }}',
    authentication: 'genericCredentialType', genericAuthType: 'httpBasicAuth',
    sendQuery: true,
    queryParameters: { parameters: [{ name: 'fields', value: 'allFields' }] },
    options: {},
  }, [460, 300], { credentials: FUB_CRED, retryOnFail: true, maxTries: 3, waitBetweenTries: 2000 });

  const code = node('Route + Build Message', 'n8n-nodes-base.code', 2, {
    mode: 'runOnceForEachItem', language: 'javaScript', jsCode: CODE_A,
  }, [680, 300]);

  const ifSkip = node('Skip?', 'n8n-nodes-base.if', 2.2, {
    options: {},
    conditions: {
      options: { version: 2, leftValue: '', caseSensitive: true, typeValidation: 'strict' },
      combinator: 'and',
      conditions: [{
        id: uid(), leftValue: '={{ $json.action }}', rightValue: 'skip',
        operator: { type: 'string', operation: 'equals' },
      }],
    },
  }, [900, 300]);

  const noop = node('No notification', 'n8n-nodes-base.noOp', 1, {}, [1120, 200]);

  const slack = node('Post to Slack', 'n8n-nodes-base.slack', 2.5, {
    resource: 'message', operation: 'post', select: 'channel',
    channelId: { __rl: true, value: '={{ $json.channelId }}', mode: 'id' },
    messageType: 'block',
    blocksUi: '={{ JSON.stringify({ blocks: $json.blocks }) }}',
    otherOptions: { text: '={{ $json.text }}' },
  }, [1120, 400], { credentials: SLACK_CRED, retryOnFail: true, maxTries: 3, waitBetweenTries: 2000 });

  const connections = {
    'FUB Webhook': { main: [[{ node: 'FUB Get Person', type: 'main', index: 0 }]] },
    'FUB Get Person': { main: [[{ node: 'Route + Build Message', type: 'main', index: 0 }]] },
    'Route + Build Message': { main: [[{ node: 'Skip?', type: 'main', index: 0 }]] },
    // IF: output 0 = true (skip → NoOp), output 1 = false (post → Slack)
    'Skip?': { main: [
      [{ node: 'No notification', type: 'main', index: 0 }],
      [{ node: 'Post to Slack', type: 'main', index: 0 }],
    ] },
  };

  const docs = [
    sticky('doc-overview',
      '## 📣 PART A — Follow Up Boss → Slack stage notifications\n' +
      'When a lead is **created** or its **stage changes** in FUB, post a formatted message to the right Slack channel.\n\n' +
      'Two FUB webhooks (`peopleCreated`, `peopleStageUpdated`) point at the **one** Webhook URL below; the flow fetches the full record, decides the route, and posts. Channels are environment-aware (staging/prod) via `CHANNEL_ENV` in the shared config.',
      [200, 20], 1140, 120, 7),
    sticky('doc-1-receive',
      '### ① Receive & fetch the lead\n' +
      '**FUB Webhook** — receives FUB’s `peopleCreated` / `peopleStageUpdated` events. Payload is *thin* (`event`, `resourceIds`, `uri`).\n\n' +
      '**FUB Get Person** — GETs `/v1/people/{id}?fields=allFields` (HTTP Basic, API key = user). NOTE: `fields=allFields` is **required** or the *Lead Manager* custom field is missing. Retries 3× on failure.',
      [200, 160], 440, 380, 5),
    sticky('doc-2-route',
      '### ② Decide the route\n' +
      '**Route + Build Message** (Code) runs the shared routing logic:\n' +
      '• stage → channel (Routes 1–9)\n' +
      '• closer stages routed by `Assigned To` (Reyes / Flora / Marco)\n' +
      '• closer stage with no `Assigned To` → catch-all to **#lead-managers**\n' +
      '• no-notify / unknown stages → **skip**\n\n' +
      'Outputs the target channel **ID** + the Block Kit message.',
      [660, 160], 220, 380, 6),
    sticky('doc-3-post',
      '### ③ Post to Slack (or skip)\n' +
      '**Skip?** (IF) — if the router said `skip`, route to **No notification** (intentional dead-end; nothing posts).\n\n' +
      'Otherwise → **Post to Slack** — posts the Block Kit message to the chosen channel **by ID** (bot token, retries 3×).',
      [900, 160], 460, 380, 4),
  ];
  return wrap([...docs, webhook, getPerson, code, ifSkip, noop, slack], connections,
    'AHB — Part A: FUB → Slack stage notifications', false, 'ahbFubSlackPartA');
}

// ============================== PART B ========================================
function buildPartB() {
  const trigger = node('Form Responses Trigger', 'n8n-nodes-base.googleSheetsTrigger', 1, {
    pollTimes: { item: [{ mode: 'everyMinute' }] },
    documentId: { __rl: true, value: 'REPLACE_SHEET_ID', mode: 'id' },
    sheetName: { __rl: true, value: 'gid=0', mode: 'list', cachedResultName: 'Form Responses 1' },
    event: 'rowAdded', options: {},
  }, [240, 300], { credentials: SHEETS_CRED });

  const normalize = node('Normalize form row', 'n8n-nodes-base.code', 2, {
    mode: 'runOnceForEachItem', language: 'javaScript', jsCode: CODE_B_NORMALIZE,
  }, [460, 300]);

  const searchPhone = node('Search by phone', 'n8n-nodes-base.httpRequest', 4.2, {
    method: 'GET', url: 'https://api.followupboss.com/v1/people',
    authentication: 'genericCredentialType', genericAuthType: 'httpBasicAuth',
    sendQuery: true,
    queryParameters: { parameters: [
      { name: 'phone', value: '={{ $json.phone_e164 }}' },
      { name: 'fields', value: 'allFields' },
    ] },
    options: {},
  }, [680, 300], { credentials: FUB_CRED, onError: 'continueRegularOutput', retryOnFail: true, maxTries: 2 });

  const searchEmail = node('Search by email', 'n8n-nodes-base.httpRequest', 4.2, {
    method: 'GET', url: 'https://api.followupboss.com/v1/people',
    authentication: 'genericCredentialType', genericAuthType: 'httpBasicAuth',
    sendQuery: true,
    queryParameters: { parameters: [
      // empty email → sentinel that can't match, so we never false-merge
      { name: 'email', value: "={{ $('Normalize form row').item.json.email || 'no-match-sentinel@example.invalid' }}" },
      { name: 'fields', value: 'allFields' },
    ] },
    options: {},
  }, [900, 300], { credentials: FUB_CRED, onError: 'continueRegularOutput', retryOnFail: true, maxTries: 2 });

  const decideMatch = node('Decide match', 'n8n-nodes-base.code', 2, {
    mode: 'runOnceForEachItem', language: 'javaScript', jsCode: CODE_B_MATCH,
  }, [1120, 300]);

  const ifNew = node('Existing?', 'n8n-nodes-base.if', 2.2, {
    options: {},
    conditions: {
      options: { version: 2, leftValue: '', caseSensitive: true, typeValidation: 'strict' },
      combinator: 'and',
      conditions: [{
        id: uid(), leftValue: '={{ $json.matchedId }}', rightValue: '',
        operator: { type: 'string', operation: 'notEmpty', singleValue: true },
      }],
    },
  }, [1340, 300]);

  // true (exists) → add note to existing; false (new) → create person then note
  const createPerson = node('Create FUB person', 'n8n-nodes-base.httpRequest', 4.2, {
    method: 'POST', url: 'https://api.followupboss.com/v1/people',
    authentication: 'genericCredentialType', genericAuthType: 'httpBasicAuth',
    sendBody: true, contentType: 'json', specifyBody: 'json',
    // customMarketState dropdown accepts PA/NJ/IN/TN/NC (confirmed); "Other" is not
    // an option, so omit it. JSON.stringify drops undefined keys.
    jsonBody: '={{ JSON.stringify({ firstName: $json.firstName, lastName: $json.lastName, stage: $json.stage, source: $json.source, tags: [$json.tag], customMarketState: ($json.market && $json.market !== "Other" ? $json.market : undefined), emails: ($json.email ? [{ value: $json.email }] : []), phones: ($json.phone_e164 ? [{ value: $json.phone_e164 }] : []) }) }}',
    options: {},
  }, [1560, 400], { credentials: FUB_CRED, retryOnFail: true, maxTries: 3, waitBetweenTries: 2000 });

  const noteNew = node('Note (new)', 'n8n-nodes-base.httpRequest', 4.2, {
    method: 'POST', url: 'https://api.followupboss.com/v1/notes',
    authentication: 'genericCredentialType', genericAuthType: 'httpBasicAuth',
    sendBody: true, contentType: 'json', specifyBody: 'json',
    jsonBody: "={{ JSON.stringify({ personId: $json.id, subject: 'Cold SMS Lead', body: $('Decide match').item.json.noteBody }) }}",
    options: {},
  }, [1780, 400], { credentials: FUB_CRED, retryOnFail: true, maxTries: 3 });

  const noteExisting = node('Note (existing)', 'n8n-nodes-base.httpRequest', 4.2, {
    method: 'POST', url: 'https://api.followupboss.com/v1/notes',
    authentication: 'genericCredentialType', genericAuthType: 'httpBasicAuth',
    sendBody: true, contentType: 'json', specifyBody: 'json',
    jsonBody: "={{ JSON.stringify({ personId: $json.matchedId, subject: 'Cold SMS Lead (dup — updated)', body: $json.noteBody }) }}",
    options: {},
  }, [1560, 200], { credentials: FUB_CRED, retryOnFail: true, maxTries: 3 });

  const connections = {
    'Form Responses Trigger': { main: [[{ node: 'Normalize form row', type: 'main', index: 0 }]] },
    'Normalize form row': { main: [[{ node: 'Search by phone', type: 'main', index: 0 }]] },
    'Search by phone': { main: [[{ node: 'Search by email', type: 'main', index: 0 }]] },
    'Search by email': { main: [[{ node: 'Decide match', type: 'main', index: 0 }]] },
    'Decide match': { main: [[{ node: 'Existing?', type: 'main', index: 0 }]] },
    'Existing?': { main: [
      [{ node: 'Note (existing)', type: 'main', index: 0 }],   // true = exists
      [{ node: 'Create FUB person', type: 'main', index: 0 }], // false = new
    ] },
    'Create FUB person': { main: [[{ node: 'Note (new)', type: 'main', index: 0 }]] },
  };

  const docs = [
    sticky('doc-overview',
      '## 📝 PART B — Cold-lead form → Follow Up Boss\n' +
      'The SMS agency submits leads via a **Google Form → linked Sheet**. Each new row creates (or updates) a FUB person at stage **Lead**, tagged **Cold Lead - SMS**, deduped by phone/email.\n\n' +
      'No Slack here — the created person triggers **Part A’s Route 1** notification.',
      [200, 20], 1800, 120, 7),
    sticky('doc-1-intake',
      '### ① Intake & normalize\n' +
      '**Form Responses Trigger** — polls the linked Google Sheet (“Form Responses 1”) for new rows.\n\n' +
      '**Normalize form row** (Code) — splits name, normalizes phone to **E.164**, maps Market/State → `customMarketState`, hardcodes stage **Lead** + tag **Cold Lead - SMS**, and builds the note body.',
      [200, 160], 440, 380, 5),
    sticky('doc-2-dedupe',
      '### ② Dedupe lookup (no duplicates)\n' +
      '**Search by phone** — FUB `/people?phone=` (E.164, exact match).\n\n' +
      '**Search by email** — FUB `/people?email=` (uses a sentinel when email is blank so it can’t false-match).\n\n' +
      '**Decide match** (Code) — picks the matched person id (phone first, then email), or empty if none.',
      [660, 160], 640, 380, 6),
    sticky('doc-3-write',
      '### ③ Create or update + note\n' +
      '**Existing?** (IF) — is there a matched person id?\n\n' +
      '• **Yes →** **Note (existing)**: adds the cold-lead note to the existing record (no duplicate created).\n\n' +
      '• **No →** **Create FUB person** (stage Lead, source = campaign, tag Cold Lead - SMS, Market/State), then **Note (new)** adds the note.',
      [1320, 160], 680, 380, 4),
  ];
  return wrap(
    [...docs, trigger, normalize, searchPhone, searchEmail, decideMatch, ifNew, createPerson, noteNew, noteExisting],
    connections, 'AHB — Part B: Cold-lead form → FUB', false, 'ahbColdLeadFormPartB');
}

// ── write ─────────────────────────────────────────────────────────────────────
fs.mkdirSync(OUT, { recursive: true });
const a = buildPartA();
_id = 0; // reset id counter between workflows for stable output
const b = buildPartB();
fs.writeFileSync(path.join(OUT, 'partA-fub-slack.json'), JSON.stringify(a, null, 2));
fs.writeFileSync(path.join(OUT, 'partB-form-fub.json'), JSON.stringify(b, null, 2));
console.log('Wrote partA-fub-slack.json (%d nodes) and partB-form-fub.json (%d nodes)',
  a.nodes.length, b.nodes.length);
