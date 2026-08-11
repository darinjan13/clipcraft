'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const packageJson = require('../package.json');

test('package exposes exactly two nodes and one credential', () => {
  assert.deepEqual(packageJson.n8n.nodes, [
    'dist/nodes/ClipCraftTextExecute/ClipCraftTextExecute.node.js',
    'dist/nodes/ClipCraftImageExecute/ClipCraftImageExecute.node.js',
  ]);
  assert.deepEqual(packageJson.n8n.credentials, [
    'dist/credentials/ClipCraftInternalApi.credentials.js',
  ]);
});

const workflowPath = path.resolve(__dirname, '../../../workflows/17-ai-generate-text.json');

test('WF17 references the custom node without exposing internal transport or signing secrets', {
  skip: !fs.existsSync(workflowPath) && 'workflow repository is outside the isolated package build context',
}, () => {
  const workflow = fs.readFileSync(workflowPath, 'utf8');

  assert.equal(workflow.includes('clipCraftTextExecute'), true);
  assert.equal(workflow.includes('/internal/ai/text/execute'), false);
  assert.equal(workflow.includes('N8N_INTERNAL_SIGNING_SECRET'), false);
  assert.equal(workflow.includes('HMAC'), false);
  assert.equal(workflow.includes('signingSecret'), false);
});
