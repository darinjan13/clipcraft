const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const WORKFLOWS = [
  { file: '05-generate-scene-images.json', id: 'gazJuTcoSGqYdGze', name: 'Generate Scene Images', prefix: 'wf05' },
  { file: '06-generate-narration.json', id: 'UhWkv3GLHVSpWrMe', name: 'Generate Narration', prefix: 'wf06' },
  { file: '07-build-captions.json', id: 'dNgYGCqkbwr552EW', name: 'Build Captions', prefix: 'wf07' },
  { file: '08-build-render-manifest.json', id: 'iik8qVHvgD9xWWjI', name: 'Build Render Manifest', prefix: 'wf08' },
  { file: '09-render-video.json', id: 'gqX0rJ1gqzHCNDso', name: 'Render AI Video', prefix: 'wf09' },
];
const workflowsDir = path.resolve(__dirname, '..', 'workflows');
const backupDir = path.resolve(__dirname, '..', 'backups', 'phase-7-cutover');
const expectedHashParameters = {
  action: 'hash',
  binaryData: false,
  type: 'SHA256',
  value: '={{ $json.stageHashInput }}',
  dataPropertyName: 'inputHash',
  encoding: 'hex',
};
const expectedMergeCode = "const {stageHashInput, ...context} = $('Hash Stage Input').first().json;\nconst result = $json;\nreturn [{json: {...context, stageState: result.state, stageRunId: result.stage_run_id, runToken: result.run_token, cachedOutput: result.output}}];";
const WRITABLE_NODE_KEYS = [
  'id',
  'name',
  'webhookId',
  'disabled',
  'notesInFlow',
  'notes',
  'type',
  'typeVersion',
  'executeOnce',
  'alwaysOutputData',
  'retryOnFail',
  'maxTries',
  'waitBetweenTries',
  'continueOnFail',
  'onError',
  'position',
  'parameters',
  'credentials',
  'customTelemetryTags',
];
const WRITABLE_SETTING_KEYS = [
  'saveExecutionProgress',
  'saveManualExecutions',
  'saveDataErrorExecution',
  'saveDataSuccessExecution',
  'executionTimeout',
  'errorWorkflow',
  'timezone',
  'executionOrder',
  'callerPolicy',
  'callerIds',
  'timeSavedPerExecution',
];
const STABILIZATION_ATTEMPTS = 6;
const STABILIZATION_DELAY_MS = 500;
const inspect = JSON.parse(execFileSync('docker', ['inspect', 'clipcraft-n8n'], {
  encoding: 'utf8',
  timeout: 10_000,
}))[0];
const apiKeyEntry = inspect.Config.Env.find((value) => value.startsWith('N8N_API_KEY='));
if (!apiKeyEntry) throw new Error('n8n API credentials are not configured');
const apiKey = apiKeyEntry.slice('N8N_API_KEY='.length);

async function main() {
  const liveWorkflows = await Promise.all(WORKFLOWS.map(async (entry) => {
    const wf = await api(`/api/v1/workflows/${entry.id}`);
    if (wf.id !== entry.id || wf.name !== entry.name || wf.active !== true) {
      throw new Error(`Live workflow preflight failed for ${entry.id}`);
    }
    return [entry.id, wf];
  }));
  const liveById = new Map(liveWorkflows);
  const selectedBackups = assertBackupSet();
  const selectedById = new Map(selectedBackups.map((selected) => [selected.entry.id, selected]));
  for (const selected of selectedBackups) {
    deepEqual(selected.backup, liveById.get(selected.entry.id), `${selected.entry.id} backup against live workflow`);
  }
  const desiredById = new Map(WORKFLOWS.map((entry) => {
    const desired = JSON.parse(fs.readFileSync(path.join(workflowsDir, entry.file), 'utf8'));
    validateDesiredWorkflow(entry, desired);
    return [entry.id, desired];
  }));

  const attempted = [];
  const outcomes = [];
  try {
    for (const entry of WORKFLOWS) {
      const selected = selectedById.get(entry.id);
      const before = selected.backup;
      const desired = desiredById.get(entry.id);
      const expected = expectedUpdatedWorkflow(before, desired);
      // n8n exposes no conditional PUT; the controller must keep this deployment quiescent and exclusive.
      const current = await api(`/api/v1/workflows/${entry.id}`);
      deepEqual(current, selected.backup, `${entry.id} drift fence`);
      if (isDesiredMutationStateUnchanged(before, desired)) {
        outcomes.push({
          id: current.id,
          name: current.name,
          nodes: current.nodes.length,
          versionId: current.versionId,
          active: current.active,
          skipped: true,
        });
        continue;
      }
      const attempt = { selected, expected, uncertain: false };
      attempted.push(attempt);
      const payload = buildPayload(before, desired);
      deepEqual(Object.keys(payload).sort(), ['connections', 'name', 'nodes', 'settings', 'staticData'], 'PUT payload keys');
      try {
        await api(`/api/v1/workflows/${entry.id}`, { method: 'PUT', body: JSON.stringify(payload) });
      } catch (error) {
        attempt.uncertain = true;
        throw error;
      }
      let after = await api(`/api/v1/workflows/${entry.id}`);
      after = await reconcileActiveState(entry, before.active, after);
      verifyWorkflow(entry, expected, after, 'import');
      outcomes.push({
        id: after.id,
        name: after.name,
        nodes: after.nodes.length,
        versionId: after.versionId,
        active: after.active,
        skipped: false,
      });
    }
  } catch (primaryError) {
    const rollbackErrors = await rollbackAttempted(attempted);
    const diagnostics = rollbackErrors.length ? rollbackErrors.join(' | ') : 'none';
    throw new Error(`Import failed: ${primaryError.message}; rollback errors: ${diagnostics}`);
  }
  for (const outcome of outcomes) console.log(JSON.stringify(outcome));
}

function assertBackupSet() {
  const names = fs.existsSync(backupDir) ? fs.readdirSync(backupDir) : [];
  const stamps = [...new Set(names.map((name) => {
    for (const entry of WORKFLOWS) {
      const prefix = `${entry.prefix}-stage-hashing-`;
      if (name.startsWith(prefix) && name.endsWith('.json')) return name.slice(prefix.length, -5);
    }
    return null;
  }).filter(Boolean))].sort().reverse();

  for (const stamp of stamps) {
    const selected = [];
    for (const entry of WORKFLOWS) {
      const backupPath = path.join(backupDir, `${entry.prefix}-stage-hashing-${stamp}.json`);
      if (!fs.existsSync(backupPath)) break;
      try {
        const backup = JSON.parse(fs.readFileSync(backupPath, 'utf8'));
        const valid = backup.id === entry.id
          && backup.name === entry.name
          && Array.isArray(backup.nodes)
          && backup.connections && typeof backup.connections === 'object'
          && !Array.isArray(backup.connections);
        if (!valid) break;
        selected.push({ entry, path: backupPath, backup });
      } catch {
        break;
      }
    }
    if (selected.length === WORKFLOWS.length) return selected;
  }
  throw new Error('A valid complete common-timestamp backup set is required');
}

function validateDesiredWorkflow(entry, desired) {
  if (desired.name !== entry.name) throw new Error(`Local workflow name mismatch for ${entry.id}`);
  const hashNodes = desired.nodes.filter((node) => node.name === 'Hash Stage Input');
  if (hashNodes.length !== 1) throw new Error(`${entry.id} must have exactly one Hash Stage Input node`);
  const hashNode = hashNodes[0];
  if (hashNode.type !== 'n8n-nodes-base.crypto' || hashNode.typeVersion !== 2) {
    throw new Error(`${entry.id} must use Crypto v2 for trusted hashing`);
  }
  deepEqual(hashNode.parameters, expectedHashParameters, `${entry.id} hash parameters`);
  deepEqual(desired.connections['Normalize Stage Context']?.main, [
    [{ node: 'Hash Stage Input', type: 'main', index: 0 }],
  ], `${entry.id} Normalize-to-Hash graph`);
  deepEqual(desired.connections['Hash Stage Input']?.main, [
    [{ node: 'Begin Stage', type: 'main', index: 0 }],
  ], `${entry.id} Hash-to-Begin graph`);
  const mergeNodes = desired.nodes.filter((node) => node.name === 'Merge Stage Context');
  if (mergeNodes.length !== 1) throw new Error(`${entry.id} must have exactly one Merge Stage Context node`);
  const mergeCode = mergeNodes[0].parameters?.jsCode || '';
  if (mergeCode !== expectedMergeCode) throw new Error(`${entry.id} merge code does not match the audited contract`);
}

function buildPayload(before, desired) {
  return {
    name: before.name,
    nodes: desired.nodes.map(projectWritableNode),
    connections: desired.connections,
    settings: projectWritableSettings(before.settings),
    staticData: before.staticData ?? null,
  };
}

function projectWritableNode(node) {
  const projected = {};
  for (const key of WRITABLE_NODE_KEYS) {
    if (Object.prototype.hasOwnProperty.call(node, key) && node[key] !== undefined) {
      projected[key] = node[key];
    }
  }
  return projected;
}

function projectWritableSettings(settings) {
  const projected = {};
  for (const key of WRITABLE_SETTING_KEYS) {
    if (Object.prototype.hasOwnProperty.call(settings, key) && settings[key] !== undefined) {
      projected[key] = settings[key];
    }
  }
  return projected;
}

function expectedUpdatedWorkflow(before, desired) {
  return {
    id: before.id,
    name: before.name,
    active: before.active,
    nodes: desired.nodes.map(projectWritableNode),
    connections: desired.connections,
    settings: before.settings,
    staticData: before.staticData ?? null,
  };
}

function isDesiredMutationStateUnchanged(before, desired) {
  return stableStringify(buildPayload(before, before)) === stableStringify(buildPayload(before, desired));
}

function verifyWorkflow(entry, expected, actual, operation) {
  if (actual.id !== expected.id || actual.id !== entry.id || actual.name !== expected.name || actual.active !== expected.active) {
    throw new Error(`${operation} identity or active state mismatch for ${entry.id}`);
  }
  deepEqual(actual.settings, expected.settings, `${operation} settings for ${entry.id}`);
  deepEqual(actual.staticData ?? null, expected.staticData ?? null, `${operation} staticData for ${entry.id}`);
  if (actual.nodes.length !== expected.nodes.length) throw new Error(`${operation} node count mismatch for ${entry.id}`);
  deepEqual(projectExecutable(actual), projectExecutable(expected), `${operation} executable workflow for ${entry.id}`);
}

async function reconcileActiveState(entry, expectedActive, current) {
  if (current.active === expectedActive) return current;
  const action = expectedActive ? 'activate' : 'deactivate';
  const endpoint = expectedActive
    ? `/api/v1/workflows/${entry.id}/activate`
    : `/api/v1/workflows/${entry.id}/deactivate`;
  let mutationError = null;
  try {
    await api(endpoint, { method: 'POST', body: '{}' });
  } catch (error) {
    mutationError = error;
  }
  try {
    current = await api(`/api/v1/workflows/${entry.id}`);
  } catch (error) {
    const prefix = mutationError ? `${mutationError.message}; ` : '';
    throw new Error(`${prefix}${action} reconciliation failed for ${entry.id}: ${error.message}`);
  }
  if (current.active !== expectedActive) {
    const prefix = mutationError ? `${mutationError.message}; ` : '';
    throw new Error(`${prefix}${action} state mismatch for ${entry.id}`);
  }
  return current;
}

async function rollbackAttempted(attempted) {
  const rollbackErrors = [];
  for (const attempt of [...attempted].reverse()) {
    try {
      await rollbackWorkflow(attempt.selected.entry, attempt.selected.backup, attempt.expected, attempt.uncertain);
    } catch (error) {
      rollbackErrors.push(`${attempt.selected.entry.id}: ${error.message}`);
    }
  }
  return rollbackErrors;
}

async function rollbackWorkflow(entry, backup, expected, uncertain) {
  const observed = await observeRollbackState(entry, backup, expected, uncertain);
  const current = observed.current;
  if (observed.classification === 'backup') {
    const restored = await reconcileActiveState(entry, backup.active, current);
    verifyWorkflow(entry, backup, restored, 'rollback');
    return;
  }
  if (observed.classification === 'drift') {
    throw new Error(`concurrent drift; rollback skipped for ${entry.id}`);
  }

  const payload = buildPayload(backup, backup);
  let putError = null;
  try {
    await api(`/api/v1/workflows/${entry.id}`, { method: 'PUT', body: JSON.stringify(payload) });
  } catch (error) {
    putError = error;
  }

  try {
    let restored = await api(`/api/v1/workflows/${entry.id}`);
    restored = await reconcileActiveState(entry, backup.active, restored);
    verifyWorkflow(entry, backup, restored, 'rollback');
  } catch (error) {
    const prefix = putError ? `${putError.message}; ` : '';
    throw new Error(`${prefix}rollback reconciliation failed for ${entry.id}: ${error.message}`);
  }
}

async function observeRollbackState(entry, backup, expected, stabilize) {
  const attempts = stabilize ? STABILIZATION_ATTEMPTS : 1;
  let observed = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const current = await api(`/api/v1/workflows/${entry.id}`);
    const classification = classifyWorkflowState(current, backup, expected);
    observed = { current, classification };
    if (classification !== 'backup') return observed;
    if (attempt < attempts - 1) await delay(STABILIZATION_DELAY_MS);
  }
  return observed;
}

function classifyWorkflowState(current, backup, expected) {
  const currentState = workflowMutationState(current);
  const backupState = workflowMutationState(backup);
  const desiredState = workflowMutationState(expected);
  if (stableStringify(currentState) === stableStringify(backupState)) return 'backup';
  if (stableStringify(currentState) !== stableStringify(desiredState)) {
    return 'drift';
  }
  return 'desired';
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function workflowMutationState(workflow) {
  return {
    id: workflow.id,
    name: workflow.name,
    nodes: workflow.nodes,
    connections: workflow.connections,
    settings: workflow.settings,
    staticData: workflow.staticData ?? null,
  };
}

function projectExecutable(workflow) {
  return { nodes: workflow.nodes, connections: workflow.connections };
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function deepEqual(actual, expected, label) {
  if (stableStringify(actual) !== stableStringify(expected)) throw new Error(`${label} mismatch`);
}

async function api(url, options = {}) {
  const response = await fetch(`http://localhost:5680${url}`, {
    ...options,
    headers: {
      'X-N8N-API-KEY': apiKey,
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    },
    signal: AbortSignal.timeout(10_000),
  });
  const text = await response.text();
  if (!response.ok) {
    let detail = '';
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed.message === 'string') detail = `: ${parsed.message.slice(0, 300)}`;
    } catch {
      // Non-JSON response bodies are intentionally omitted from diagnostics.
    }
    throw new Error(`${options.method || 'GET'} ${url} returned HTTP ${response.status}${detail}`);
  }
  return text ? JSON.parse(text) : null;
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
