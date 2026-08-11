const fs = require('fs');
const { execFileSync } = require('child_process');

const inspect = JSON.parse(execFileSync('docker', ['inspect', 'clipcraft-n8n'], { encoding: 'utf8' }))[0];
const apiKey = inspect.Config.Env.find((value) => value.startsWith('N8N_API_KEY=')).slice('N8N_API_KEY='.length);
const headers = { 'X-N8N-API-KEY': apiKey, 'Content-Type': 'application/json' };

async function request(url, options = {}) {
  const response = await fetch(`http://localhost:5680${url}`, { ...options, headers: { ...headers, ...(options.headers || {}) } });
  const text = await response.text();
  if (!response.ok) throw new Error(`${options.method || 'GET'} ${url} returned HTTP ${response.status}: ${text}`);
  return text ? JSON.parse(text) : null;
}

async function main() {
  const before = await request('/api/v1/workflows/17');
  const desired = JSON.parse(fs.readFileSync('workflows/17-ai-generate-text.json', 'utf8'));
  const payload = {
    name: desired.name,
    nodes: desired.nodes.map((node) => { const copy = JSON.parse(JSON.stringify(node)); delete copy.outputs; return copy; }),
    connections: desired.connections,
    settings: { executionOrder: desired.settings.executionOrder },
    staticData: desired.staticData ?? null,
  };
  await request('/api/v1/workflows/17', { method: 'PUT', body: JSON.stringify(payload) });
  let after = await request('/api/v1/workflows/17');
  if (before.active && !after.active) {
    await request('/api/v1/workflows/17/activate', { method: 'POST', body: '{}' });
    after = await request('/api/v1/workflows/17');
  }
  if (after.id !== '17' || after.active !== before.active || after.nodes.length !== desired.nodes.length) throw new Error('WF17 identity/state mismatch after import');
  console.log(JSON.stringify({ id: after.id, active: after.active, nodes: after.nodes.length, versionId: after.versionId }));
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
