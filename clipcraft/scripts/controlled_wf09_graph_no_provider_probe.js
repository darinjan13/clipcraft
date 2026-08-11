const { execFileSync } = require('child_process');
const { createHash } = require('crypto');
const { readFileSync } = require('fs');
const { resolve } = require('path');
const {
  EXPECTED_JOB_ID: inputJobId,
  EXPECTED_LEASE_TOKEN: expectedLeaseToken,
  EXPECTED_RUN_TOKEN: expectedRunToken,
  EXPECTED_STAGE_RUN_ID: expectedStageRunId,
  UNWRAP_CODE: unwrapCode,
  BEGIN_CODE: beginCode,
  RESERVE_CODE: reserveCode,
  HEARTBEAT_CODE: heartbeatCode,
  RENDER_CODE: renderCode,
  BUILD_RESPONSE_CODE: buildResponseCode,
  FINALIZE_CODE: finalizeCode,
} = require('./wf09_gate_a_contract');

const inspect = JSON.parse(execFileSync('docker', ['inspect', 'clipcraft-n8n'], { encoding: 'utf8', timeout: 10000 }))[0];
const apiKeyEntry = inspect.Config.Env.find((value) => value.startsWith('N8N_API_KEY='));
if (!apiKeyEntry) throw new Error('N8N_API_KEY not found in clipcraft-n8n');
const apiKey = apiKeyEntry.slice('N8N_API_KEY='.length);
const headers = { 'X-N8N-API-KEY': apiKey, 'Content-Type': 'application/json' };
const LIVE_WORKFLOW_ID = 'gqX0rJ1gqzHCNDso';
const LIVE_WORKFLOW_NAME = 'Render AI Video';
const fetchTimeoutMs = 10000;
const CREATE_TIMEOUT_MS = 30_000;
const UNKNOWN_CREATE_RECOVERY_ATTEMPTS = 60;
const UNKNOWN_CREATE_RECOVERY_DELAY_MS = 2_000;
const recoveryAttempts = 10;
const recoveryDelayMs = 1000;
const executionPollAttempts = 10;
const executionPollDelayMs = 1000;
const maxListPages = 10;
const WRITABLE_NODE_KEYS = [
  'id', 'name', 'webhookId', 'disabled', 'notesInFlow', 'notes', 'type', 'typeVersion',
  'executeOnce', 'alwaysOutputData', 'retryOnFail', 'maxTries', 'waitBetweenTries',
  'continueOnFail', 'onError', 'position', 'parameters', 'credentials', 'customTelemetryTags',
];
const EXPECTED_HASH_PARAMETERS = {
  action: 'hash',
  binaryData: false,
  type: 'SHA256',
  value: '={{ $json.stageHashInput }}',
  dataPropertyName: 'inputHash',
  encoding: 'hex',
};
const EXPECTED_NODE_TYPES = new Map([
  ['Workflow Trigger', 'n8n-nodes-base.webhook'],
  ['Unwrap Probe Input', 'n8n-nodes-base.code'],
  ['Normalize Stage Context', 'n8n-nodes-base.code'],
  ['Hash Stage Input', 'n8n-nodes-base.crypto'],
  ['Stub Begin Stage', 'n8n-nodes-base.code'],
  ['Merge Stage Context', 'n8n-nodes-base.code'],
  ['Stage Started?', 'n8n-nodes-base.if'],
  ['Stub Reserve External Attempt', 'n8n-nodes-base.code'],
  ['Merge Attempt Context', 'n8n-nodes-base.code'],
  ['Stub Heartbeat Stage Lease', 'n8n-nodes-base.code'],
  ['Merge Heartbeat Context', 'n8n-nodes-base.code'],
  ['Stub Render Output', 'n8n-nodes-base.code'],
  ['Stub Build Response', 'n8n-nodes-base.code'],
  ['Finalize Boundary', 'n8n-nodes-base.code'],
]);
const EXPECTED_CONNECTIONS = JSON.parse('{"Workflow Trigger":{"main":[[{"node":"Unwrap Probe Input","type":"main","index":0}]]},"Unwrap Probe Input":{"main":[[{"node":"Normalize Stage Context","type":"main","index":0}]]},"Normalize Stage Context":{"main":[[{"node":"Hash Stage Input","type":"main","index":0}]]},"Hash Stage Input":{"main":[[{"node":"Stub Begin Stage","type":"main","index":0}]]},"Stub Begin Stage":{"main":[[{"node":"Merge Stage Context","type":"main","index":0}]]},"Merge Stage Context":{"main":[[{"node":"Stage Started?","type":"main","index":0}]]},"Stage Started?":{"main":[[{"node":"Stub Reserve External Attempt","type":"main","index":0}],[]]},"Stub Reserve External Attempt":{"main":[[{"node":"Merge Attempt Context","type":"main","index":0}]]},"Merge Attempt Context":{"main":[[{"node":"Stub Heartbeat Stage Lease","type":"main","index":0}]]},"Stub Heartbeat Stage Lease":{"main":[[{"node":"Merge Heartbeat Context","type":"main","index":0}]]},"Merge Heartbeat Context":{"main":[[{"node":"Stub Render Output","type":"main","index":0}]]},"Stub Render Output":{"main":[[{"node":"Stub Build Response","type":"main","index":0}]]},"Stub Build Response":{"main":[[{"node":"Finalize Boundary","type":"main","index":0}]]}}');
const SAFE_STRUCTURAL_TYPES = new Set(EXPECTED_NODE_TYPES.values());
const RENDERER_NODE_TYPES = new Set(['n8n-nodes-base.executeCommand', '@clipcraft/n8n-nodes-clipcraft.clipCraftVideoExecute']);
const expectedCodePins = new Map([
  ['Normalize Stage Context', 'dc277a72ee32c02be8e619c725b80c91f9cd1657b69b2e5be0e2c24318506f87'],
  ['Merge Stage Context', 'bb4728c321338bdaf1f62b5c5a79146cac72ac7b5408b7f5a2e3a3f462e3cfa3'],
  ['Merge Attempt Context', 'ee9c1a114ede1c4628ef72b989ae1653d599c0deca8b829ac293a2e782d2e3c5'],
  ['Merge Heartbeat Context', '9ca1fbd702f69928b24aa1a4699934d11c3ebbd14932f607b4ce97dfaac905c0'],
  ['Unwrap Probe Input', 'bd5fee3e212df6d062f8eea0f106b0f0a863e8a4305d322ba4ccf5ab961a1eeb'],
  ['Stub Begin Stage', '76f33131e9cacada73aeef5761e8b457f5be2e1e4b4fd7313106914c7ff41e35'],
  ['Stub Reserve External Attempt', '1fab8bcf3f04bca35a677b3873400793929da5622bb7e91b2b0d6bfdb8e24a4e'],
  ['Stub Heartbeat Stage Lease', '5bd497097c339520ad8953073f656782526c89000623638a7a062f38d3494029'],
  ['Stub Render Output', 'f417452351cf7df002e51b25ae6bfcf812b3c88e7ae36a6a2d2f6e3c26da02a3'],
  ['Stub Build Response', 'b7ba557ee145f42365fe097ea8f8e925432f787a3b5cfc6d7c05f5109e1046e7'],
  ['Finalize Boundary', '76651ff9f75b055db8a2246e1175fff57ba5404f05b7cce9aa51e2ef81402eeb'],
]);

async function fetchWithTimeout(url, options = {}, timeoutMs = fetchTimeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const text = await response.text();
    return { response, text };
  } catch (error) {
    if (error.name === 'AbortError') throw new Error(`${options.method || 'GET'} ${url} timed out after ${timeoutMs}ms`);
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function api(url, options = {}, expectedStatuses = null, timeoutMs = fetchTimeoutMs) {
  const { response, text } = await fetchWithTimeout(`http://localhost:5680${url}`, {
    ...options,
    headers: { ...headers, ...(options.headers || {}) },
  }, timeoutMs);
  const accepted = expectedStatuses ? expectedStatuses.includes(response.status) : response.ok;
  if (!accepted) throw new Error(`${options.method || 'GET'} ${url} returned HTTP ${response.status}: ${text}`);
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (error) {
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

function safeGateSummary(report) {
  return {
    gateA: report.gateA,
    finalizationBoundaryReached: report.finalizationBoundaryReached,
    runTokenMatches: report.runTokenMatches,
    inputHashMatches: report.inputHashMatches,
    finalizationCount: report.finalizationCount,
    providerCalls: report.providerCalls,
    rendererInvocations: report.rendererInvocations,
  };
}

function projectWritableNode(node) {
  const projected = {};
  for (const key of WRITABLE_NODE_KEYS) {
    if (Object.prototype.hasOwnProperty.call(node, key) && node[key] !== undefined) projected[key] = node[key];
  }
  return projected;
}

function projectExecutableWorkflow(workflow) {
  return {
    nodes: workflow.nodes.map(projectWritableNode),
    connections: workflow.connections,
    settings: workflow.settings,
    staticData: workflow.staticData ?? null,
  };
}

function assertLiveWorkflowIdentity(live, local) {
  if (live.id !== LIVE_WORKFLOW_ID || live.name !== LIVE_WORKFLOW_NAME || live.active !== true) {
    throw new Error('Live WF09 identity or active state mismatch');
  }
  if (local.name !== LIVE_WORKFLOW_NAME) throw new Error('Local WF09 name mismatch');
  if (stableStringify(projectExecutableWorkflow(live)) !== stableStringify(projectExecutableWorkflow(local))) {
    throw new Error('Live WF09 executable graph differs from the local workflow definition');
  }
}

function sha256(value) {
  return createHash('sha256').update(value, 'utf8').digest('hex');
}

function validateProbeSafety(workflow) {
  if (workflow.nodes.length !== EXPECTED_NODE_TYPES.size) throw new Error('Probe node count does not match the audited graph');
  const actualNames = new Set(workflow.nodes.map((node) => node.name));
  if (actualNames.size !== EXPECTED_NODE_TYPES.size) throw new Error('Probe node names are duplicated or incomplete');
  if (stableStringify(workflow.connections) !== stableStringify(EXPECTED_CONNECTIONS)) {
    throw new Error('Probe connections do not match the audited graph');
  }
  const codeNodes = workflow.nodes.filter((node) => node.type === 'n8n-nodes-base.code');
  if (codeNodes.length !== expectedCodePins.size) throw new Error('Probe Code node set does not match the audited pins');
  const pinnedNames = new Set();
  for (const node of workflow.nodes) {
    if (EXPECTED_NODE_TYPES.get(node.name) !== node.type) throw new Error(`Unexpected probe node or type ${node.name}: ${node.type}`);
    if (node.credentials != null || Object.prototype.hasOwnProperty.call(node, 'credentials')) {
      throw new Error(`Probe node ${node.name} must not contain credentials`);
    }
    if (stableStringify(node).includes('$env')) throw new Error(`Probe node ${node.name} contains an environment expression`);
    if (node.type === 'n8n-nodes-base.code') {
      const jsCode = node.parameters?.jsCode;
      if (typeof jsCode !== 'string') throw new Error(`Probe Code node ${node.name} has no jsCode`);
      const expectedPin = expectedCodePins.get(node.name);
      if (!expectedPin || sha256(jsCode) !== expectedPin) throw new Error(`Probe Code node ${node.name} does not match its audited SHA-256 pin`);
      pinnedNames.add(node.name);
    }
  }
  if (pinnedNames.size !== expectedCodePins.size) throw new Error('Probe Code node names do not match the audited pins');
  const hashNode = workflow.nodes.find((node) => node.name === 'Hash Stage Input');
  if (stableStringify(hashNode.parameters) !== stableStringify(EXPECTED_HASH_PARAMETERS)) {
    throw new Error('Probe Hash Stage Input parameters do not match the approved contract');
  }
  const externalCallCapableNodes = workflow.nodes.filter((node) => !SAFE_STRUCTURAL_TYPES.has(node.type));
  const rendererNodes = workflow.nodes.filter((node) => RENDERER_NODE_TYPES.has(node.type));
  if (externalCallCapableNodes.length !== 0 || rendererNodes.length !== 0) {
    throw new Error('Probe contains an external-call-capable or renderer node');
  }
  return { providerCalls: 0, rendererInvocations: 0 };
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

async function listRunningExecutionsForWorkflowIds(workflowIds) {
  if (workflowIds.size === 0) return [];
  const matches = [];
  let cursor;
  for (let pageNumber = 0; pageNumber < maxListPages; pageNumber += 1) {
    const query = new URLSearchParams({ status: 'running', limit: '100' });
    if (cursor) query.set('cursor', cursor);
    const { data: page } = await api(`/api/v1/executions?${query.toString()}`);
    const executions = Array.isArray(page?.data) ? page.data : [];
    matches.push(...executions.filter((execution) => {
      const workflowId = execution.workflowId ?? execution.workflowData?.id;
      return workflowIds.has(String(workflowId));
    }));
    cursor = page?.nextCursor;
    if (!cursor) return matches;
  }
  throw new Error(`Execution list exceeded ${maxListPages} pages`);
}

async function waitForNoRunningExecutions(workflowIds, phase) {
  let running = [];
  for (let attempt = 1; attempt <= executionPollAttempts; attempt += 1) {
    running = await listRunningExecutionsForWorkflowIds(workflowIds);
    if (running.length === 0) return;
    if (attempt < executionPollAttempts) await new Promise((resolveDelay) => setTimeout(resolveDelay, executionPollDelayMs));
  }
  throw new Error(`${phase}: running executions remain for workflow IDs ${[...workflowIds].join(', ')}`);
}

async function cleanupWorkflowIds(workflowIds, deletedWorkflowIds, cleanupErrors) {
  const pendingIds = [...workflowIds].filter((workflowId) => !deletedWorkflowIds.has(workflowId));
  if (pendingIds.length === 0) return;
  for (const workflowId of pendingIds) {
    try {
      await api(`/api/v1/workflows/${workflowId}/deactivate`, { method: 'POST', body: '{}' });
    } catch (error) {
      cleanupErrors.push(`deactivate ${workflowId}: ${error.message}`);
    }
  }
  try {
    await waitForNoRunningExecutions(workflowIds, 'before deletion');
  } catch (error) {
    cleanupErrors.push(error.message);
    return;
  }
  for (const workflowId of pendingIds) {
    try {
      await api(`/api/v1/workflows/${workflowId}`, { method: 'DELETE' });
      deletedWorkflowIds.add(workflowId);
    } catch (error) {
      cleanupErrors.push(`delete ${workflowId}: ${error.message}`);
    }
  }
  for (const workflowId of deletedWorkflowIds) {
    try {
      const gone = await api(`/api/v1/workflows/${workflowId}`, {}, [404]);
      if (gone.status !== 404) throw new Error(`temporary workflow still exists with HTTP ${gone.status}`);
    } catch (error) {
      cleanupErrors.push(`verify deletion ${workflowId}: ${error.message}`);
    }
  }
  try {
    await waitForNoRunningExecutions(workflowIds, 'after deletion');
  } catch (error) {
    cleanupErrors.push(error.message);
  }
}

async function pollExactNameAbsence(probeName, knownWorkflowIds, deletedWorkflowIds, cleanupErrors, attempts = recoveryAttempts, delayMs = recoveryDelayMs) {
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const matches = await listWorkflowsByExactName(probeName);
      for (const workflow of matches) knownWorkflowIds.add(String(workflow.id));
      await cleanupWorkflowIds(knownWorkflowIds, deletedWorkflowIds, cleanupErrors);
    } catch (error) {
      cleanupErrors.push(`recover workflow by name attempt ${attempt}: ${error.message}`);
    }
    if (attempt < attempts) await new Promise((resolveDelay) => setTimeout(resolveDelay, delayMs));
  }
  try {
    const remaining = await listWorkflowsByExactName(probeName);
    for (const workflow of remaining) knownWorkflowIds.add(String(workflow.id));
    if (remaining.length !== 0) throw new Error(`recovered workflow still exists: ${remaining.map((workflow) => workflow.id).join(', ')}`);
    await waitForNoRunningExecutions(knownWorkflowIds, 'after exact-name stabilization');
  } catch (error) {
    cleanupErrors.push(`verify recovered workflow absence: ${error.message}`);
  }
}

function codeNode(name, id, position, jsCode) {
  return {
    parameters: { jsCode },
    type: 'n8n-nodes-base.code',
    typeVersion: 2,
    position,
    id,
    name,
  };
}

async function main() {
  const uniqueSuffix = `${Date.now()}-${process.pid}`;
  const webhookPath = `phase7-wf09-gate-a-${uniqueSuffix}`;
  const probeName = `Phase 7 WF09 Gate A Probe ${uniqueSuffix}`;
  const localPath = resolve(__dirname, '..', 'workflows', '09-render-video.json');
  const local = JSON.parse(readFileSync(localPath, 'utf8'));
  const { data: live } = await api('/api/v1/workflows/gqX0rJ1gqzHCNDso');
  assertLiveWorkflowIdentity(live, local);
  const liveNodes = new Map(live.nodes.map((node) => [node.name, node]));

  const normalize = liveNodes.get('Normalize Stage Context');
  const hash = liveNodes.get('Hash Stage Input');
  const mergeStage = liveNodes.get('Merge Stage Context');
  const stageStarted = liveNodes.get('Stage Started?');
  const mergeAttempt = liveNodes.get('Merge Attempt Context');
  const mergeHeartbeat = liveNodes.get('Merge Heartbeat Context');
  const workflow = {
    name: probeName,
    nodes: [
      {
        parameters: { path: webhookPath, httpMethod: 'POST', responseMode: 'lastNode', options: {} },
        type: 'n8n-nodes-base.webhook',
        typeVersion: 2.1,
        position: [0, 0],
        id: 'phase7-wf09-probe-trigger-0001',
        name: 'Workflow Trigger',
      },
      codeNode('Unwrap Probe Input', 'phase7-wf09-probe-unwrap-0002', [220, 0], unwrapCode),
      { ...normalize, position: [440, 0], id: 'phase7-wf09-probe-normalize-0003', name: 'Normalize Stage Context' },
      { ...hash, position: [660, 0], id: 'phase7-wf09-probe-hash-0004', name: 'Hash Stage Input' },
      codeNode('Stub Begin Stage', 'phase7-wf09-probe-begin-0005', [880, 0], beginCode),
      { ...mergeStage, position: [1100, 0], id: 'phase7-wf09-probe-merge-stage-0006', name: 'Merge Stage Context' },
      { ...stageStarted, position: [1320, 0], id: 'phase7-wf09-probe-started-0007', name: 'Stage Started?' },
      codeNode('Stub Reserve External Attempt', 'phase7-wf09-probe-reserve-0008', [1540, 0], reserveCode),
      { ...mergeAttempt, position: [1760, 0], id: 'phase7-wf09-probe-merge-attempt-0009', name: 'Merge Attempt Context' },
      codeNode('Stub Heartbeat Stage Lease', 'phase7-wf09-probe-heartbeat-0010', [1980, 0], heartbeatCode),
      { ...mergeHeartbeat, position: [2200, 0], id: 'phase7-wf09-probe-merge-heartbeat-0011', name: 'Merge Heartbeat Context' },
      codeNode('Stub Render Output', 'phase7-wf09-probe-render-0012', [2420, 0], renderCode),
      codeNode('Stub Build Response', 'phase7-wf09-probe-response-0013', [2640, 0], buildResponseCode),
      codeNode('Finalize Boundary', 'phase7-wf09-probe-finalize-0014', [2860, 0], finalizeCode),
    ],
    connections: EXPECTED_CONNECTIONS,
    settings: { executionOrder: 'v1' },
    staticData: null,
  };
  const structuralSafety = validateProbeSafety(workflow);

  let id;
  let report;
  let primaryError;
  const cleanupErrors = [];
  const knownWorkflowIds = new Set();
  const deletedWorkflowIds = new Set();
  try {
    const { data: created } = await api('/api/v1/workflows', { method: 'POST', body: JSON.stringify(workflow) }, null, CREATE_TIMEOUT_MS);
    if (!created?.id) throw new Error('Workflow creation returned no ID');
    id = created.id;
    knownWorkflowIds.add(String(id));
    if (created.active !== false) throw new Error('Temporary workflow was not created inactive');
    await api(`/api/v1/workflows/${id}/activate`, { method: 'POST', body: '{}' });
    const { response, text } = await fetchWithTimeout(`http://localhost:5680/webhook/${webhookPath}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jobId: inputJobId,
        workerId: 'clipcraft-n8n',
        leaseToken: expectedLeaseToken,
        attemptNumber: 1,
        pipelineRevision: 1,
        currentRevision: 1,
      }),
    });
    if (response.status !== 200) throw new Error(`Webhook returned HTTP ${response.status}: ${text}`);
    let result;
    try {
      result = JSON.parse(text);
    } catch (error) {
      throw new Error(`Webhook returned invalid JSON: ${error.message}; body: ${text}`);
    }
    report = {
      ...result,
      finalizationCount: result.finalizationBoundaryReached ? 1 : 0,
      ...structuralSafety,
    };
    if (report.gateA !== true || report.finalizationBoundaryReached !== true || report.runTokenMatches !== true || report.inputHashMatches !== true || report.finalizationCount !== 1 || report.providerCalls !== 0 || report.rendererInvocations !== 0) {
      throw new Error(`Provider-free WF09 probe did not satisfy Gate A: ${JSON.stringify(safeGateSummary(report))}`);
    }
  } catch (error) {
    primaryError = error;
  } finally {
    if (id) {
      await cleanupWorkflowIds(knownWorkflowIds, deletedWorkflowIds, cleanupErrors);
      await pollExactNameAbsence(probeName, knownWorkflowIds, deletedWorkflowIds, cleanupErrors);
    } else {
      await pollExactNameAbsence(probeName, knownWorkflowIds, deletedWorkflowIds, cleanupErrors, UNKNOWN_CREATE_RECOVERY_ATTEMPTS, UNKNOWN_CREATE_RECOVERY_DELAY_MS);
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
