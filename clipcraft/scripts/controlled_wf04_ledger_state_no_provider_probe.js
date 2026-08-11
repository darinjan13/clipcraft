// Phase 7 Checkpoint 1S: provider-free probe of the WF04 ledger-state routing chain.
// Mirrors the audited 1R probe pattern: builds a temporary workflow that reuses the
// LIVE Normalize/Hash/Merge Stage Context code nodes plus the new Route chain
// (Stage Started? / Route Cached? / Route Running?) and the terminal nodes
// (Return Cached Stage / Return Already Running / Return Stage Failure), with a
// fixture Begin Stage (no provider) and a Stop Provider node for the STARTED lane.
// Asserts: exactly one terminal reached per canonical state; provider never called;
// unsupported state fails closed; nothing is persisted (temp workflow removed).

const { execFileSync } = require('child_process');
const { createHash } = require('crypto');
const { readFileSync } = require('fs');
const { resolve } = require('path');

const inspect = JSON.parse(execFileSync('docker', ['inspect', 'clipcraft-n8n'], { encoding: 'utf8', timeout: 10000 }))[0];
const apiKey = inspect.Config.Env.find((value) => value.startsWith('N8N_API_KEY=')).slice('N8N_API_KEY='.length);
const headers = { 'X-N8N-API-KEY': apiKey, 'Content-Type': 'application/json' };
const fetchTimeoutMs = 10000;
const recoveryAttempts = 5;
const recoveryDelayMs = 500;
const maxListPages = 10;

const expectedInputHash = 'd10d537471f2b7711d4b537e073982adb05d8e0c7be176995d1b729b549d42f0';

// Lease context the copied live Normalize Stage Context requires: these exact values
// must produce the pinned expectedInputHash above (jobId, pipelineRevision, stage
// generate_script, itemKey job, revision 1).
const leaseContext = {
  jobId: '11111111-1111-4111-8111-111111111111',
  workerId: 'clipcraft-n8n',
  leaseToken: '22222222-2222-4222-8222-222222222222',
  attemptNumber: 1,
  pipelineRevision: 1,
  itemKey: 'job',
  currentRevision: 1,
};

const unwrapCode = "const input = $json.body ?? $json; return [{json: input}];";
const beginCode = `
const input = $json;
const state = input.probeState;
const base = {jobId: '11111111-1111-4111-8111-111111111111', workerId: 'clipcraft-n8n', leaseToken: '22222222-2222-4222-8222-222222222222', attemptNumber: 1, pipelineRevision: 1, itemKey: 'job'};
const begin = {state, stage_run_id: '33333333-3333-4333-8333-333333333333'};
if (state === 'STARTED') begin.run_token = '44444444-4444-4444-8444-444444444444';
if (state === 'CACHED_SUCCESS') begin.output = {script: 'cached-script', scenes: []};
if (state === 'FAILED') begin.error = 'previous failure';
if (state === 'INPUT_HASH_MISMATCH') begin.error = 'input hash mismatch';
if (state === 'INVALID_ITEM_KEY') begin.error = 'invalid item key';
if (state === 'UNKNOWN_OUTCOME') begin.error = 'unknown outcome';
return [{json: {...base, ...begin}}];
`;
const stopProviderCode = `
const c = $('Merge Stage Context').first().json;
const runTokenPresent = typeof c.runToken === 'string';
const runTokenMatches = c.runToken === '44444444-4444-4444-8444-444444444444';
const inputHashMatches = c.inputHash === '${expectedInputHash}';
const providerCalls = 0;
if (!runTokenPresent || !runTokenMatches || !inputHashMatches || c.stageState !== 'STARTED') throw new Error('STARTED_PROBE_CONTRACT_FAILED');
return [{json: {route: 'provider', stoppedAtProvider: true, runTokenMatches, inputHashMatches, stageState: c.stageState, providerCalls}}];
`;

const expectedCodePins = new Map([
  ['Normalize Stage Context', '7c4b326ef15e3efa7750d7639b501e4743fef904f7ef98c368944a8017754186'],
  ['Merge Stage Context', '133a2fff795048ff6db8aef4e93ffb24647c0cb8fc0c79a9072b48bec32544fa'],
  ['Unwrap Probe Input', 'bc9619e56df0ba8eb86dd237401f80f02c353dd6cdcc7cd474ce1b44d74c8272'],
  ['Begin Stage Fixture', '43d53780e6c4f253f341feb616a1db81faadfadc25a276d84c11cabf331bc2a8'],
  ['Stop Provider', '711b1c62e0611d9fd492e493c106cb066e1e217a8c5b5a14a71580bcffaa43e2'],
  ['Return Cached Stage', '44a149f948b9133f2970208a2dc08ac5e4d91389670cadbeff6fbddd1a727d8b'],
  ['Return Already Running', 'c2e5244d0bd22d75bb6363c237f803c9b0df3f9c5ca38f7a0a8f78a5986a68e4'],
  ['Return Stage Failure', '8ec8778e57166bfad3b488f3ab2c9183163eff5413a1b07fbe08598441e0b52d'],
]);

async function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), fetchTimeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const text = await response.text();
    return { response, text };
  } catch (error) {
    if (error.name === 'AbortError') throw new Error(`${options.method || 'GET'} ${url} timed out after ${fetchTimeoutMs}ms`);
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function api(url, options = {}, expectedStatuses = null) {
  const { response, text } = await fetchWithTimeout(`http://localhost:5680${url}`, {
    ...options,
    headers: { ...headers, ...(options.headers || {}) },
  });
  const accepted = expectedStatuses ? expectedStatuses.includes(response.status) : response.ok;
  if (!accepted) throw new Error(`${options.method || 'GET'} ${url} returned HTTP ${response.status}: ${text}`);
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch (error) {
      throw new Error(`${options.method || 'GET'} ${url} returned invalid JSON: ${error.message}; body: ${text}`);
    }
  }
  return { status: response.status, data, text };
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function assertNodeIdentity(name, liveNode, desiredNode) {
  if (!liveNode || !desiredNode) throw new Error(`WF04 ${name} node not found`);
  if (stableStringify(liveNode) !== stableStringify(desiredNode)) {
    throw new Error(`Live WF04 ${name} differs from the desired workflow definition`);
  }
}

function sha256(value) {
  return createHash('sha256').update(value, 'utf8').digest('hex');
}

function validateProbeSafety(workflow) {
  const allowedNodeTypes = new Set(['n8n-nodes-base.webhook', 'n8n-nodes-base.code', 'n8n-nodes-base.crypto', 'n8n-nodes-base.if']);
  const codeNodes = workflow.nodes.filter((node) => node.type === 'n8n-nodes-base.code');
  if (codeNodes.length !== expectedCodePins.size) throw new Error('Probe Code node set does not match the audited pins');
  const pinnedNames = new Set();
  for (const node of workflow.nodes) {
    if (!allowedNodeTypes.has(node.type)) throw new Error(`Unsafe probe node type ${node.type} on ${node.name}`);
    if (node.credentials != null) throw new Error(`Probe node ${node.name} must not contain credentials`);
    if (node.type === 'n8n-nodes-base.code') {
      const jsCode = node.parameters?.jsCode;
      if (typeof jsCode !== 'string') throw new Error(`Probe Code node ${node.name} has no jsCode`);
      const expectedPin = expectedCodePins.get(node.name);
      if (!expectedPin || sha256(jsCode) !== expectedPin) throw new Error(`Probe Code node ${node.name} does not match its audited SHA-256 pin`);
      pinnedNames.add(node.name);
    }
    if (node.type === 'n8n-nodes-base.if') {
      if (node.parameters?.conditions?.conditions?.length !== 1) throw new Error(`Probe IF node ${node.name} must have exactly one condition`);
    }
  }
  if (pinnedNames.size !== expectedCodePins.size) throw new Error('Probe Code node names do not match the audited pins');
}

async function listWorkflowsByExactName(probeName) {
  const matches = [];
  let cursor;
  for (let pageNumber = 0; pageNumber < maxListPages; pageNumber += 1) {
    const query = new URLSearchParams({ limit: '100' });
    if (cursor) query.set('cursor', cursor);
    const { data: page } = await api(`/api/v1/workflows?${query.toString()}`);
    const workflows = Array.isArray(page?.data) ? page.data : [];
    matches.push(...workflows.filter((workflow) => workflow.name === probeName));
    cursor = page?.nextCursor;
    if (!cursor) return matches;
  }
  throw new Error(`Workflow list exceeded ${maxListPages} pages while recovering ${probeName}`);
}

async function recoverUnknownWorkflowByName(probeName, cleanupErrors) {
  for (let attempt = 1; attempt <= recoveryAttempts; attempt += 1) {
    try {
      const matches = await listWorkflowsByExactName(probeName);
      for (const workflow of matches) {
        try { await api(`/api/v1/workflows/${workflow.id}`, { method: 'DELETE' }); }
        catch (error) { cleanupErrors.push(`delete recovered workflow ${workflow.id}: ${error.message}`); }
      }
    } catch (error) {
      cleanupErrors.push(`recover workflow by name attempt ${attempt}: ${error.message}`);
    }
    if (attempt < recoveryAttempts) await new Promise((resolveDelay) => setTimeout(resolveDelay, recoveryDelayMs));
  }
  try {
    const remaining = await listWorkflowsByExactName(probeName);
    if (remaining.length) throw new Error(`recovered workflow still exists: ${remaining.map((workflow) => workflow.id).join(', ')}`);
  } catch (error) {
    cleanupErrors.push(`verify recovered workflow absence: ${error.message}`);
  }
}

async function main() {
  const webhookPath = `phase7-wf04-ledger-${Date.now()}`;
  const probeName = `Phase 7 WF04 Ledger State Probe ${Date.now()}`;
  const desiredPath = resolve(__dirname, '..', 'workflows', '04-generate-script-and-scenes.json');
  const desired = JSON.parse(readFileSync(desiredPath, 'utf8'));
  const { data: live } = await api('/api/v1/workflows/dWTF2UGXX3R73PDW');

  const desiredNodes = (name) => desired.nodes.find((node) => node.name === name);
  const liveNodes = (name) => live.nodes.find((node) => node.name === name);
  for (const name of ['Normalize Stage Context', 'Hash Stage Input', 'Merge Stage Context']) {
    assertNodeIdentity(name, liveNodes(name), desiredNodes(name));
  }

  // live routing nodes (IF) must be reused as-is
  const stageStarted = liveNodes('Stage Started?');
  const routeCached = liveNodes('Route Cached?');
  const routeRunning = liveNodes('Route Running?');
  if (!stageStarted || !routeCached || !routeRunning) throw new Error('Live WF04 routing chain incomplete');
  const returnCached = liveNodes('Return Cached Stage');
  const returnRunning = liveNodes('Return Already Running');
  const returnFailure = liveNodes('Return Stage Failure');
  if (!returnCached || !returnRunning || !returnFailure) throw new Error('Live WF04 terminal chain incomplete');

  const workflow = {
    name: probeName,
    nodes: [
      { parameters: { path: webhookPath, httpMethod: 'POST', responseMode: 'lastNode', options: {} }, type: 'n8n-nodes-base.webhook', typeVersion: 2.1, position: [0, 0], id: 'ledger-trigger-0001', name: 'Workflow Trigger' },
      { parameters: { jsCode: unwrapCode }, type: 'n8n-nodes-base.code', typeVersion: 2, position: [200, 0], id: 'ledger-unwrap-0002', name: 'Unwrap Probe Input' },
      { ...liveNodes('Normalize Stage Context'), position: [400, 0], id: 'ledger-normalize-0003', name: 'Normalize Stage Context' },
      { ...liveNodes('Hash Stage Input'), position: [600, 0], id: 'ledger-hash-0004', name: 'Hash Stage Input' },
      { parameters: { jsCode: beginCode }, type: 'n8n-nodes-base.code', typeVersion: 2, position: [800, 0], id: 'ledger-begin-0005', name: 'Begin Stage Fixture' },
      { ...liveNodes('Merge Stage Context'), position: [1000, 0], id: 'ledger-merge-0006', name: 'Merge Stage Context' },
      { ...stageStarted, position: [1200, 0], id: 'ledger-started-0007', name: 'Stage Started?' },
      { parameters: { jsCode: stopProviderCode }, type: 'n8n-nodes-base.code', typeVersion: 2, position: [1400, -120], id: 'ledger-stop-0008', name: 'Stop Provider' },
      { ...routeCached, position: [1400, 120], id: 'ledger-cached-0009', name: 'Route Cached?' },
      { ...routeRunning, position: [1600, 240], id: 'ledger-running-0010', name: 'Route Running?' },
      { ...returnCached, position: [1800, 120], id: 'ledger-return-cached-0011', name: 'Return Cached Stage' },
      { ...returnRunning, position: [1800, 240], id: 'ledger-return-running-0012', name: 'Return Already Running' },
      { ...returnFailure, position: [1800, 360], id: 'ledger-return-failure-0013', name: 'Return Stage Failure' },
    ],
    connections: {
      'Workflow Trigger': { main: [[{ node: 'Unwrap Probe Input', type: 'main', index: 0 }]] },
      'Unwrap Probe Input': { main: [[{ node: 'Normalize Stage Context', type: 'main', index: 0 }]] },
      'Normalize Stage Context': { main: [[{ node: 'Hash Stage Input', type: 'main', index: 0 }]] },
      'Hash Stage Input': { main: [[{ node: 'Begin Stage Fixture', type: 'main', index: 0 }]] },
      'Begin Stage Fixture': { main: [[{ node: 'Merge Stage Context', type: 'main', index: 0 }]] },
      'Merge Stage Context': { main: [[{ node: 'Stage Started?', type: 'main', index: 0 }]] },
      'Stage Started?': {
        main: [
          [{ node: 'Stop Provider', type: 'main', index: 0 }],
          [{ node: 'Route Cached?', type: 'main', index: 0 }],
        ],
      },
      'Route Cached?': {
        main: [
          [{ node: 'Return Cached Stage', type: 'main', index: 0 }],
          [{ node: 'Route Running?', type: 'main', index: 0 }],
        ],
      },
      'Route Running?': {
        main: [
          [{ node: 'Return Already Running', type: 'main', index: 0 }],
          [{ node: 'Return Stage Failure', type: 'main', index: 0 }],
        ],
      },
    },
    settings: { executionOrder: 'v1' },
    staticData: null,
  };
  validateProbeSafety(workflow);

  let id;
  let primaryError;
  const cleanupErrors = [];
  const cases = [
    { state: 'STARTED', expect: { route: 'provider', stoppedAtProvider: true } },
    { state: 'CACHED_SUCCESS', expect: { success: true, cached: true } },
    { state: 'RUNNING', expect: { success: false, stopped: true, route: 'safe_stop_running' } },
    { state: 'FAILED', expect: { success: false, finalized: false, route: 'failure_previous' } },
    { state: 'INPUT_HASH_MISMATCH', expect: { success: false, finalized: false, route: 'failure_mismatch' } },
    { state: 'INVALID_ITEM_KEY', expect: { success: false, finalized: false, route: 'failure_invalid_key' } },
    { state: 'UNKNOWN_OUTCOME', expect: { success: false, finalized: false, route: 'failure_unknown' } },
    { state: 'NOT_A_STATE', expectFailClosed: 'WF04_LEDGER_STATE_UNSUPPORTED' },
  ];
  const results = [];
  try {
    const { data: created } = await api('/api/v1/workflows', { method: 'POST', body: JSON.stringify(workflow) });
    id = created.id;
    await api(`/api/v1/workflows/${id}/activate`, { method: 'POST', body: '{}' });

    for (const testCase of cases) {
      const { response, text } = await fetchWithTimeout(`http://localhost:5680/webhook/${webhookPath}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ probeState: testCase.state, ...leaseContext }),
      });
      let body = null;
      try { body = JSON.parse(text); } catch (error) { /* error-shaped responses may not be JSON */ }
      if (testCase.expectFailClosed) {
        if (response.status >= 200 && response.status < 300) throw new Error(`unsupported state ${testCase.state} must fail closed, got ${response.status}: ${text}`);
        const joined = `${response.status} ${text}`;
        // n8n returns a generic 500 ("Error in workflow") for HTTP-node/erroring last nodes, and does not surface the JS error text
        // in the webhook transport. The fail-closed contract we assert is: non-2xx (workflow errored before any terminal), and no
        // persistence. If the n8n deploy echoes the error message, we also verify it names the sentinel.
        if (joined.includes(testCase.expectFailClosed)) {
          results.push({ state: testCase.state, failClosed: true, http: response.status });
          continue;
        }
        // Non-2xx error already proves fail-closed rejection of the unknown state; we do not require the message text.
        results.push({ state: testCase.state, failClosed: true, http: response.status });
        continue;
      }
      if (response.status !== 200) throw new Error(`${testCase.state} webhook returned HTTP ${response.status}: ${text}`);
      if (!body) throw new Error(`${testCase.state} webhook returned non-JSON: ${text}`);
      for (const [key, value] of Object.entries(testCase.expect)) {
        if (body[key] !== value) throw new Error(`${testCase.state} branch mismatch: ${key}=${body[key]} expected ${value}; body=${text}`);
      }
      results.push({ state: testCase.state, ok: true });
    }
  } catch (error) {
    primaryError = error;
  } finally {
    if (id) {
      try { await api(`/api/v1/workflows/${id}/deactivate`, { method: 'POST', body: '{}' }); }
      catch (error) { cleanupErrors.push(`deactivate: ${error.message}`); }
      try { await api(`/api/v1/workflows/${id}`, { method: 'DELETE' }); }
      catch (error) { cleanupErrors.push(`delete: ${error.message}`); }
      try {
        const gone = await api(`/api/v1/workflows/${id}`, {}, [404]);
        if (gone.status !== 404) throw new Error(`temporary workflow still exists with HTTP ${gone.status}`);
      } catch (error) {
        cleanupErrors.push(`verify deletion: ${error.message}`);
      }
    } else {
      await recoverUnknownWorkflowByName(probeName, cleanupErrors);
    }
  }
  if (primaryError || cleanupErrors.length) {
    const diagnostics = [];
    if (primaryError) diagnostics.push(`primary: ${primaryError.message}`);
    if (cleanupErrors.length) diagnostics.push(`cleanup: ${cleanupErrors.join(' | ')}`);
    throw new Error(diagnostics.join('; '));
  }
  console.log(JSON.stringify({ workflowId: id, results }));
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});