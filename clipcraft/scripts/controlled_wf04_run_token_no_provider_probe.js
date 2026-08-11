const { execFileSync } = require('child_process');
const { createHash } = require('crypto');
const { readFileSync } = require('fs');
const { resolve } = require('path');

const inspect = JSON.parse(execFileSync('docker', ['inspect', 'clipcraft-n8n'], { encoding: 'utf8', timeout: 10000 }))[0];
const apiKey = inspect.Config.Env.find((value) => value.startsWith('N8N_API_KEY=')).slice('N8N_API_KEY='.length);
const headers = { 'X-N8N-API-KEY': apiKey, 'Content-Type': 'application/json' };
const expectedRunToken = '33333333-3333-4333-8333-333333333333';
const expectedInputHash = 'd10d537471f2b7711d4b537e073982adb05d8e0c7be176995d1b729b549d42f0';
const fetchTimeoutMs = 10000;
const recoveryAttempts = 5;
const recoveryDelayMs = 500;
const maxListPages = 10;
const unwrapCode = "const input = $json.body ?? $json; return [{json: input}];";
const beginCode = `const input = $json; return [{json: {state: 'STARTED', stage_run_id: '44444444-4444-4444-8444-444444444444', run_token: '${expectedRunToken}', output: null}}];`;
const stopCode = `const input = $json; const runTokenPresent = typeof input.runToken === 'string'; const runTokenMatches = input.runToken === '${expectedRunToken}'; const inputHashMatches = input.inputHash === '${expectedInputHash}'; const stageHashInputAbsent = !Object.prototype.hasOwnProperty.call(input, 'stageHashInput'); const providerCalls = 0; if (!runTokenPresent) throw new Error('RUN_TOKEN_REQUIRED'); if (!runTokenMatches || !inputHashMatches || !stageHashInputAbsent || providerCalls !== 0) throw new Error('PROBE_CONTRACT_FAILED'); return [{json: {probeStopped: true, runTokenPresent, runTokenMatches, inputHash: input.inputHash, inputHashMatches, stageHashInputAbsent, jobId: input.jobId, providerCalls: 0}}];`;
const expectedCodePins = new Map([
  ['Normalize Stage Context', '7c4b326ef15e3efa7750d7639b501e4743fef904f7ef98c368944a8017754186'],
  ['Merge Stage Context', '133a2fff795048ff6db8aef4e93ffb24647c0cb8fc0c79a9072b48bec32544fa'],
  ['Unwrap Probe Input', 'bc9619e56df0ba8eb86dd237401f80f02c353dd6cdcc7cd474ce1b44d74c8272'],
  ['Begin Stage', '4c1d35bc6725a5399d3557be12949f60718c986b66a1ed896379b0d91fe0bb25'],
  ['Generate Script Token Stop', '7041050016cdb774cc61b650b465cfa04613b163cadb5d7fe11ac31ac960cbaa'],
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
  const allowedNodeTypes = new Set(['n8n-nodes-base.webhook', 'n8n-nodes-base.code', 'n8n-nodes-base.crypto']);
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
  const webhookPath = `phase7-wf04-run-token-${Date.now()}`;
  const probeName = `Phase 7 WF04 Run Token Probe ${Date.now()}`;
  const desiredPath = resolve(__dirname, '..', 'workflows', '04-generate-script-and-scenes.json');
  const desired = JSON.parse(readFileSync(desiredPath, 'utf8'));
  const { data: live } = await api('/api/v1/workflows/dWTF2UGXX3R73PDW');
  const normalize = live.nodes.find((node) => node.name === 'Normalize Stage Context');
  const hash = live.nodes.find((node) => node.name === 'Hash Stage Input');
  const merge = live.nodes.find((node) => node.name === 'Merge Stage Context');
  const desiredNormalize = desired.nodes.find((node) => node.name === 'Normalize Stage Context');
  const desiredHash = desired.nodes.find((node) => node.name === 'Hash Stage Input');
  const desiredMerge = desired.nodes.find((node) => node.name === 'Merge Stage Context');
  assertNodeIdentity('Normalize Stage Context', normalize, desiredNormalize);
  assertNodeIdentity('Hash Stage Input', hash, desiredHash);
  assertNodeIdentity('Merge Stage Context', merge, desiredMerge);

  const workflow = {
    name: probeName,
    nodes: [
      {
        parameters: { path: webhookPath, httpMethod: 'POST', responseMode: 'lastNode', options: {} },
        type: 'n8n-nodes-base.webhook',
        typeVersion: 2.1,
        position: [0, 0],
        id: 'phase7-wf04-token-trigger-0001',
        name: 'Workflow Trigger',
      },
      {
        parameters: { jsCode: unwrapCode },
        type: 'n8n-nodes-base.code',
        typeVersion: 2,
        position: [220, 0],
        id: 'phase7-wf04-token-unwrap-0002',
        name: 'Unwrap Probe Input',
      },
      {
        ...normalize,
        position: [440, 0],
        id: 'phase7-wf04-token-normalize-0003',
        name: 'Normalize Stage Context',
      },
      {
        ...hash,
        position: [660, 0],
        id: 'phase7-wf04-token-hash-0004',
        name: 'Hash Stage Input',
      },
      {
        parameters: {
          jsCode: beginCode,
        },
        type: 'n8n-nodes-base.code',
        typeVersion: 2,
        position: [880, 0],
        id: 'phase7-wf04-token-begin-0005',
        name: 'Begin Stage',
      },
      {
        ...merge,
        position: [1100, 0],
        id: 'phase7-wf04-token-merge-0006',
        name: 'Merge Stage Context',
      },
      {
        parameters: {
          jsCode: stopCode,
        },
        type: 'n8n-nodes-base.code',
        typeVersion: 2,
        position: [1320, 0],
        id: 'phase7-wf04-token-stop-0007',
        name: 'Generate Script Token Stop',
      },
    ],
    connections: {
      'Workflow Trigger': { main: [[{ node: 'Unwrap Probe Input', type: 'main', index: 0 }]] },
      'Unwrap Probe Input': { main: [[{ node: 'Normalize Stage Context', type: 'main', index: 0 }]] },
      'Normalize Stage Context': { main: [[{ node: 'Hash Stage Input', type: 'main', index: 0 }]] },
      'Hash Stage Input': { main: [[{ node: 'Begin Stage', type: 'main', index: 0 }]] },
      'Begin Stage': { main: [[{ node: 'Merge Stage Context', type: 'main', index: 0 }]] },
      'Merge Stage Context': { main: [[{ node: 'Generate Script Token Stop', type: 'main', index: 0 }]] },
    },
    settings: { executionOrder: 'v1' },
    staticData: null,
  };
  validateProbeSafety(workflow);

  let id;
  let report;
  let primaryError;
  const cleanupErrors = [];
  try {
    const { data: created } = await api('/api/v1/workflows', { method: 'POST', body: JSON.stringify(workflow) });
    id = created.id;
    await api(`/api/v1/workflows/${id}/activate`, { method: 'POST', body: '{}' });
    const { response, text } = await fetchWithTimeout(`http://localhost:5680/webhook/${webhookPath}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jobId: '11111111-1111-4111-8111-111111111111',
        workerId: 'clipcraft-n8n',
        leaseToken: '22222222-2222-4222-8222-222222222222',
        attemptNumber: 1,
        pipelineRevision: 1,
        currentRevision: 1,
      }),
    });
    if (response.status !== 200) throw new Error(`Webhook returned HTTP ${response.status}: ${text}`);
    let result;
    try { result = JSON.parse(text); } catch (error) {
      throw new Error(`Webhook returned invalid JSON: ${error.message}; body: ${text}`);
    }
    if (result.probeStopped !== true || result.runTokenMatches !== true || result.inputHashMatches !== true || result.stageHashInputAbsent !== true || result.providerCalls !== 0) {
      throw new Error('provider-free probe did not preserve the trusted stage contract');
    }
    report = { workflowId: id, httpStatus: response.status, result };
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
  console.log(JSON.stringify(report));
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
