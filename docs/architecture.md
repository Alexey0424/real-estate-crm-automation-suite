# Architecture

Three event-driven pipelines connect the CRM (Follow Up Boss), the phone system (JustCall), Slack, and a Google Forms intake channel. All three run as Make.com scenarios triggered by webhooks. This document describes the design and the reasoning behind it.

## Pipeline A: CRM stage notifications to Slack

**Trigger.** Two CRM webhooks, `peopleCreated` and `peopleStageUpdated`, both registered programmatically (`shared/fub-scripts/register_webhooks.py`) against one custom Make webhook.

**Why a fetch step exists.** Follow Up Boss webhook payloads are thin: an event name and a list of resource IDs, no person data and no custom fields. The scenario immediately calls `GET /v1/people/{id}?fields=allFields` to load the person, including the Lead Manager custom field the messages need.

**Routing.** A route table (see `shared/lib/config.js`) maps each deal stage to a destination:

- New lead created at stage Lead goes to the team-wide new-leads channel.
- Stages owned by a specific closer (offer work) route to that closer's personal deal channel, resolved by a case-insensitive match on the assigned user's name.
- Underwriting, contract, dispositions, and closed stages each have a fixed channel.
- A person at a closer stage with no assigned closer, or with a closer that matches no channel, falls through to a catch-all channel with a warning instead of being silently dropped.
- Eleven stages are explicitly no-notify by design, so silence on those is intentional rather than a bug.

**Channel identity.** Every Slack post targets an immutable channel ID, never a channel name. Names get renamed and break integrations silently; IDs do not. The channel registry keeps a staging map and a production map, and one patch script flips the scenario between them, so the entire system was testable against staging channels with production untouched.

**Messages.** Slack Block Kit with a plain-text fallback, built by `shared/lib/format.js`. Every template renders to reviewable markdown via `shared/slack-messages/render_examples.js`, which is how message copy was approved before anything went live.

## Pipeline B: cold lead intake form

**Trigger.** A Google Apps Script `onFormSubmit` handler posts the submission to a Make webhook instantly. The alternative, watching the response spreadsheet with a polling trigger, was rejected for cost and latency.

**Processing.** The scenario normalizes the phone number to E.164, checks the CRM for an existing person by exact phone or email, and then writes through the events endpoint so the CRM applies its own dedupe semantics. Stage and tag are constants in the automation, never fields on the form, so the texting agency cannot misfile a lead.

**Lead manager assignment.** Round-robin between the lead managers, implemented in Apps Script with a persisted counter behind a lock so concurrent submissions still alternate correctly.

**No Slack from pipeline B.** The first build posted its own new-lead message. Live testing showed the CRM fires `peopleCreated` for API-created people too, so pipeline A already announces these leads and pipeline B posting as well produced duplicates. The Slack leg was removed; pipeline A is the single notifier. The lesson is written up in the engineering notes.

**Resilience.** The Apps Script keeps a retry queue in script properties: if the webhook call fails, the payload is stored and retried on a timer, and the operator is emailed after repeated failures.

## Pipeline C: call and SMS mirror

**Trigger.** Six JustCall webhook topics (call completed, AI report generated, SMS sent and received, and the sales-dialer variants) point at one Make webhook.

**Design: single-step call logging.** Calls are logged when the AI report event arrives, not when the call completes. The AI event carries the call metadata, duration, agent, and the AI fields in one payload, so one `POST /v1/calls` writes a complete record. The earlier two-step design (log at completion, enrich when the AI report arrives) had a real race: AI events can arrive late and out of order, and "enrich the most recent call" matched the wrong call in production. The trade-off is documented: a call appears one to two minutes after it ends, and a pure ring-with-no-answer that generates no AI report is not logged.

**Contact matching.** The external party's number searches the CRM (`GET /v1/people?phone=`). An existing person gets the call on their timeline; an unknown number creates a person at stage Lead with a source tag first.

**Attribution.** The JustCall agent email maps to a CRM user ID so the call is attributed to the right closer. An unmapped agent degrades gracefully: the call still logs, just without attribution.

**Note format.** The call note carries only what the sales managers asked for: call score, topics, customer sentiment, a transcription link, and the verbatim AI summary with action items. Native JustCall call logging is disabled to avoid double logging; native SMS logging stays on because the CRM rejects a second integration writing text messages.

## The shared logic core

`shared/lib` holds the tables and functions both platform builds follow:

- `config.js` routes, channel registry, closer routing, no-notify stages, intake constants
- `routing.js` `decide()`, the pure function that answers where an event notifies
- `phone.js` E.164 normalization
- `fields.js` extraction of notification fields from a CRM person object
- `format.js` Slack mrkdwn and Block Kit builders
- `test.js` 26 assertions over all of the above

The n8n workflows are generated from this core by `n8n/build-workflows.js`. The Make blueprints are generated by the Python scripts in `make/`, which mirror the same tables. The core is the reviewable, testable statement of the business rules.

## Scenarios as code

The Make scenarios were never built by hand in the GUI:

- `make/build_make_part{A,B,C}.py` generate complete scenario blueprints.
- `make/create_scenario.py` creates or updates scenarios through the Make API while preserving webhook URLs.
- `make/inject_keys.py` injects API credentials from the environment into the live scenario after every update, because a blueprint overwrite wipes inline auth. No secret ever exists in a repo file.
- `make/patch_*.py` are surgical, single-purpose patches applied to the live scenarios as requirements changed. Each fetches the current blueprint, edits the specific modules, and writes back, preserving connections. They double as a change log.
- `make/add_notes.py` posts color-coded documentation notes onto the scenario modules through the API, so the next engineer opening the Make GUI sees the design rationale in place.
- `make/test_*.py` fire controlled webhook payloads at the live scenarios and assert on the resulting Slack posts or CRM records: end-to-end tests against the real integration surface.
