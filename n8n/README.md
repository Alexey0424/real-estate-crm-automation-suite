# n8n implementation

Two workflows, both **verified importable** into a real n8n (June 2026, node
typeVersions confirmed against n8n master). The Code-node logic is the SAME code
that passes `shared/lib/test.js` (25 assertions) - the builder concatenates the
tested modules so this can't drift from the spec.

- `workflows/partA-fub-slack.json` - FUB webhook -> GET person -> route -> Slack
- `workflows/partB-form-fub.json` - Sheet row -> normalize -> dedupe -> create/update FUB + note
- `build-workflows.js` - regenerates both from `shared/lib`. Run `node n8n/build-workflows.js` after editing config.

## 1. Run n8n

```bash
cd n8n
printf "N8N_ENCRYPTION_KEY=%s\n" "$(openssl rand -hex 24)" > .env   # gitignored
docker compose up -d            # -> http://localhost:5678  (create the owner account)
```

For **Part A** FUB must reach the webhook over **public HTTPS** - on a laptop put a
Cloudflare Tunnel / ngrok in front and set `WEBHOOK_URL` (and `N8N_HOST`,
`N8N_PROTOCOL=https`) in `n8n/.env` to that public URL, then `docker compose up -d` again.

## 2. Import the workflows

```bash
docker compose exec n8n n8n import:workflow --separate --input=/workflows
```
(or in the UI: ⋮ -> Import from File). They import **inactive** - activate after wiring credentials.

## 3. Create the three credentials (Credentials -> New)

| Credential | Type | Values |
|---|---|---|
| **FUB Basic Auth** | *Basic Auth* (Generic) | User = your FUB **API key**, Password = **blank** |
| **Slack (AHB bot)** | *Slack API* | the `xoxb-…` bot token (scopes `chat:write`, `chat:write.public`) |
| **Google Sheets (AHB)** | *Google Sheets Trigger OAuth2* | OAuth-connect the AHB Google account |

Then open each workflow and pick these credentials on the HTTP/Slack/Sheets nodes
(the JSON references them by name; n8n will prompt if the IDs differ).

## 4. Fill the account-specific values

These are placeholders until you run the inspection scripts:

- **Channel IDs** - run `shared/fub-scripts/fetch_slack_channels.py`, paste the
  IDs into `shared/lib/config.js` (`CHANNELS[*].id`), then re-run
  `node n8n/build-workflows.js` and re-import. (The Code node emits the ID; the
  Slack node posts by ID.)
- **Exact stage names** - run `shared/fub-scripts/inspect_fub.py`, reconcile with
  `docs/architecture.md §4`, update `ROUTES[*].stage` in config, rebuild.
- **`customLeadManager`** - confirm via the same script; fix in config if different.
- **Part B sheet** - set the Google Sheet document ID in the *Form Responses
  Trigger* node (`REPLACE_SHEET_ID`) and confirm the tab name is `Form Responses 1`.

## 5. Register the FUB webhooks (Part A) - WRITE, do with approval

Once the webhook URL exists (n8n shows it on the Webhook node - `…/webhook/fub-events`):
```bash
FUB_API_KEY=... X_SYSTEM=AHB-Automation X_SYSTEM_KEY=... \
TARGET_URL=https://<public-n8n>/webhook/fub-events \
python3 shared/fub-scripts/register_webhooks.py
```
Registers `peopleCreated` + `peopleStageUpdated` to the one URL; the workflow
branches on `event` internally.

## 6. Activate + test

Activate both workflows, then follow `docs/engineering-notes.md` (walk a dummy lead through
every stage, screenshot each Slack message; submit a form twice for the dedupe test).

## Migrating to n8n Cloud later
Export each workflow JSON -> import into the Cloud account -> re-create the 3
credentials -> re-point the FUB webhook to the new `…app.n8n.cloud/webhook/fub-events`
URL -> re-test. Workflow logic travels; credentials + webhook URLs do not.
