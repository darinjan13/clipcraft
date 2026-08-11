const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const WORKFLOW_ENTRY = { file: '09-render-video.json', id: 'gqX0rJ1gqzHCNDso', name: 'Render AI Video', prefix: 'wf09' };
const workflowsDir = path.resolve(__dirname, '..', 'workflows');
const backupDir = path.resolve(__dirname, '..', 'backups', 'phase-7-cutover');
const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
const WRITABLE_NODE_KEYS = [
  'id', 'name', 'webhookId', 'disabled', 'notesInFlow', 'notes', 'type', 'typeVersion',
  'executeOnce', 'alwaysOutputData', 'retryOnFail', 'maxTries', 'waitBetweenTries',
  'continueOnFail', 'onError', 'position', 'parameters', 'credentials', 'customTelemetryTags',
];
const WRITABLE_SETTING_KEYS = [
  'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution',
  'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone',
  'executionOrder', 'callerPolicy', 'callerIds', 'timeSavedPerExecution',
];
const STABILIZATION_ATTEMPTS = 6;
const STABILIZATION_DELAY_MS = 500;

const inspect = JSON.parse(execFileSync('docker', ['inspect', 'clipcraft-n8n'], {
  encoding: 'utf8',
  timeout: 10000,
}))[0];
const apiKeyEntry = inspect.Config.Env.find((v) => v.startsWith('N8N_API_KEY='));
if (!apiKeyEntry) throw new Error('n8n API credentials not configured');
const apiKey = apiKeyEntry.slice('N8N_API_KEY='.length);

async function main() {
  // 1. Backup current live WF09
  const liveBeforeBackup = await api(`/api/v1/workflows/${WORKFLOW_ENTRY.id}`);
  if (liveBeforeBackup.id !== WORKFLOW_ENTRY.id || liveBeforeBackup.name !== WORKFLOW_ENTRY.name || liveBeforeBackup.active !== true) {
    throw new Error('Live WF09 identity/active mismatch');
  }
  const backupPath = path.join(backupDir, `${WORKFLOW_ENTRY.prefix}-item-lineage-1q-${stamp}.json`);
  fs.mkdirSync(backupDir, { recursive: true });
  if (fs.existsSync(backupPath)) throw new Error('Backup path already exists');
  const backupDescriptor = fs.openSync(backupPath, 'wx', 0o600);
  try { fs.writeFileSync(backupDescriptor, JSON.stringify(liveBeforeBackup, null, 2) + '\n', 'utf8'); }
  finally { fs.closeSync(backupDescriptor); }
  console.log(JSON.stringify({ backedUp: backupPath }));

  // 2. Load local desired WF09
  const desired = JSON.parse(fs.readFileSync(path.join(workflowsDir, WORKFLOW_ENTRY.file), 'utf8'));
  if (stableStringify(desired.name) !== stableStringify(WORKFLOW_ENTRY.name)) throw new Error('Local WF09 name mismatch');

  if (stableStringify(proactivePayload(liveBeforeBackup)) === stableStringify(proactivePayload(desired))) {
    console.log(JSON.stringify({ skipped: true, reason: 'no mutation needed', versionId: liveBeforeBackup.versionId }));
    return;
  }

  // 3. Drift fence: re-read live to confirm no concurrent change
  const liveBeforePut = await api(`/api/v1/workflows/${WORKFLOW_ENTRY.id}`);
  deepEqual(liveBeforePut, liveBeforeBackup, 'drift fence');

  // 4. PUT
  const payload = buildPayload(desired);
  try {
    await api(`/api/v1/workflows/${WORKFLOW_ENTRY.id}`, { method: 'PUT', body: JSON.stringify(payload) });
  } catch (error) {
    throw new Error(`Workflow PUT failed: ${error.message}; backup preserved at ${backupPath}`);
  }

  // 5. Verify
  let after = await api(`/api/v1/workflows/${WORKFLOW_ENTRY.id}`);
  after = await reconcileActiveState(liveBeforeBackup.active, after);

  // Verify Stage Started? schema
  const ss = after.nodes.find(n => n.name === 'Stage Started?');
  const actualOp = ss?.parameters?.conditions?.conditions?.[0]?.operator?.operation;
  const actualComb = ss?.parameters?.conditions?.combinator;
  const actualOpts = stableStringify(ss?.parameters?.conditions?.options || {});
  if (actualOp !== 'equals' || actualComb !== 'and' || actualOpts !== stableStringify({ caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 1 })) {
    throw new Error(`Stage Started? schema not applied: op=${actualOp} comb=${actualComb} opts=${actualOpts}`);
  }

  console.log(JSON.stringify({
    id: after.id,
    name: after.name,
    nodes: after.nodes.length,
    versionId: after.versionId,
    active: after.active,
    imported: true,
  }));
}

function proactivePayload(target) {
  return { nodes: target.nodes.map(projectWritableNode), connections: target.connections, settings: target.settings, staticData: target.staticData ?? null };
}

function buildPayload(desired) {
  return {
    name: WORKFLOW_ENTRY.name,
    nodes: desired.nodes.map(projectWritableNode),
    connections: desired.connections,
    settings: projectWritableSettings(desired.settings || {}),
    staticData: null,
  };
}

function projectWritableNode(node) {
  const projected = {};
  for (const key of WRITABLE_NODE_KEYS) { if (Object.prototype.hasOwnProperty.call(node, key) && node[key] !== undefined) projected[key] = node[key]; }
  return projected;
}

function projectWritableSettings(settings) {
  const projected = {};
  for (const key of WRITABLE_SETTING_KEYS) { if (Object.prototype.hasOwnProperty.call(settings, key) && settings[key] !== undefined) projected[key] = settings[key]; }
  return projected;
}

async function reconcileActiveState(expectedActive, current) {
  if (current.active === expectedActive) return current;
  const action = expectedActive ? 'activate' : 'deactivate';
  const endpoint = expectedActive ? `/api/v1/workflows/${WORKFLOW_ENTRY.id}/activate` : `/api/v1/workflows/${WORKFLOW_ENTRY.id}/deactivate`;
  try { await api(endpoint, { method: 'POST', body: '{}' }); } catch (_) { /* continue */ }
  current = await api(`/api/v1/workflows/${WORKFLOW_ENTRY.id}`);
  if (current.active !== expectedActive) throw new Error(`${action} state mismatch`);
  return current;
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${stableStringify(value[k])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function deepEqual(a, b, label) {
  if (stableStringify(a) !== stableStringify(b)) throw new Error(`${label || 'mismatch'}`);
}

async function api(url, options = {}) {
  const response = await fetch(`http://localhost:5680${url}`, {
    ...options,
    headers: { 'X-N8N-API-KEY': apiKey, ...(options.body ? { 'Content-Type': 'application/json' } : {}) },
    signal: AbortSignal.timeout(10000),
  });
  const text = await response.text();
  if (!response.ok) {
    let detail = '';
    try { const p = JSON.parse(text); if (typeof p.message === 'string') detail = `: ${p.message.slice(0, 300)}`; } catch (_) {}
    throw new Error(`${options.method || 'GET'} ${url} HTTP ${response.status}${detail}`);
  }
  return text ? JSON.parse(text) : null;
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});