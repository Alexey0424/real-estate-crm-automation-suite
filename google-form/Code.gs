/**
 * Code.gs — AHB Seller Intake, hosted as a Google Apps Script WEB APP.
 *
 * ONE deployment does both jobs (Option 1 — Google hosts it, $0, no infra):
 *   • doGet()      → serves the branded HTML page (Index.html). This is the public
 *                    form URL the SMS agency opens.
 *   • submitLead() → called from the page (google.script.run, no CORS) when someone
 *                    submits. Assigns the round-robin Lead Manager, builds the FUB
 *                    /v1/events payload, and relays it to the Make Part-B webhook.
 *   • doPost(e)    → same logic from a raw JSON POST, so the page can later be moved
 *                    to a static host (Option 2) without changing the backend.
 *
 * HOW TO DEPLOY (≈2 min) — signed in as Alexey@acmehomebuyers.example:
 *   1. script.google.com → New project.
 *   2. Paste THIS file into Code.gs.
 *   3. File ▸ New ▸ HTML file, name it exactly `Index` (no .html), paste Index.html.
 *   4. Deploy ▸ New deployment ▸ type "Web app".
 *        - Execute as:  Me (alexey@acmehomebuyers.example)
 *        - Who has access:  Anyone   (so the SMS agency can open it without a Google login)
 *      Click Deploy, approve the permission prompt → copy the "Web app" URL.
 *   5. That URL *is* the live form. Share it with the SMS agency.
 *   NOTE: After editing either file, Deploy ▸ Manage deployments ▸ edit ▸ Version: New
 *      version, so the live URL serves the update.
 */

// Make Part-B webhook (scenario 5390808). Relays our payload → FUB /v1/events.
var WEBHOOK_URL = 'https://hook.us2.make.com/xxxxxxxxxxxxxxxxxxxxxxxx';

// Lead Managers, assigned in strict alternation (Ethan → Pam → Ethan → …).
var LEAD_MANAGERS = ['Ethan Rivers', 'Pam Alvarez'];


/** Serve the branded form page. */
function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('New Lead Intake | Acme Home Buyers')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1.0');
}

/** Called by the page (google.script.run). `data` = the form fields. */
function submitLead(data) {
  return processLead(data || {});
}

/** Raw JSON POST entry point (for hosting the page elsewhere later). */
function doPost(e) {
  var data = {};
  try { data = JSON.parse((e && e.postData && e.postData.contents) || '{}'); } catch (err) {}
  var ok = processLead(data);
  return ContentService
    .createTextOutput(JSON.stringify({ ok: ok }))
    .setMimeType(ContentService.MimeType.JSON);
}


/**
 * Strict round-robin across LEAD_MANAGERS, persisted in Script Properties and
 * guarded by a lock so two simultaneous submissions can't grab the same slot.
 */
function nextLeadManager() {
  var lock = LockService.getScriptLock();
  try { lock.waitLock(5000); } catch (err) { /* fall through with best effort */ }
  try {
    var props = PropertiesService.getScriptProperties();
    var n = parseInt(props.getProperty('lm_counter') || '0', 10);
    if (isNaN(n)) n = 0;
    var pick = LEAD_MANAGERS[n % LEAD_MANAGERS.length];
    props.setProperty('lm_counter', String(n + 1));
    return pick;
  } finally {
    try { lock.releaseLock(); } catch (err) {}
  }
}


/**
 * Build the FUB /v1/events payload from a submission and relay it to Make.
 * Returns true on a fired request. Throws on bad input so the page shows its error.
 */
function processLead(data) {
  var firstName = String(data.firstName || '').trim();
  var lastName  = String(data.lastName  || '').trim();
  var phone     = String(data.phone     || '').trim();
  var email     = String(data.email     || '').trim();
  var address   = String(data.propertyAddress || '').trim();
  var source    = String(data.leadSource || '').trim();
  var notes     = String(data.notes      || '').trim();

  // Never create a blank lead (the page already requires these, but double-guard).
  if (!firstName || !phone || !address || !source || !notes) {
    throw new Error('Missing required fields.');
  }

  var leadManager = nextLeadManager();

  var noteLines = ['Cold lead via SMS intake form.'];
  if (source)      noteLines.push('Lead source: ' + source);
  if (notes)       noteLines.push('Notes: ' + notes);
  if (leadManager) noteLines.push('Lead Manager: ' + leadManager);
  var noteText = noteLines.join('\n');

  var person = {
    firstName: firstName,
    lastName: lastName,
    stage: 'Lead',                       // constant (never a form field)
    tags: ['Cold Lead - SMS'],           // constant (never a form field)
    customLeadManager: leadManager       // FUB "Lead Manager" custom field → Part A routing
  };
  if (email)   person.emails    = [{ value: email }];
  if (phone)   person.phones    = [{ value: phone }];
  if (address) person.addresses = [{ street: address }];

  var fubBody = {
    source: source || 'Cold Lead - SMS',
    system: 'AHB',
    type: 'Registration',
    message: noteText,
    person: person
  };

  UrlFetchApp.fetch(WEBHOOK_URL, {
    method: 'post', contentType: 'application/json',
    payload: JSON.stringify({
      payload: JSON.stringify(fubBody),        // → relayed to FUB /v1/events
      noteBodyJson: JSON.stringify(noteText),  // → FUB /v1/notes "body" (pre-escaped)
      firstName: firstName, lastName: lastName,
      source: source, address: address, leadManager: leadManager
    }),
    muteHttpExceptions: true
  });

  return true;
}
