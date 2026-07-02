/**
 * format.js — build the Slack message (mrkdwn text + Block Kit blocks) for each
 * route, verbatim from the SOW §5 templates.
 *
 * Slack formatting rules baked in (research gotchas):
 *  - bold is *single* asterisks (NOT **double**)
 *  - links are <url|text> (NOT [text](url))
 *  - always set a plain-text `text` fallback even when using blocks
 */

// Template registry: heading + ordered [label, fieldKey] rows.
// fieldKey maps into the bag from fields.extractFields().
const TEMPLATES = {
  newLead: {
    heading: 'New Seller Lead :rocket:',
    rows: [
      ['Marketing Campaign', 'source'],
      ['Seller Name', 'sellerName'],
      ['Address', 'address'],
      ['Lead Manager', 'leadManager'],
    ],
  },
  prequalified: {
    heading: ':telephone_receiver: PREQUALIFIED LEAD ASSIGNED TO YOU',
    rows: [
      ['Seller Name', 'sellerName'],
      ['Address', 'address'],
      ['Source', 'source'],
      ['Lead Manager', 'leadManager'],
    ],
  },
  underwritingRequest: {
    heading: 'UNDERWRITING REQUEST',
    rows: [
      ['Seller Name', 'sellerName'],
      ['Closer', 'closer'],
      ['Address', 'address'],
      ['Source', 'source'],
    ],
  },
  offerProvidedByUw: {
    heading: 'OFFER PROVIDED BY UW!',
    rows: [
      ['Seller Name', 'sellerName'],
      ['Closer', 'closer'],
      ['Address', 'address'],
      ['Source', 'source'],
    ],
  },
  offerMade: {
    heading: ':envelope_with_arrow: OFFER MADE',
    rows: [
      ['Closer', 'closer'],
      ['Seller Name', 'sellerName'],
      ['Address', 'address'],
    ],
  },
  offerRejected: {
    heading: 'OFFER REJECTED',
    rows: [
      ['Closer', 'closer'],
      ['Seller Name', 'sellerName'],
      ['Address', 'address'],
    ],
  },
  contractRequest: {
    heading: ':memo: CONTRACT REQUEST',
    rows: [
      ['Seller Name', 'sellerName'],
      ['Closer', 'closer'],
      ['Address', 'address'],
    ],
  },
  contractSent: {
    heading: ':white_check_mark: CONTRACT SENT',
    rows: [
      ['Seller Name', 'sellerName'],
      ['Closer', 'closer'],
      ['Address', 'address'],
    ],
  },
  underContract: {
    heading: 'NEW DEAL UNDER CONTRACT!',
    rows: [
      ['Seller Name', 'sellerName'],
      ['Closer', 'closer'],
      ['Address', 'address'],
      ['Source', 'source'],
    ],
  },
  closed: {
    heading: ':tada: Congrats to the closer!',
    rows: [
      ['Closer', 'closer'],
      ['Property', 'address'],
      ['Source', 'source'],
    ],
  },
};

const FUB_LINK_LABEL = 'Open in FUB';

function fubLinkMrkdwn(url) {
  return url ? `<${url}|${FUB_LINK_LABEL}>` : '_(no FUB link)_';
}

/** The catch-all warning for a closer-routed stage with no Assigned To. */
function buildCatchall(stage, fields) {
  const text =
    `:warning: Lead moved to *${stage}* with no closer assigned\n` +
    `*Seller Name:* ${fields.sellerName || '—'}\n` +
    `*FUB Link:* ${fubLinkMrkdwn(fields.fubLink)}`;
  const blocks = [
    { type: 'section', text: { type: 'mrkdwn', text: `:warning: *Lead moved to ${stage} with no closer assigned*` } },
    { type: 'section', fields: [
      { type: 'mrkdwn', text: `*Seller Name:*\n${fields.sellerName || '—'}` },
      { type: 'mrkdwn', text: `*FUB Link:*\n${fubLinkMrkdwn(fields.fubLink)}` },
    ] },
  ];
  return { text, blocks };
}

/** Build a normal route message. templateKey ∈ keys of TEMPLATES. */
function buildMessage(templateKey, fields) {
  if (templateKey === 'catchall') return buildCatchall(fields.stage, fields);
  const tpl = TEMPLATES[templateKey];
  if (!tpl) throw new Error(`unknown template "${templateKey}"`);

  // mrkdwn text (fallback + simple clients)
  const lines = [`*${tpl.heading}*`];
  for (const [label, key] of tpl.rows) lines.push(`*${label}:* ${fields[key] || '—'}`);
  lines.push(`*FUB Link:* ${fubLinkMrkdwn(fields.fubLink)}`);
  const text = lines.join('\n');

  // Block Kit: heading section + two-column fields + link section
  const fieldBlocks = tpl.rows.map(([label, key]) => ({
    type: 'mrkdwn',
    text: `*${label}:*\n${fields[key] || '—'}`,
  }));
  const blocks = [
    { type: 'section', text: { type: 'mrkdwn', text: `*${tpl.heading}*` } },
    { type: 'section', fields: fieldBlocks },
    { type: 'section', text: { type: 'mrkdwn', text: `*FUB Link:* ${fubLinkMrkdwn(fields.fubLink)}` } },
  ];
  return { text, blocks };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { buildMessage, buildCatchall, TEMPLATES };
}
