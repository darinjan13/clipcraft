const { execFileSync } = require('child_process');

const inspect = JSON.parse(execFileSync('docker', ['inspect', 'clipcraft-n8n'], { encoding: 'utf8' }))[0];
const apiKey = inspect.Config.Env.find((value) => value.startsWith('N8N_API_KEY=')).slice('N8N_API_KEY='.length);
const mode = inspect.Config.Env.find((value) => value.startsWith('IMAGE_EXECUTION_MODE='))?.split('=', 2)[1] || 'unset';
const headers = { 'X-N8N-API-KEY': apiKey, 'Content-Type': 'application/json' };

async function api(url, options = {}) {
  const response = await fetch(`http://localhost:5680${url}`, { ...options, headers: { ...headers, ...(options.headers || {}) } });
  const text = await response.text();
  if (!response.ok) throw new Error(`${options.method || 'GET'} ${url} returned HTTP ${response.status}: ${text}`);
  return text ? JSON.parse(text) : null;
}

function summarize(value) {
  if (Array.isArray(value)) return value.map(summarize);
  if (!value || typeof value !== 'object') return value;
  const result = {};
  for (const [key, item] of Object.entries(value)) {
    if (/base64|image|secret|token|authorization|signature|body/i.test(key)) {
      result[key] = typeof item === 'string' ? `<redacted:${item.length}>` : '<redacted>';
    } else {
      result[key] = summarize(item);
    }
  }
  return result;
}

async function main() {
  const path = 'phase6c-wf18-controlled-probe';
  const workflow = {
    name: `Phase 6C WF18 Controlled Probe ${Date.now()}`,
    nodes: [
      {
        parameters: { path, httpMethod: 'POST', responseMode: 'lastNode', options: {} },
        type: 'n8n-nodes-base.webhook',
        typeVersion: 2.1,
        position: [0, 0],
        id: 'phase6c-probe-webhook-000000000001',
        name: 'Controlled Probe Webhook',
      },
      {
        parameters: {
          jsCode: "const body = $json.body && typeof $json.body === 'object' ? $json.body : $json; return [{ json: body }];",
        },
        type: 'n8n-nodes-base.code',
        typeVersion: 2,
        position: [180, 0],
        id: 'phase6c-probe-unwrapper-000000000003',
        name: 'Unwrap Probe Input',
      },
      {
        parameters: {
          workflowId: { __rl: true, value: '18', mode: 'list', cachedResultName: 'AI Generate Image' },
          mode: 'each',
        },
        type: 'n8n-nodes-base.executeWorkflow',
        typeVersion: 2,
        position: [440, 0],
        id: 'phase6c-probe-execute-000000000002',
        name: 'Execute WF18',
      },
    ],
    connections: {
      'Controlled Probe Webhook': { main: [[{ node: 'Unwrap Probe Input', type: 'main', index: 0 }]] },
      'Unwrap Probe Input': { main: [[{ node: 'Execute WF18', type: 'main', index: 0 }]] },
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
      jobId: '6dc17562-2066-4ec9-9c95-b8dd9954025d',
      sceneId: '5388b73c-4da4-4979-88c5-729fb085f3e8',
      sceneIndex: 5,
      requestId: 'b7e2a7f5-7e0b-4e73-9f35-6e5eeec8a5d1',
      prompt: 'A cinematic mountain landscape at sunrise, vertical composition.',
      provider: 'cloudflare',
      modelId: '@cf/black-forest-labs/flux-1-schnell',
      _testCorrelationId: 'phase6c-controlled-legacy',
    };
    const response = await fetch(`http://localhost:5680/webhook/${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
    const text = await response.text();
    if (!response.ok) throw new Error(`Webhook returned HTTP ${response.status}: ${text.slice(0, 500)}`);
    let parsed;
    try { parsed = JSON.parse(text); } catch { parsed = text; }
    console.log(JSON.stringify({ mode, workflowId: id, httpStatus: response.status, response: summarize(parsed) }));
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
