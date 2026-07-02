/**
 * push-to-cloud.js — import the two workflows into an n8n Cloud (or any n8n)
 * instance via the public REST API, so I can load them for you instead of you
 * drag-dropping. Reads N8N_CLOUD_URL + N8N_API_KEY from ../.env.txt (gitignored).
 *
 *   N8N_CLOUD_URL=https://<your-subdomain>.app.n8n.cloud
 *   N8N_API_KEY=<from Settings → n8n API → Create API key>
 *
 * Run: `node n8n/push-to-cloud.js`
 * Imports are created INACTIVE (credentials get linked in the UI first, then you
 * activate). The API rejects id/active/tags/meta — we strip them per n8n's schema.
 */
const fs = require('fs');
const path = require('path');

function envVal(key) {
  const v = process.env[key];
  if (v) return v.trim();
  let f = path.join(__dirname, '..', '.env');
  if (!fs.existsSync(f)) f = path.join(__dirname, '..', '.env.txt');
  if (fs.existsSync(f)) {
    for (const line of fs.readFileSync(f, 'utf8').split('\n')) {
      if (line.trim().startsWith(key + '=')) return line.split('=', 2)[1].trim();
    }
  }
  return null;
}

async function main() {
  const base = (envVal('N8N_CLOUD_URL') || '').replace(/\/+$/, '');
  const key = envVal('N8N_API_KEY');
  if (!base || !key) { console.error('Set N8N_CLOUD_URL and N8N_API_KEY in .env.txt'); process.exit(1); }

  const files = ['partA-fub-slack.json', 'partB-form-fub.json'];
  for (const file of files) {
    const wf = JSON.parse(fs.readFileSync(path.join(__dirname, 'workflows', file), 'utf8'));
    // API accepts only name/nodes/connections/settings (settings required, may be {}).
    const body = { name: wf.name, nodes: wf.nodes, connections: wf.connections, settings: wf.settings || {} };
    const res = await fetch(`${base}/api/v1/workflows`, {
      method: 'POST',
      headers: { 'X-N8N-API-KEY': key, 'Content-Type': 'application/json', accept: 'application/json' },
      body: JSON.stringify(body),
    });
    const txt = await res.text();
    if (res.ok) {
      const j = JSON.parse(txt);
      console.log(`✓ ${file} → imported as id=${j.id} ("${j.name}")`);
    } else {
      console.error(`✗ ${file} → HTTP ${res.status}: ${txt.slice(0, 400)}`);
    }
  }
  console.log('\nNext: link the FUB/Slack/Google credentials on the nodes, then activate.');
}
main().catch((e) => { console.error(e); process.exit(1); });
