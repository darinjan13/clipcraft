const fs = require('fs');
const path = require('path');

const backupPath = path.resolve(
  __dirname,
  '..',
  'backups',
  'phase-7-cutover',
  'wf09-stage-hashing-20260804T132837Z.json',
);
const outputPath = path.resolve(__dirname, '..', 'workflows', '09-render-video.json');

const expectedNormalizeCode = "const input = $json.body ?? $json;\nconst jobId = input.jobId ?? input.id;\nif (!jobId) throw new Error('JOB_ID_REQUIRED');\nconst workerId = input.workerId || input.claimed_by || 'clipcraft-n8n';\nconst leaseToken = input.leaseToken || input.lease_token || ('legacy-render-' + jobId);\nconst attemptNumber = Number(input.attemptNumber ?? input.attempt_number ?? 0);\nconst pipelineRevision = Number(input.pipelineRevision ?? input.pipeline_revision ?? 1);\nconst stage = 'render';\nconst itemKey = input.itemKey ?? 'job';\nconst canonical = JSON.stringify({jobId, pipelineRevision, stage, itemKey, revision: input.currentRevision ?? pipelineRevision});\nconst inputHash = canonical;\nreturn [{json: {...input, jobId, stage, itemKey, inputHash, workerId, leaseToken, attemptNumber, pipelineRevision}}];\n";
const desiredNormalizeCode = "const input = $json.body ?? $json;\nconst jobId = input.jobId ?? input.id;\nif (!jobId) throw new Error('JOB_ID_REQUIRED');\nconst workerId = input.workerId || input.claimed_by || 'clipcraft-n8n';\nconst leaseToken = input.leaseToken || input.lease_token || ('legacy-render-' + jobId);\nconst attemptNumber = Number(input.attemptNumber ?? input.attempt_number ?? 0);\nconst pipelineRevision = Number(input.pipelineRevision ?? input.pipeline_revision ?? 1);\nconst stage = 'render';\nconst itemKey = input.itemKey ?? 'job';\nconst canonical = JSON.stringify({jobId, pipelineRevision, stage, itemKey, revision: input.currentRevision ?? pipelineRevision});\nreturn [{json: {...input, jobId, stage, itemKey, stageHashInput: canonical, workerId, leaseToken, attemptNumber, pipelineRevision}}];\n";
const expectedMergeCode = "const context = $('Normalize Stage Context').first().json;\nconst result = $json;\nreturn [{json: {...context, stageState: result.state, stageRunId: result.stage_run_id, runToken: result.run_token, cachedOutput: result.output}}];";
const desiredMergeCode = "const {stageHashInput, ...context} = $('Hash Stage Input').first().json;\nconst result = $json;\nreturn [{json: {...context, stageState: result.state, stageRunId: result.stage_run_id, runToken: result.run_token, cachedOutput: result.output}}];";
const normalizeToBegin = [[{ node: 'Begin Stage', type: 'main', index: 0 }]];
const triggerToValidate = [[{ node: 'Validate Input', type: 'main', index: 0 }]];
const beginToMerge = [[{ node: 'Merge Stage Context', type: 'main', index: 0 }]];

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function assertEqual(actual, expected, label) {
  if (stableStringify(actual) !== stableStringify(expected)) {
    throw new Error(`Authoritative WF09 backup has unexpected ${label}`);
  }
}

function uniqueNode(workflow, name) {
  const matches = workflow.nodes.filter((node) => node.name === name);
  if (matches.length !== 1) throw new Error(`Authoritative WF09 backup must contain one ${name} node`);
  return matches[0];
}

const backup = JSON.parse(fs.readFileSync(backupPath, 'utf8'));
const repository = JSON.parse(fs.readFileSync(outputPath, 'utf8'));

if (backup.id !== 'gqX0rJ1gqzHCNDso' || backup.name !== 'Render AI Video') {
  throw new Error('Authoritative WF09 backup identity mismatch');
}
if (!Array.isArray(backup.nodes) || !backup.connections || Array.isArray(backup.connections)) {
  throw new Error('Authoritative WF09 backup executable shape mismatch');
}
if (repository.name !== 'Render AI Video' || !Array.isArray(repository.nodes)) {
  throw new Error('Repository WF09 wrapper shape mismatch');
}
if (backup.nodes.some((node) => node.name === 'Hash Stage Input')) {
  throw new Error('Authoritative WF09 backup unexpectedly contains Hash Stage Input');
}

const normalize = uniqueNode(backup, 'Normalize Stage Context');
const merge = uniqueNode(backup, 'Merge Stage Context');
uniqueNode(backup, 'Begin Stage');
uniqueNode(backup, 'Workflow Trigger');
uniqueNode(backup, 'Validate Input');
assertEqual(normalize.parameters?.jsCode, expectedNormalizeCode, 'Normalize Stage Context code');
assertEqual(merge.parameters?.jsCode, expectedMergeCode, 'Merge Stage Context code');
assertEqual(backup.connections['Normalize Stage Context']?.main, normalizeToBegin, 'Normalize Stage Context connection');
assertEqual(backup.connections['Begin Stage']?.main, beginToMerge, 'Begin Stage connection');
assertEqual(backup.connections['Workflow Trigger']?.main, triggerToValidate, 'Workflow Trigger blocker');

const hashNode = {
  parameters: {
    action: 'hash',
    binaryData: false,
    type: 'SHA256',
    value: '={{ $json.stageHashInput }}',
    dataPropertyName: 'inputHash',
    encoding: 'hex',
  },
  type: 'n8n-nodes-base.crypto',
  typeVersion: 2,
  position: [-775, 0],
  id: '4b2-hash-stage-input',
  name: 'Hash Stage Input',
};

const nodes = [];
for (const node of backup.nodes) {
  if (node.name === 'Normalize Stage Context') {
    nodes.push({ ...node, parameters: { ...node.parameters, jsCode: desiredNormalizeCode } });
    nodes.push(hashNode);
  } else if (node.name === 'Merge Stage Context') {
    nodes.push({ ...node, parameters: { ...node.parameters, jsCode: desiredMergeCode } });
  } else {
    nodes.push(node);
  }
}

const connections = JSON.parse(JSON.stringify(backup.connections));
connections['Normalize Stage Context'] = {
  main: [[{ node: 'Hash Stage Input', type: 'main', index: 0 }]],
};
connections['Hash Stage Input'] = {
  main: [[{ node: 'Begin Stage', type: 'main', index: 0 }]],
};

const output = {
  ...repository,
  nodes,
  connections,
  settings: backup.settings,
  pinData: backup.pinData,
};
output.staticData = backup.staticData ?? null;

fs.writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`, 'utf8');
