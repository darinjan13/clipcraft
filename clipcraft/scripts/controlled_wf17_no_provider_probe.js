const { execFileSync } = require('child_process');

const inspect = JSON.parse(execFileSync('docker', ['inspect', 'clipcraft-n8n'], { encoding: 'utf8' }))[0];
const apiKey = inspect.Config.Env.find((value) => value.startsWith('N8N_API_KEY=')).slice('N8N_API_KEY='.length);
const headers = { 'X-N8N-API-KEY': apiKey, 'Content-Type': 'application/json' };

async function api(url, options = {}) {
  const response = await fetch(`http://localhost:5680${url}`, {
    ...options,
    headers: { ...headers, ...(options.headers || {}) },
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${options.method || 'GET'} ${url} returned HTTP ${response.status}: ${text}`);
  return text ? JSON.parse(text) : null;
}

function safeSummary(value) {
  return {
    probeStopped: value.probeStopped === true,
    branch: value.branch,
    jobId: value.jobId,
    requestId: value.requestId,
    providerId: value.providerId,
    modelId: value.modelId,
    credentialSource: value.credentialSource,
    routingVersion: value.routingVersion,
    responseFormat: value.responseFormat,
    hasPrompt: value.hasPrompt === true || (typeof value.prompt === 'string' && value.prompt.length > 0),
  };
}

async function main() {
  const path = `phase7-wf17-no-provider-${Date.now()}`;
  const live = await api('/api/v1/workflows/17');
  const prepare = live.nodes.find((node) => node.name === 'Prepare Internal Request');
  if (!prepare) throw new Error('WF17 Prepare Internal Request node not found');
  const prepareCode = prepare.parameters.jsCode.replace(
    /^const input = [^\n]+;\n/,
    'const input = $json ?? {};\n',
  );

  const workflow = {
    name: `Phase 7 WF17 Deterministic No Provider Probe ${Date.now()}`,
    nodes: [
      {
        parameters: { path, httpMethod: 'POST', responseMode: 'lastNode', options: {} },
        type: 'n8n-nodes-base.webhook',
        typeVersion: 2.1,
        position: [0, 0],
        id: 'phase7-wf17-probe-trigger-0001',
        name: 'Workflow Trigger',
      },
      {
        parameters: {
          jsCode: "const input = $json.body && typeof $json.body === 'object' ? $json.body : $json; return [{ json: input }];",
        },
        type: 'n8n-nodes-base.code',
        typeVersion: 2,
        position: [120, 0],
        id: 'phase7-wf17-probe-unwrap-0002',
        name: 'Unwrap Probe Input',
      },
      {
        parameters: {
          conditions: {
            boolean: [{ value1: '={{ $env.TEXT_EXECUTION_MODE }}', value2: 'internal' }],
          },
        },
        type: 'n8n-nodes-base.if',
        typeVersion: 1,
        position: [220, 0],
        id: 'phase7-wf17-probe-mode-0003',
        name: 'Text Execution Mode?',
      },
      {
        parameters: { ...prepare.parameters, jsCode: prepareCode },
        type: 'n8n-nodes-base.code',
        typeVersion: 2,
        position: [580, -100],
        id: 'phase7-wf17-probe-prepare-0004',
        name: 'Prepare Internal Request',
      },
      {
        parameters: {
          jsCode: "const input = $json; return [{ json: { probeStopped: true, branch: 'internal', ...input } }];",
        },
        type: 'n8n-nodes-base.code',
        typeVersion: 2,
        position: [820, -100],
        id: 'phase7-wf17-probe-stop-0005',
        name: 'Deterministic Probe Stop',
      },
      {
        parameters: {
          jsCode: "return [{ json: { probeStopped: true, branch: 'legacy', providerId: $json.provider ?? null } }];",
        },
        type: 'n8n-nodes-base.code',
        typeVersion: 2,
        position: [580, 100],
        id: 'phase7-wf17-probe-legacy-stop-0006',
        name: 'Legacy Probe Stop',
      },
      {
        parameters: {
          jsCode: "const value = $json; return [{ json: { probeStopped: value.probeStopped === true, branch: value.branch, jobId: value.jobId, requestId: value.requestId, providerId: value.providerId, modelId: value.modelId, credentialSource: value.credentialSource, routingVersion: value.routingVersion, responseFormat: value.responseFormat, hasPrompt: typeof value.prompt === 'string' && value.prompt.length > 0 } }];",
        },
        type: 'n8n-nodes-base.code',
        typeVersion: 2,
        position: [1060, 0],
        id: 'phase7-wf17-probe-response-0007',
        name: 'Return Probe Result',
      },
    ],
    connections: {
      'Workflow Trigger': { main: [[{ node: 'Unwrap Probe Input', type: 'main', index: 0 }]] },
      'Unwrap Probe Input': { main: [[{ node: 'Text Execution Mode?', type: 'main', index: 0 }]] },
      'Text Execution Mode?': {
        main: [
          [{ node: 'Prepare Internal Request', type: 'main', index: 0 }],
          [{ node: 'Legacy Probe Stop', type: 'main', index: 0 }],
        ],
      },
      'Prepare Internal Request': { main: [[{ node: 'Deterministic Probe Stop', type: 'main', index: 0 }]] },
      'Deterministic Probe Stop': { main: [[{ node: 'Return Probe Result', type: 'main', index: 0 }]] },
      'Legacy Probe Stop': { main: [[{ node: 'Return Probe Result', type: 'main', index: 0 }]] },
    },
    settings: { executionOrder: 'v1' },
    staticData: null,
  };

  let id;
  try {
    const created = await api('/api/v1/workflows', { method: 'POST', body: JSON.stringify(workflow) });
    id = created.id;
    await api(`/api/v1/workflows/${id}/activate`, { method: 'POST', body: '{}' });
    const input = {
      jobId: '11111111-1111-4111-8111-111111111111',
      requestId: '22222222-2222-4222-8222-222222222222',
      provider: 'cloudflare',
      modelId: '@cf/meta/llama-3.1-8b-instruct',
      credentialSource: 'environment',
      routingVersion: '1',
      prompt: 'Return one short sentence about calm focus.',
      systemPrompt: '',
      temperature: 0.2,
      maxOutputTokens: 128,
      responseFormat: 'text',
      timeoutMs: 30000,
      _testCorrelationId: 'phase7-wf17-deterministic-no-provider',
    };
    const response = await fetch(`http://localhost:5680/webhook/${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
    const text = await response.text();
    let parsed;
    try { parsed = JSON.parse(text); } catch { parsed = {}; }
    console.log(JSON.stringify({
      mode: inspect.Config.Env.find((value) => value.startsWith('TEXT_EXECUTION_MODE='))?.split('=', 2)[1] || 'unset',
      workflowId: id,
      httpStatus: response.status,
      result: safeSummary(parsed),
    }));
    if (response.status !== 200 || parsed.probeStopped !== true || parsed.branch !== 'internal') {
      throw new Error('deterministic no-provider probe did not stop at the internal boundary');
    }
  } finally {
    if (id) {
      try { await api(`/api/v1/workflows/${id}/deactivate`, { method: 'POST', body: '{}' }); } catch {}
      await api(`/api/v1/workflows/${id}`, { method: 'DELETE' });
    }
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
