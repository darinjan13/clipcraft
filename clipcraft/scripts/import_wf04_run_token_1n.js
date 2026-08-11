const fs = require('fs');
const { execFileSync } = require('child_process');

const inspect = JSON.parse(execFileSync('docker', ['inspect', 'clipcraft-n8n'], { encoding: 'utf8' }))[0];
const entry = inspect.Config.Env.find((value) => value.startsWith('N8N_API_KEY='));
if (!entry) throw new Error('N8N_API_KEY is not configured');
const apiKey = entry.slice('N8N_API_KEY='.length);
const headers = { 'X-N8N-API-KEY': apiKey, 'Content-Type': 'application/json' };

async function request(url, options = {}) {
  const response = await fetch(`http://localhost:5680${url}`, { ...options, headers: { ...headers, ...(options.headers || {}) } });
  const text = await response.text();
  if (!response.ok) throw new Error(`${options.method || 'GET'} ${url} returned HTTP ${response.status}: ${text}`);
  return text ? JSON.parse(text) : null;
}

async function main() {
  const desired = JSON.parse(fs.readFileSync('workflows/04-generate-script-and-scenes.json', 'utf8'));
  const before = await request('/api/v1/workflows/dWTF2UGXX3R73PDW');
  const payload = {
    name: desired.name,
    nodes: desired.nodes,
    connections: desired.connections,
    settings: { executionOrder: desired.settings.executionOrder },
    staticData: desired.staticData ?? null,
  };
  await request('/api/v1/workflows/dWTF2UGXX3R73PDW', { method: 'PUT', body: JSON.stringify(payload) });
  let after = await request('/api/v1/workflows/dWTF2UGXX3R73PDW');
  if (before.active && !after.active) {
    await request('/api/v1/workflows/dWTF2UGXX3R73PDW/activate', { method: 'POST', body: '{}' });
    after = await request('/api/v1/workflows/dWTF2UGXX3R73PDW');
  }
  if (after.id !== before.id || after.active !== before.active || after.nodes.length !== desired.nodes.length) {
    throw new Error('WF04 identity, active state, or node count changed unexpectedly');
  }
  console.log(JSON.stringify({ id: after.id, active: after.active, nodes: after.nodes.length, versionId: after.versionId, activeVersionId: after.activeVersionId }));
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
