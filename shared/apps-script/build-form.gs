/**
 * build-form.gs — ALL-IN-ONE builder for the AHB Cold-Lead Intake Google Form.
 *
 * Running buildColdLeadForm() once will:
 *   1. Create the Google Form with all 9 SOW fields (dropdowns, required flags,
 *      phone/email validation).
 *   2. Install an onFormSubmit trigger.
 *   3. Wire submissions → the Make Part-B webhook (builds the full FUB /v1/events
 *      payload here: name split, note, omit empty optionals, Market/State, tag).
 *
 * HOW TO RUN (≈1 min):
 *   1. script.google.com → New project (signed in as Alexey@acmehomebuyers.example).
 *   2. Paste this whole file. Save (disk icon).
 *   3. Pick `buildColdLeadForm` in the function dropdown → click Run.
 *      Approve the permission prompt (it's your own account).
 *   4. View → Logs (or Executions) → copy the "Live form" URL to share with the
 *      SMS agency, and the "Edit" URL to tweak it.
 *   NOTE: Run buildColdLeadForm ONCE — re-running creates a second form + trigger.
 *
 * Edit CAMPAIGNS and SMS_AGENTS to Marco's real values (placeholders for now).
 * The other dropdowns are fixed by the SOW.
 */

var WEBHOOK_URL = 'https://hook.us2.make.com/xxxxxxxxxxxxxxxxxxxxxxxx';

var CAMPAIGNS  = ['SMS agency']; // only campaign so far — add more entries here as they come
var SMS_AGENTS = ['Haider'];     // only SMS agent so far — add more entries here as they come
var MARKETS    = ['PA', 'NJ', 'IN', 'TN', 'NC', 'Other'];                  // fixed by SOW
var PROP_TYPES = ['SFH', 'Condo', 'Multi', 'Land', 'Other'];               // fixed by SOW

// Id of the already-built form (from build's Edit URL) — used by updateDropdowns().
var FORM_ID = '1KzrSaEQAzoiH8Ym7wOYCB4I7QPy4O79YLtEx80w1dTk';


function buildColdLeadForm() {
  var form = FormApp.create('AHB Cold Lead Intake (SMS Agency)')
    .setDescription('Upload cold seller leads here. Fields marked * are required. ' +
                    'Leads are created in Follow Up Boss at stage "Lead" automatically.')
    .setCollectEmail(false);

  // 1. Seller Full Name *
  form.addTextItem().setTitle('Seller Full Name').setRequired(true);

  // 2. Property Address * (paragraph — SOW allows multiple addresses, one per line)
  form.addParagraphTextItem()
    .setTitle('Property Address')
    .setHelpText('Street, City, State, ZIP. More than one property? One address per line.')
    .setRequired(true);

  // 3. Seller Phone Number * (format hint + permissive validation)
  var phoneOk = FormApp.createTextValidation()
    .setHelpText('Enter a 10-digit US phone, e.g. (215) 555 1234')
    .requireTextMatchesPattern('^\\(?\\d{3}\\)?[\\s.\\-]?\\d{3}[\\s.\\-]?\\d{4}$')
    .build();
  form.addTextItem()
    .setTitle('Seller Phone Number')
    .setHelpText('Format: (215) 555 1234')
    .setRequired(true)
    .setValidation(phoneOk);

  // 4. Seller Email Address (optional, validated)
  var emailOk = FormApp.createTextValidation()
    .setHelpText('Enter a valid email address.').requireTextIsEmail().build();
  form.addTextItem().setTitle('Seller Email Address').setRequired(false).setValidation(emailOk);

  // 5. Lead Source / Campaign * (dropdown — keeps Source never blank)
  form.addListItem().setTitle('Lead Source / Campaign').setChoiceValues(CAMPAIGNS).setRequired(true);

  // 6. Market / State *
  form.addListItem().setTitle('Market / State').setChoiceValues(MARKETS).setRequired(true);

  // 7. Notes / Motivation / Reason for Selling (optional)
  form.addParagraphTextItem().setTitle('Notes / Motivation / Reason for Selling').setRequired(false);

  // 8. Property Type (optional)
  form.addListItem().setTitle('Property Type').setChoiceValues(PROP_TYPES).setRequired(false);

  // 9. Submitted By * (dropdown of SMS agents — avoids typos)
  form.addListItem().setTitle('Submitted By').setChoiceValues(SMS_AGENTS).setRequired(true);

  // install the submit → webhook trigger (idempotent: clear any prior ones first)
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'onFormSubmit') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('onFormSubmit').forForm(form).onFormSubmit().create();

  Logger.log('[x] Form built. Share the LIVE url with the SMS agency.');
  Logger.log('Live form: ' + form.getPublishedUrl());
  Logger.log('Edit URL:  ' + form.getEditUrl());
}


/**
 * Update the two dynamic dropdowns (Lead Source/Campaign + Submitted By) on the
 * EXISTING form, in place — does NOT create a new form. Run this after editing
 * CAMPAIGNS / SMS_AGENTS above (e.g. when the agency adds campaigns or agents).
 * Keeps both as dropdowns.
 */
function updateDropdowns() {
  var form = FormApp.openById(FORM_ID);
  form.getItems(FormApp.ItemType.LIST).forEach(function (it) {
    var li = it.asListItem(), t = it.getTitle();
    if (t === 'Lead Source / Campaign') li.setChoiceValues(CAMPAIGNS);
    if (t === 'Submitted By')           li.setChoiceValues(SMS_AGENTS);
  });
  Logger.log('Updated dropdowns -> Lead Source: ' + CAMPAIGNS + ' | Submitted By: ' + SMS_AGENTS);
}


/**
 * Fires on every submission. Builds the full FUB /v1/events payload and POSTs it
 * (plus display fields) to the Make webhook. Uses e.response (form-bound trigger).
 */
function onFormSubmit(e) {
  if (!e || !e.response) return;
  var map = {};
  e.response.getItemResponses().forEach(function (ir) {
    map[ir.getItem().getTitle()] = String(ir.getResponse() || '').trim();
  });
  function get(names) {
    for (var i = 0; i < names.length; i++) { if (map[names[i]]) return map[names[i]]; }
    return '';
  }

  var fullName     = get(['Seller Full Name']);
  var address      = get(['Property Address']);
  var phone        = get(['Seller Phone Number']);
  var email        = get(['Seller Email Address']);
  var source       = get(['Lead Source / Campaign']);
  var marketState  = get(['Market / State']);
  var motivation   = get(['Notes / Motivation / Reason for Selling']);
  var propertyType = get(['Property Type']);
  var submittedBy  = get(['Submitted By']);

  var first = fullName, last = '';
  if (fullName.indexOf(' ') > -1) {
    var parts = fullName.split(/\s+/); first = parts.shift(); last = parts.join(' ');
  }

  var noteLines = ['Cold lead via SMS agency Google Form.'];
  if (motivation)   noteLines.push('Reason for selling: ' + motivation);
  if (propertyType) noteLines.push('Property type: ' + propertyType);
  if (marketState)  noteLines.push('Market/State: ' + marketState);  // captured even if "Other"
  if (submittedBy)  noteLines.push('Submitted by (SMS agent): ' + submittedBy);
  var noteText = noteLines.join('\n');

  var person = { firstName: first, lastName: last, stage: 'Lead', tags: ['Cold Lead - SMS'] };
  if (email)       person.emails = [{ value: email }];
  if (phone)       person.phones = [{ value: phone }];
  if (address)     person.addresses = [{ street: address }];
  if (marketState) person.customMarketState = marketState;  // maps for PA/NJ/IN/TN/NC; "Other" ignored by FUB

  var fubBody = {
    source: source || 'Cold Lead - SMS', system: 'AHB', type: 'Registration',
    message: noteText, person: person
  };

  if (!phone && !email) return;  // never create a blank lead

  UrlFetchApp.fetch(WEBHOOK_URL, {
    method: 'post', contentType: 'application/json',
    payload: JSON.stringify({
      payload: JSON.stringify(fubBody),       // → relayed to FUB /v1/events
      noteBodyJson: JSON.stringify(noteText), // → FUB /v1/notes "body" (pre-escaped JSON string)
      firstName: first, lastName: last, source: source, address: address
    }),
    muteHttpExceptions: true
  });
}
