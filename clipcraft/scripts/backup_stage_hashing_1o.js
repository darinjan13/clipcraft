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
const backupDir = path.resolve(__dirname, '..', 'backups', 'phase-7-cutover');
const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
const inspect = JSON.parse(execFileSync('docker', ['inspect', 'clipcraft-n8n'], {
  encoding: 'utf8',
  timeout: 10_000,
}))[0];
const apiKeyEntry = inspect.Config.Env.find((value) => value.startsWith('N8N_API_KEY='));
if (!apiKeyEntry) throw new Error('n8n API credentials are not configured');
const apiKey = apiKeyEntry.slice('N8N_API_KEY='.length);

async function request(workflowId) {
  const response = await fetch(`http://localhost:5680/api/v1/workflows/${workflowId}`, {
    headers: { 'X-N8N-API-KEY': apiKey },
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error(`Workflow ${workflowId} returned HTTP ${response.status}`);
  return response.json();
}

async function main() {
  const liveWorkflows = await Promise.all(WORKFLOWS.map(async (entry) => {
    const live = await request(entry.id);
    if (live.id !== entry.id || live.name !== entry.name) {
      throw new Error(`Workflow identity mismatch for ${entry.id}`);
    }
    return { entry, live };
  }));

  const destinations = liveWorkflows.map(({ entry, live }) => ({
    entry,
    live,
    output: path.join(backupDir, `${entry.prefix}-stage-hashing-${stamp}.json`),
  }));
  fs.mkdirSync(backupDir, { recursive: true });
  if (destinations.some(({ output }) => fs.existsSync(output))) {
    throw new Error('Backup destination already exists');
  }

  const createdPaths = [];
  try {
    for (const { live, output } of destinations) {
      const descriptor = fs.openSync(output, 'wx', 0o600);
      createdPaths.push(output);
      try {
        fs.writeFileSync(descriptor, `${JSON.stringify(live, null, 2)}\n`, 'utf8');
      } finally {
        fs.closeSync(descriptor);
      }
    }
  } catch (error) {
    for (const createdPath of createdPaths.reverse()) {
      try {
        fs.unlinkSync(createdPath);
      } catch {
        // Cleanup is best-effort; preserve the original write failure.
      }
    }
    throw error;
  }
  for (const { output } of destinations) console.log(output);
  console.log(JSON.stringify({ backedUp: liveWorkflows.length }));
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
