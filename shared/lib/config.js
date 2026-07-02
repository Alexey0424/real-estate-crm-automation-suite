/**
 * config.js — SINGLE SOURCE OF TRUTH for the AHB FUB → Slack notification system.
 *
 * Both implementations (n8n and Make.com) are built FROM this file so they can
 * never drift apart. The tested logic in routing.js / phone.js / format.js
 * consumes these tables. The n8n Code nodes embed copies of the tested functions;
 * the Make build mirrors the same tables in its modules.
 *
 * Anything marked `CONFIRM:` is a reconciliation decision we made to unblock the
 * build — it MUST be verified with Marco / against the live FUB account before
 * acceptance. See docs/architecture.md §"Ambiguities".
 */

// ── FUB account-specific values Alexey must fill once (run shared/fub-scripts) ──
const FUB = {
  // GET /v1/people/view link base. UNVERIFIED in FUB docs — confirm by opening a
  // real record in the browser and copying the URL. (Research flagged this.)
  PERSON_URL_BASE: 'https://app.followupboss.com/2/people/view/', // + personId

  // The "Lead Manager" custom field. CONFIRMED 2026-06-14 via GET /v1/customFields
  // (label "Lead Manager", type dropdown).
  LEAD_MANAGER_FIELD: 'customLeadManager',

  // Market/State custom field (dropdown) — CONFIRMED present. Part B can write
  // the form's Market/State here (values must match the dropdown's options).
  MARKET_STATE_FIELD: 'customMarketState',

  API_BASE: 'https://api.followupboss.com/v1',
};

// ── Slack channel registry (STAGING + PROD) ─────────────────────────────────
// Two environments because the team already created `staging-*` channels for
// testing (confirmed live 2026-06-14). Test against STAGING, then flip
// CHANNEL_ENV to 'prod' at cutover. Post by immutable ID (names rename → silent
// breakage); staging IDs are real (fetched), prod IDs are filled as channels are
// created / the bot is invited.  `''` id → the Slack node posts by name instead.
const CHANNEL_ENV = 'staging'; // 'staging' | 'prod'  ← flip to 'prod' for go-live

// Prod IDs fetched live 2026-06-14 after the bot was invited (most are PRIVATE).
const CHANNELS = {
  newLeads:     { prod: { name: 'all-ahb-new-leads',  id: 'C0PORTFOL01' },   staging: { name: 'staging-ahb-new-leads',     id: 'C0PORTFOL11' } },
  underwriter:  { prod: { name: 'underwriter-to-dos', id: 'C0PORTFOL02' },   staging: { name: 'staging-underwriter-to-dos', id: 'C0PORTFOL12' } },
  closersChat:  { prod: { name: 'closers-chat',       id: 'C0PORTFOL03' },   staging: { name: 'staging-closers-chat',       id: 'C0PORTFOL13' } },
  tc:         { prod: { name: 'tc-to-dos',         id: 'C0PORTFOL04' },   staging: { name: 'staging-tc-to-dos',        id: 'C0PORTFOL14' } },
  dispo:        { prod: { name: 'dispo-external-chat', id: 'C0PORTFOL05' },   staging: { name: 'staging-internal-dispo-chat', id: 'C0PORTFOL15' } }, // prod = dispo-EXTERNAL (SOW template was right)
  teamWins:     { prod: { name: 'team-wins',           id: 'C0PORTFOL06' },   staging: { name: 'team-wins',                  id: 'C0PORTFOL06' } }, // no staging variant
  leadManagers: { prod: { name: 'lead-managers',       id: 'C0PORTFOL07' },   staging: { name: '',                          id: '' } },
  closerReyes:    { prod: { name: 'closer-deals-reyes',    id: 'C0PORTFOL08' },   staging: { name: '',                          id: '' } },
  closerFlora:   { prod: { name: 'closer-deals-flora',   id: 'C0PORTFOL09' },   staging: { name: '',                          id: '' } },
  closerMarco:   { prod: { name: 'closer-deals-marco',   id: 'C0PORTFOL10' },   staging: { name: '',                          id: '' } },
  // (closer-deals-nick removed 2026-06-14 — Ned no longer with the team)
};

// Resolve a channel for the active env; fall back to prod if no staging variant.
function chan(key) {
  const c = CHANNELS[key];
  if (!c) return { name: key, id: '' };
  const e = c[CHANNEL_ENV] || {};
  if (e.name) return e;
  return c.prod || { name: key, id: '' };
}

// ── Closer routing: match on the FUB `assignedTo` display name (case-insensitive
//    "contains"). Order matters only if names overlap (they don't here). ────────
const CLOSER_ROUTING = [
  { contains: 'reyes',  channelKey: 'closerReyes'  },
  { contains: 'flora', channelKey: 'closerFlora' },
  { contains: 'marco', channelKey: 'closerMarco' },
];
// If assignedTo is set but matches none of the above → ADDED SAFETY (not in SOW):
// route to leadManagers with an "unmapped closer" note instead of dropping it.
const CLOSER_FALLBACK_CHANNEL = 'leadManagers';

// ── Stage routes. `key` is an internal id; `stage` is the EXACT FUB stage string
//    (CONFIRM every one against GET /v1/stages — filters must match exactly). ───
// trigger: 'created'  → fires on contact-created webhook (peopleCreated)
//          'stage'    → fires on stage-changed webhook (peopleStageUpdated)
// channel: a CHANNELS key, OR 'BY_CLOSER' to route via CLOSER_ROUTING.
const ROUTES = [
  {
    key: 'route1_new_lead',
    trigger: 'created',
    stage: 'Lead',
    channel: 'newLeads',
    template: 'newLead',
    requiresCloser: false,
  },
  {
    key: 'route2_pending_closer',
    trigger: 'stage',
    stage: 'Pending Closer Contact',
    channel: 'BY_CLOSER',
    template: 'prequalified',
    requiresCloser: true, // missing assignedTo → catch-all warning
  },
  {
    key: 'route3_needs_uw',
    trigger: 'stage',
    stage: 'Needs Underwriting',
    channel: 'underwriter',
    template: 'underwritingRequest',
    requiresCloser: false,
  },
  {
    key: 'route4_make_offer',
    trigger: 'stage',
    // CONFIRM: routes table calls the STAGE "Closer Needs To Make Offer"; the
    // message template titles it "OFFER PROVIDED BY UW!". We treat the table as
    // the trigger stage and the template title as the heading. Verify the real
    // stage name + intent with Marco.
    stage: 'Closer Needs To Make Offer',
    channel: 'BY_CLOSER',
    template: 'offerProvidedByUw',
    requiresCloser: true,
  },
  {
    key: 'route5_offer_made_submitted',
    trigger: 'stage',
    stage: 'Offer Submitted - Waiting to Hear Back', // CONFIRMED stage id=41
    channel: 'closersChat',
    template: 'offerMade',
    requiresCloser: false,
  },
  // 2026-06-16: Marco CONFIRMED "Offer Rejected - Future Follow Up" (id=40) should
  // ALSO notify #closers-chat (distinct "OFFER REJECTED" message). Moved out of
  // NO_NOTIFY_STAGES; this is the second Route-5 stage.
  {
    key: 'route5b_offer_rejected',
    trigger: 'stage',
    stage: 'Offer Rejected - Future Follow Up',
    channel: 'closersChat',
    template: 'offerRejected',
    requiresCloser: false,
  },
  {
    key: 'route6_needs_contract',
    trigger: 'stage',
    stage: 'Needs Contract (Automatically Requested To TC)',
    channel: 'tc',
    template: 'contractRequest',
    requiresCloser: false,
  },
  {
    key: 'route7_contract_sent',
    trigger: 'stage',
    stage: 'Contract Sent',
    // 2026-06-16: Marco CONFIRMED → #closers-chat (was tc-to-dos in the SOW table).
    channel: 'closersChat',
    template: 'contractSent',
    requiresCloser: false,
  },
  {
    key: 'route8_under_contract',
    trigger: 'stage',
    stage: 'Under Contract',
    channel: 'dispo',
    template: 'underContract',
    requiresCloser: false,
  },
  {
    key: 'route9_closed',
    trigger: 'stage',
    stage: 'Closed',
    channel: 'teamWins',
    template: 'closed',
    requiresCloser: false,
  },
];

// Stages that EXPLICITLY get no notification (fall through silently by design).
const NO_NOTIFY_STAGES = [
  'No Contact Made',
  'Cold - Follow Up',
  // 'Offer Rejected - Future Follow Up' — MOVED to a notifying route (Marco 2026-06-16).
  'Hot Leads',
  'Dead (Previous Deal)',
  'Dead/Already Sold',
  'Other Contacts',
  'Title Companies',
  'Lawyers',
  'Buyers List',
  'Buyers List (Real Estate Broker)',
  'Trash',
];

// ── Part B (cold-lead intake form) constants ────────────────────────────────
const INTAKE = {
  HARDCODED_STAGE: 'Lead',          // set in the automation, never on the form
  HARDCODED_TAG: 'Cold Lead - SMS', // tag every form lead so managers can spot it
  // Dropdown values for the form (edit to the agency's real campaigns / roster).
  MARKETS: ['PA', 'NJ', 'IN', 'TN', 'NC', 'Other'],
  PROPERTY_TYPES: ['SFH', 'Condo', 'Multi', 'Land', 'Other'],
  // Placeholders — REPLACE with the agency's real campaign + agent names:
  CAMPAIGNS: ['Spring Absentee PA', 'Probate NJ Q2', 'High-Equity IN', 'Tired Landlord TN', 'Pre-Foreclosure NC'],
  SMS_AGENTS: ['Agent A', 'Agent B', 'Agent C'],
};

// Export for Node (tests) and ignore in n8n (n8n Code nodes embed copies).
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    FUB, CHANNELS, CHANNEL_ENV, chan, CLOSER_ROUTING, CLOSER_FALLBACK_CHANNEL,
    ROUTES, NO_NOTIFY_STAGES, INTAKE,
  };
}
