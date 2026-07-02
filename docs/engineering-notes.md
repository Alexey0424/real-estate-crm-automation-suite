# Engineering notes

Decisions, bugs, and platform behavior discovered while building and operating this system. Kept because the reasoning is more reusable than the code.

## Webhooks over polling is a budget decision, not a style preference

Make.com bills per operation. The native Follow Up Boss and Google Sheets triggers are polling triggers: a one-minute watch on a spreadsheet costs about 43,000 operations per month before a single lead arrives. Rebuilding every trigger as an inbound webhook (CRM webhooks registered via API, Apps Script pushing form submissions, JustCall webhooks) cut the cost per event to roughly 3 operations for a notification and 4 to 5 for an intake, which is the difference between fitting a 10,000 operation plan and needing ten times that.

## The null versus empty string bug class

Make evaluates `null = ""` as false. Any guard written as `if(X = ""; fallback; X)` silently misses null, and a webhook payload full of optional fields produces null constantly. This single behavior caused three separate production bugs before being recognized as a class:

1. People with no address rendered "Address: , , " in Slack messages.
2. Calls from lines missing from the agent map were dropped with a 400 instead of logging unattributed.
3. Call notes rendered with broken sections when optional AI fields were absent.

The fix pattern, applied everywhere: `if(ifempty(X; "") = ""; fallback; X)`. When a platform has a semantics gap like this, grep for every guard and fix the class, not the instance.

## Duplicate Slack posts: verify assumptions against the live system

Pipeline B originally posted its own new-lead message, on the assumption that CRM webhooks would not fire for people created through the same API integration. A live test disproved that: `peopleCreated` fires regardless of who created the person, so every form lead was announced twice. The fix was to delete pipeline B's Slack leg entirely and make pipeline A the single notifier. Assumptions about webhook semantics are cheap to verify with one controlled event and expensive to keep wrong.

## The call logging race

First design: log a basic call record when `call.completed` arrives, then enrich "the most recent call for this person" when the AI report event arrives a minute or two later. This is a classic read-modify-write race against an eventually-ordered event stream. A delayed AI event enriched the wrong call and overwrote a real call score in production.

Second design: log nothing at completion, write one complete record per AI event. Each event is self-contained, so ordering no longer matters. Accepted trade-offs, stated to the client explicitly: records appear one to two minutes after the call, and a ring with no answer and no voicemail generates no AI report and therefore no record.

## Own the note, disable the native integration, but only where you write

JustCall ships a native CRM integration with a fixed call note template. The client wanted fields removed from it, which the template does not allow, so this system disables native call logging and writes its own note. Native SMS logging stays enabled because the CRM returns 403 when a second integration posts text messages for the same number. The boundary is explicit: this system owns call notes, the native integration owns texts, and nothing writes the same record type from two places.

## Post to channel IDs, never channel names

Slack channels get renamed by people who have no idea an automation targets them. Every post in this system uses the immutable channel ID. The registry in `shared/lib/config.js` keeps name and ID together so humans can read it, but only the ID is ever sent. A staging map next to the production map, with a one-command switch, made it possible to run the full test matrix against staging channels while production stayed silent.

## Catch-alls beat silent drops

Two places where events could have disappeared were given explicit fallbacks instead:

- A stage-change event matching no route and not on the intentional no-notify list posts to a catch-all channel with the stage name and a warning.
- A closer-stage event with an unmapped or missing closer posts to the lead managers channel flagged as unrouted, rather than being dropped.

In an integration that fires from someone else's system, "we did not receive it" and "we dropped it" must be distinguishable at a glance.

## Integration identity matters

The CRM displays the `X-System` header verbatim as the author of every API-created record. Giving each pipeline its own registered identity (the intake pipeline and the phone sync each have their own) means the sales team can see at a glance where any record came from, and misbehavior can be traced to a pipeline in seconds.

## Test against the integration surface, not the dashboard

Platform dashboards lag and aggregate. Every acceptance test here fires a controlled payload at the real webhook and then asserts on the observable outcome: the Slack message in the staging channel, or the CRM record via the API. The `make/test_*.py` scripts encode those tests so they are repeatable after every patch, which is what made it safe to apply a dozen surgical changes to live scenarios over the engagement.

## Platform limits found and documented rather than fought

- CRM webhook payloads carry no person data: every consumer needs the follow-up GET, so it is one shared, documented step.
- API-logged calls cannot populate the CRM's native transcript and summary tabs; the industry-standard approximation is the recording on the call plus the AI summary in the note, and that was agreed with the client rather than promised around.
- Calls logged via API cannot be deleted via API (only people and notes can), which changes how you design test data. Test people are created and deleted as whole units, cascading their calls.
