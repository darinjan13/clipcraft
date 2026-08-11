const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
const output = path.join(process.cwd(), 'backups', 'phase-7-cutover', `wf04-run-token-reconciliation-${stamp}.json`);
const inspect = JSON.parse(execFileSync('docker', ['inspect', 'clipcraft-n8n'], { encoding: 'utf8' }))[0];
const entry = inspect.Config.Env.find((value) => value.startsWith('N8N_API_KEY='));
if (!entry) throw new Error('N8N_API_KEY is not configured');
const apiKey = entry.slice('N8N_API_KEY='.length);

async function main() {
  const response = await fetch('http://localhost:5680/api/v1/workflows/dWTF2UGXX3R73PDW', {
    headers: { 'X-N8N-API-KEY': apiKey },
  });
  if (!response.ok) throw new Error(`WF04 returned HTTP ${response.status}`);
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, `${JSON.stringify(await response.json(), null, 2)}\n`);
  console.log(output);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
