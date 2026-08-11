const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const root = process.cwd();
const reconciled = path.join(root, 'backups', 'n8n-recovery', '20260801-231151Z', 'workflow-exports', 'reconciled');
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
  const results = [];
  for (const [file, id] of [['WF05-reconciled.json', 'gazJuTcoSGqYdGze'], ['WF18-reconciled.json', '18']]) {
    const desired = JSON.parse(fs.readFileSync(path.join(reconciled, file), 'utf8'));
    const before = await request(`/api/v1/workflows/${id}`);
    const payload = {
      name: desired.name,
      nodes: desired.nodes,
      connections: desired.connections,
      settings: { executionOrder: desired.settings.executionOrder },
      staticData: desired.staticData,
    };
    await request(`/api/v1/workflows/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
    let after = await request(`/api/v1/workflows/${id}`);
    if (before.active && !after.active) {
      await request(`/api/v1/workflows/${id}/activate`, { method: 'POST', body: '{}' });
      after = await request(`/api/v1/workflows/${id}`);
    } else if (!before.active && after.active) {
      await request(`/api/v1/workflows/${id}/deactivate`, { method: 'POST', body: '{}' });
      after = await request(`/api/v1/workflows/${id}`);
    }
    if (after.id !== id) throw new Error(`${id} changed ID to ${after.id}`);
    if (after.active !== before.active) throw new Error(`${id} changed active state`);
    if (after.nodes.length !== desired.nodes.length) throw new Error(`${id} node count mismatch`);
    results.push({ id, active: after.active, nodes: after.nodes.length, versionId: after.versionId, activeVersionId: after.activeVersionId });
  }
  console.log(JSON.stringify(results));
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
