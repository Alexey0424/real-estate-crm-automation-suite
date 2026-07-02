/**
 * routing.js — decide where (if anywhere) a FUB event should notify.
 *
 * Pure, testable. The n8n Switch/Code nodes and the Make Router filters both
 * mirror this logic. Input is the normalized event; output is a decision the
 * caller turns into a Slack post.
 */
const {
  chan, CLOSER_ROUTING, CLOSER_FALLBACK_CHANNEL,
  ROUTES, NO_NOTIFY_STAGES,
} = require('./config');

const norm = (s) => String(s == null ? '' : s).trim();
const lc = (s) => norm(s).toLowerCase();

/** Resolve a closer's channel from the FUB assignedTo display name. */
function resolveCloserChannel(assignedTo) {
  const a = lc(assignedTo);
  if (!a) return { channelKey: null, isFallback: false, missing: true };
  for (const r of CLOSER_ROUTING) {
    if (a.includes(r.contains)) return { channelKey: r.channelKey, isFallback: false, missing: false };
  }
  // assignedTo is set but matches no known closer → safety net, never drop it.
  return { channelKey: CLOSER_FALLBACK_CHANNEL, isFallback: true, missing: false };
}

function isNoNotify(stage) {
  const s = lc(stage);
  return NO_NOTIFY_STAGES.some((x) => lc(x) === s);
}

function findRoute(triggerType, stage) {
  const s = lc(stage);
  return ROUTES.find((r) => r.trigger === triggerType && lc(r.stage) === s) || null;
}

/**
 * decide(event) → decision
 *   event = { type: 'created'|'stage', stage, assignedTo }
 *   decision = {
 *     action: 'notify' | 'catchall' | 'skip',
 *     routeKey, template, channelKey, channelName,
 *     warnUnmappedCloser (bool), reason
 *   }
 */
function decide(event) {
  const type = event && event.type;
  const stage = norm(event && event.stage);
  const assignedTo = norm(event && event.assignedTo);

  if (type === 'stage' && isNoNotify(stage)) {
    return { action: 'skip', reason: `no-notify stage "${stage}"` };
  }

  const route = findRoute(type, stage);
  if (!route) {
    return { action: 'skip', reason: `no route for trigger=${type} stage="${stage}" (unknown/future stage falls through by design)` };
  }

  // Catch-all: closer-routed stage with no Assigned To → warn lead-managers.
  if (route.requiresCloser && !assignedTo) {
    return {
      action: 'catchall',
      routeKey: route.key,
      template: 'catchall',
      channelKey: 'leadManagers',
      channelName: chan('leadManagers').name,
      reason: `${route.stage} with no closer assigned`,
    };
  }

  let channelKey = route.channel;
  let warnUnmappedCloser = false;
  if (route.channel === 'BY_CLOSER') {
    const c = resolveCloserChannel(assignedTo);
    channelKey = c.channelKey;
    warnUnmappedCloser = c.isFallback;
  }

  return {
    action: 'notify',
    routeKey: route.key,
    template: route.template,
    channelKey,
    channelName: chan(channelKey).name,
    warnUnmappedCloser,
    reason: 'routed',
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { decide, resolveCloserChannel, isNoNotify, findRoute };
}
