const { spawnSync } = require('child_process');
const { createHash, randomUUID } = require('crypto');
const { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } = require('fs');
const { tmpdir } = require('os');
const { join, resolve } = require('path');
const {
  EXPECTED_JOB_ID,
  EXPECTED_LEASE_TOKEN,
  EXPECTED_RUN_TOKEN,
  BEGIN_CODE,
  RESERVE_CODE,
  HEARTBEAT_CODE,
  RENDER_CODE,
  BUILD_RESPONSE_CODE,
  FINALIZE_CODE,
} = require('./wf09_gate_a_contract');

const IMAGE = 'clipcraft-n8n-debug:2.29.7-clipcraft-0.1.0';
const WORKFLOW_ID = 'wf09-gate-a-offline-runtime';
const DOCKER_TIMEOUT_MS = 90_000;
const CLEANUP_TIMEOUT_MS = 10_000;
const EXPECTED_NODE_TYPES = JSON.parse('{"Manual Trigger":"n8n-nodes-base.manualTrigger","Fixed Safe Input":"n8n-nodes-base.code","Normalize Stage Context":"n8n-nodes-base.code","Hash Stage Input":"n8n-nodes-base.crypto","Stub Begin Stage":"n8n-nodes-base.code","Merge Stage Context":"n8n-nodes-base.code","Stage Started?":"n8n-nodes-base.if","Stub Reserve External Attempt":"n8n-nodes-base.code","Merge Attempt Context":"n8n-nodes-base.code","Stub Heartbeat Stage Lease":"n8n-nodes-base.code","Merge Heartbeat Context":"n8n-nodes-base.code","Stub Render Output":"n8n-nodes-base.code","Stub Build Response":"n8n-nodes-base.code","Finalize Boundary":"n8n-nodes-base.code"}');
const EXPECTED_CONNECTIONS = JSON.parse('{"Manual Trigger":{"main":[[{"node":"Fixed Safe Input","type":"main","index":0}]]},"Fixed Safe Input":{"main":[[{"node":"Normalize Stage Context","type":"main","index":0}]]},"Normalize Stage Context":{"main":[[{"node":"Hash Stage Input","type":"main","index":0}]]},"Hash Stage Input":{"main":[[{"node":"Stub Begin Stage","type":"main","index":0}]]},"Stub Begin Stage":{"main":[[{"node":"Merge Stage Context","type":"main","index":0}]]},"Merge Stage Context":{"main":[[{"node":"Stage Started?","type":"main","index":0}]]},"Stage Started?":{"main":[[{"node":"Stub Reserve External Attempt","type":"main","index":0}],[]]},"Stub Reserve External Attempt":{"main":[[{"node":"Merge Attempt Context","type":"main","index":0}]]},"Merge Attempt Context":{"main":[[{"node":"Stub Heartbeat Stage Lease","type":"main","index":0}]]},"Stub Heartbeat Stage Lease":{"main":[[{"node":"Merge Heartbeat Context","type":"main","index":0}]]},"Merge Heartbeat Context":{"main":[[{"node":"Stub Render Output","type":"main","index":0}]]},"Stub Render Output":{"main":[[{"node":"Stub Build Response","type":"main","index":0}]]},"Stub Build Response":{"main":[[{"node":"Finalize Boundary","type":"main","index":0}]]}}');
const EXPECTED_NODE_NAMES = Object.keys(EXPECTED_NODE_TYPES);
const EXPECTED_OUTPUT_COUNTS = Object.fromEntries(EXPECTED_NODE_NAMES.map((name) => [
  name,
  name === 'Stage Started?' ? [1, 0] : [1],
]));
const allowedTypes = new Set(Object.values(EXPECTED_NODE_TYPES));

const fixedInputCode = `return [{json: {jobId: '${EXPECTED_JOB_ID}', workerId: 'offline-worker', leaseToken: '${EXPECTED_LEASE_TOKEN}', attemptNumber: 1, pipelineRevision: 1, currentRevision: 1}, pairedItem: {item: 0}}];`;

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

function buildWorkflow() {
  const localPath = resolve(__dirname, '..', 'workflows', '09-render-video.json');
  const local = JSON.parse(readFileSync(localPath, 'utf8'));
  const productionNodes = new Map(local.nodes.map((node) => [node.name, node]));
  const cloneNames = [
    'Normalize Stage Context',
    'Hash Stage Input',
    'Merge Stage Context',
    'Stage Started?',
    'Merge Attempt Context',
    'Merge Heartbeat Context',
  ];
  const cloned = cloneNames.map((name) => {
    const node = productionNodes.get(name);
    if (!node) throw new Error(`Missing production node: ${name}`);
    return JSON.parse(JSON.stringify(node));
  });
  const byName = new Map(cloned.map((node) => [node.name, node]));

  const workflow = {
    id: WORKFLOW_ID,
    name: 'WF09 Gate A Offline Native Runtime',
    active: false,
    nodes: [
      {
        parameters: {},
        type: 'n8n-nodes-base.manualTrigger',
        typeVersion: 1,
        position: [0, 0],
        id: 'offline-manual-trigger-0001',
        name: 'Manual Trigger',
      },
      codeNode('Fixed Safe Input', 'offline-fixed-input-0002', [220, 0], fixedInputCode),
      byName.get('Normalize Stage Context'),
      byName.get('Hash Stage Input'),
      codeNode('Stub Begin Stage', 'offline-begin-stage-0005', [880, 0], BEGIN_CODE),
      byName.get('Merge Stage Context'),
      byName.get('Stage Started?'),
      codeNode('Stub Reserve External Attempt', 'offline-reserve-0008', [1540, 0], RESERVE_CODE),
      byName.get('Merge Attempt Context'),
      codeNode('Stub Heartbeat Stage Lease', 'offline-heartbeat-0010', [1980, 0], HEARTBEAT_CODE),
      byName.get('Merge Heartbeat Context'),
      codeNode('Stub Render Output', 'offline-render-0012', [2420, 0], RENDER_CODE),
      codeNode('Stub Build Response', 'offline-response-0013', [2640, 0], BUILD_RESPONSE_CODE),
      codeNode('Finalize Boundary', 'offline-finalize-0014', [2860, 0], FINALIZE_CODE),
    ],
    connections: EXPECTED_CONNECTIONS,
    settings: { executionOrder: 'v1' },
    staticData: null,
  };
  validateWorkflow(workflow, productionNodes, cloneNames);
  return workflow;
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function validateWorkflow(workflow, productionNodes, cloneNames) {
  for (const name of cloneNames) {
    const clone = workflow.nodes.find((node) => node.name === name);
    if (stableStringify(clone) !== stableStringify(productionNodes.get(name))) {
      throw new Error(`Production node was modified while cloning: ${name}`);
    }
  }
  const serialized = stableStringify(workflow);
  if (serialized.includes('$env')) throw new Error('Offline workflow contains an environment expression');
  if (workflow.nodes.length !== EXPECTED_NODE_NAMES.length) {
    throw new Error('Offline workflow has duplicate, missing, or extra nodes');
  }
  const actualNodeTypes = Object.fromEntries(workflow.nodes.map((node) => [node.name, node.type]));
  if (stableStringify(actualNodeTypes) !== stableStringify(EXPECTED_NODE_TYPES)) {
    throw new Error('Offline workflow node names and types do not match the exact contract');
  }
  if (stableStringify(workflow.connections) !== stableStringify(EXPECTED_CONNECTIONS)) {
    throw new Error('Offline workflow connections do not match the exact contract');
  }
  for (const node of workflow.nodes) {
    if (!allowedTypes.has(node.type)) throw new Error(`External-capable node type rejected: ${node.type}`);
    if (Object.prototype.hasOwnProperty.call(node, 'credentials')) {
      throw new Error(`Credentials rejected on node: ${node.name}`);
    }
  }
  const freshCodeNames = new Set([
    'Fixed Safe Input', 'Stub Begin Stage', 'Stub Reserve External Attempt',
    'Stub Heartbeat Stage Lease', 'Stub Render Output', 'Stub Build Response', 'Finalize Boundary',
  ]);
  for (const node of workflow.nodes) {
    if (freshCodeNames.has(node.name) && !node.parameters.jsCode.includes('pairedItem: {item: 0}')) {
      throw new Error(`Fresh-item stub lacks explicit lineage: ${node.name}`);
    }
  }
}

function outputCounts(runData) {
  const counts = Object.fromEntries(EXPECTED_NODE_NAMES.map((name) => [name, null]));
  for (const [name, runs] of Object.entries(runData)) {
    const outputs = runs.at(-1)?.data?.main ?? [];
    counts[name] = outputs.map((items) => Array.isArray(items) ? items.length : 0);
  }
  return counts;
}

function parseNativeResult(stdout) {
  let parsed;
  try {
    parsed = JSON.parse(stdout);
  } catch (directError) {
    for (let index = 0; index < stdout.length; index += 1) {
      if (stdout[index] !== '{' && stdout[index] !== '[') continue;
      try {
        parsed = JSON.parse(stdout.slice(index));
        break;
      } catch (_) {
        // n8n can emit startup notices before the raw execution JSON.
      }
    }
    if (parsed === undefined) throw new Error(`Native raw output was not JSON (${directError.message})`);
  }
  const execution = parsed.data && parsed.data.resultData ? parsed.data : parsed;
  const resultData = execution.resultData;
  if (!resultData || !resultData.runData) throw new Error('Native output has no resultData.runData');
  return { parsed, execution, resultData };
}

function diagnosticFromResult(native, containerName) {
  const { execution, resultData } = native;
  const runData = resultData.runData;
  const executedNodeNames = Object.keys(runData);
  const counts = outputCounts(runData);
  const missingNodeNames = EXPECTED_NODE_NAMES.filter((name) => !Object.prototype.hasOwnProperty.call(runData, name));
  const lastNodeExecuted = resultData.lastNodeExecuted ?? null;
  let lastItemProducingNode = null;
  for (const name of executedNodeNames) {
    if ((counts[name] ?? []).some((count) => count > 0)) lastItemProducingNode = name;
  }
  const finalItems = runData['Finalize Boundary']?.at(-1)?.data?.main?.[0] ?? [];
  const finalJson = finalItems[0]?.json ?? {};
  return {
    isolated: true,
    offline: true,
    networkMode: 'none',
    executionId: `isolated-cli-${execution.id ?? createHash('sha256').update(containerName).digest('hex').slice(0, 16)}`,
    expectedNodeNames: EXPECTED_NODE_NAMES,
    executedNodeNames,
    missingNodeNames,
    outputCounts: counts,
    lastNodeExecuted,
    lastItemProducingNode,
    finalItemCount: finalItems.length,
    runTokenMatches: finalJson.runTokenMatches === true,
    inputHashMatches: finalJson.inputHashMatches === true,
    cleanupErrors: [],
    infrastructureError: null,
  };
}

function infrastructureDiagnostic(message) {
  return {
    isolated: true,
    offline: true,
    networkMode: 'none',
    executionId: null,
    expectedNodeNames: EXPECTED_NODE_NAMES,
    executedNodeNames: [],
    missingNodeNames: EXPECTED_NODE_NAMES,
    outputCounts: Object.fromEntries(EXPECTED_NODE_NAMES.map((name) => [name, null])),
    lastNodeExecuted: null,
    lastItemProducingNode: null,
    finalItemCount: 0,
    runTokenMatches: false,
    inputHashMatches: false,
    cleanupErrors: [],
    infrastructureError: message,
  };
}

function main() {
  const containerName = `clipcraft-wf09-offline-${process.pid}-${randomUUID().slice(0, 8)}`;
  const cleanupErrors = [];
  let tempRoot;
  let exitCode = 2;
  let diagnostic = infrastructureDiagnostic('Offline harness did not start');
  try {
    const tempBase = join(tmpdir(), 'opencode');
    mkdirSync(tempBase, { recursive: true });
    tempRoot = mkdtempSync(join(tempBase, 'wf09-offline-'));
    const fixtureDir = join(tempRoot, 'fixture');
    const n8nDataDir = join(tempRoot, 'n8n-data');
    mkdirSync(fixtureDir);
    mkdirSync(n8nDataDir);
    const workflow = buildWorkflow();
    writeFileSync(join(fixtureDir, 'workflow.json'), JSON.stringify(workflow), 'utf8');
    const command = `n8n import:workflow --input=/fixture/workflow.json 1>&2 && n8n execute --id=${WORKFLOW_ID} --rawOutput`;
    const completed = spawnSync('docker', [
      'run', '--rm', '--name', containerName, '--network', 'none',
      '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '256',
      '-e', 'HOME=/n8n-data', '-e', 'N8N_USER_FOLDER=/n8n-data',
      '-e', 'N8N_DIAGNOSTICS_ENABLED=false', '-e', 'N8N_VERSION_NOTIFICATIONS_ENABLED=false',
      '-e', 'N8N_ENCRYPTION_KEY=offline-runtime-only-not-a-production-secret',
      '-v', `${fixtureDir}:/fixture:ro`, '-v', `${n8nDataDir}:/n8n-data`,
      '--entrypoint', '/bin/sh', IMAGE, '-c', command,
    ], { encoding: 'utf8', timeout: DOCKER_TIMEOUT_MS, windowsHide: true });
    if (completed.error) throw completed.error;
    if (completed.status !== 0) {
      const safeError = (completed.stderr || `docker exited ${completed.status}`).trim().slice(-2000);
      throw new Error(`isolated n8n command failed: ${safeError}`);
    }
    diagnostic = diagnosticFromResult(parseNativeResult(completed.stdout.trim()), containerName);
    const passed = stableStringify(diagnostic.outputCounts) === stableStringify(EXPECTED_OUTPUT_COUNTS)
      && diagnostic.finalItemCount === 1
      && diagnostic.runTokenMatches && diagnostic.inputHashMatches;
    exitCode = passed ? 0 : 1;
  } catch (error) {
    diagnostic = infrastructureDiagnostic(error.message);
    exitCode = 2;
  } finally {
    try {
      const removed = spawnSync('docker', ['rm', '-f', containerName], {
        encoding: 'utf8', timeout: CLEANUP_TIMEOUT_MS, windowsHide: true,
      });
      const noSuchContainer = /No such container/i.test(removed.stderr ?? '');
      if (removed.error) cleanupErrors.push(`docker rm: ${removed.error.message}`);
      else if (removed.status !== 0 && !noSuchContainer) {
        cleanupErrors.push(`docker rm exited ${removed.status}`);
      }
    } catch (error) {
      cleanupErrors.push(`docker rm: ${error.message}`);
    }
    if (tempRoot) {
      try {
        rmSync(tempRoot, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
        if (existsSync(tempRoot)) cleanupErrors.push('temporary directory still exists');
      } catch (error) {
        cleanupErrors.push(`temporary directory: ${error.message}`);
      }
    }
  }
  diagnostic.cleanupErrors = cleanupErrors;
  if (cleanupErrors.length > 0) {
    const cleanupMessage = `cleanup: ${cleanupErrors.join(' | ')}`;
    diagnostic.infrastructureError = diagnostic.infrastructureError
      ? `${diagnostic.infrastructureError}; ${cleanupMessage}`
      : cleanupMessage;
    exitCode = 2;
  }
  process.stdout.write(`${JSON.stringify(diagnostic)}\n`);
  process.exitCode = exitCode;
}

main();
