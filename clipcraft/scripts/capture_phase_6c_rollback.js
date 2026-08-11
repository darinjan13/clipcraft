const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const output = path.join(process.cwd(), 'backups', 'n8n-recovery', '20260801-231151Z', 'workflow-exports', 'pre-import-live');
const inspect = JSON.parse(execFileSync('docker', ['inspect', 'clipcraft-n8n'], { encoding: 'utf8' }))[0];
const entry = inspect.Config.Env.find((value) => value.startsWith('N8N_API_KEY='));
if (!entry) throw new Error('N8N_API_KEY is not configured');
const apiKey = entry.slice('N8N_API_KEY='.length);

async function main() {
  fs.mkdirSync(output, { recursive: true });
  for (const [name, id] of [['WF05-live-pre-import.json', 'gazJuTcoSGqYdGze'], ['WF18-live-pre-import.json', '18']]) {
    const response = await fetch(`http://localhost:5680/api/v1/workflows/${id}`, { headers: { 'X-N8N-API-KEY': apiKey } });
    if (!response.ok) throw new Error(`${id} returned HTTP ${response.status}`);
    fs.writeFileSync(path.join(output, name), `${JSON.stringify(await response.json(), null, 2)}\n`);
  }
  console.log(output);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
