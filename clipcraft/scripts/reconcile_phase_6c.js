const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const root = process.cwd();
const recovery = path.join(root, 'backups', 'n8n-recovery', '20260801-231151Z');
const source = path.join(recovery, 'workflow-exports');
const output = path.join(source, 'reconciled');

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function getApiKey() {
  const inspect = execFileSync('docker', ['inspect', 'clipcraft-n8n'], { encoding: 'utf8' });
  const container = JSON.parse(inspect)[0];
  const entry = container.Config.Env.find((value) => value.startsWith('N8N_API_KEY='));
  if (!entry) throw new Error('N8N_API_KEY is not configured');
  return entry.slice('N8N_API_KEY='.length);
}

async function getLive(id, apiKey) {
  const response = await fetch(`http://localhost:5680/api/v1/workflows/${id}`, {
    headers: { 'X-N8N-API-KEY': apiKey },
  });
  if (!response.ok) throw new Error(`Live workflow ${id} returned HTTP ${response.status}`);
  return response.json();
}

async function getCredential(apiKey) {
  const response = await fetch('http://localhost:5680/api/v1/credentials', {
    headers: { 'X-N8N-API-KEY': apiKey },
  });
  if (!response.ok) throw new Error(`Credentials returned HTTP ${response.status}`);
  const body = await response.json();
  const credential = body.data.find((item) => item.type === 'clipCraftInternalApi');
  if (!credential) throw new Error('ClipCraft Internal API credential is missing');
  return credential;
}

function nodeByName(workflow, name) {
  const node = workflow.nodes.find((item) => item.name === name);
  if (!node) throw new Error(`Missing node ${name}`);
  return node;
}

function commonMetadata(repository, live) {
  const merged = clone(repository);
  for (const key of ['id', 'name', 'description', 'active', 'isArchived', 'createdAt', 'updatedAt', 'meta', 'tags']) {
    if (live[key] !== undefined) merged[key] = clone(live[key]);
  }
  for (const node of merged.nodes) delete node.outputs;
  return merged;
}

function buildWf05(repository, live) {
  const merged = commonMetadata(repository, live);
  const livePending = nodeByName(live, 'Get Pending Scenes');
  const liveDecode = nodeByName(live, 'Decode Image');
  const liveWrite = nodeByName(live, 'Write Image File');
  const liveUpdate = nodeByName(live, 'Update Scene Record');
  const liveAsset = nodeByName(live, 'Insert Asset Record');
  const liveResponse = nodeByName(live, 'Build Response');
  const pendingScenes = nodeByName(live, 'Pending Scenes?');
  const existingImages = nodeByName(live, 'Return Existing Images');

  nodeByName(merged, 'Get Pending Scenes').parameters = clone(livePending.parameters);
  nodeByName(merged, 'Prepare Items').parameters = {
    jsCode: "const uuidV4 = () => { const bytes = new Uint8Array(16); for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256); bytes[6] = (bytes[6] & 0x0f) | 0x40; bytes[8] = (bytes[8] & 0x3f) | 0x80; return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('').replace(/^(........)(....)(....)(....)(............)$/, '$1-$2-$3-$4-$5'); };\nconst scenes = $input.all().map(item => item.json);\nif (scenes.length === 0) return [{json: {skipImages: true, job_id: $('Validate').first().json.jobId}}];\nreturn scenes.map(s => ({json: {scene_id: s.id, scene_index: s.scene_index, image_prompt: s.image_prompt, job_id: s.job_id, request_id: uuidV4()}}));",
  };
  const saveIndex = merged.nodes.findIndex((node) => node.name === 'Save Image File');
  merged.nodes[saveIndex] = clone(liveDecode);
  for (const [name, liveNode] of [['Update Scene Record', liveUpdate], ['Insert Asset Record', liveAsset], ['Build Response', liveResponse]]) {
    const index = merged.nodes.findIndex((node) => node.name === name);
    merged.nodes[index] = clone(liveNode);
  }
  nodeByName(merged, 'Execute AI Image').parameters = clone(nodeByName(live, 'Execute Cloudflare Image').parameters);
  nodeByName(merged, 'Execute AI Image').parameters.workflowId = {
    __rl: true,
    value: '18',
    mode: 'list',
    cachedResultName: 'AI Generate Image',
  };
  merged.nodes.push(clone(liveWrite), clone(pendingScenes), clone(existingImages));
  merged.connections['Prepare Items'] = { main: [[{ node: 'Pending Scenes?', type: 'main', index: 0 }]] };
  delete merged.connections['Save Image File'];
  delete merged.connections['Insert Asset Record'];
  delete merged.connections['Update Scene Record'];
  delete merged.connections['Build Response'];
  merged.connections['AI Image Success?'] = {
    main: [
      [{ node: 'Decode Image', type: 'main', index: 0 }],
      [{ node: 'Finalize Provider Failure', type: 'main', index: 0 }],
    ],
  };
  merged.connections['Decode Image'] = { main: [[{ node: 'Write Image File', type: 'main', index: 0 }]] };
  merged.connections['Write Image File'] = { main: [[{ node: 'Update Scene Record', type: 'main', index: 0 }]] };
  merged.connections['Update Scene Record'] = { main: [[{ node: 'Insert Asset Record', type: 'main', index: 0 }]] };
  merged.connections['Insert Asset Record'] = { main: [[{ node: 'Build Response', type: 'main', index: 0 }]] };
  merged.connections['Build Response'] = { main: [[{ node: 'Finalize Stage', type: 'main', index: 0 }]] };
  merged.connections['Pending Scenes?'] = {
    main: [
      [{ node: 'Execute AI Image', type: 'main', index: 0 }],
      [{ node: 'Return Existing Images', type: 'main', index: 0 }],
    ],
  };
  merged.connections['Return Existing Images'] = { main: [] };
  return merged;
}

function buildWf18(repository, live, credential) {
  const merged = commonMetadata(repository, live);
  const internalNode = nodeByName(merged, 'ClipCraft Image Execute');
  internalNode.credentials = {
    clipCraftInternalApi: { id: credential.id, name: credential.name },
  };
  return merged;
}

async function main() {
  const apiKey = getApiKey();
  const [currentWf05, currentWf18, credential] = await Promise.all([
    getLive('gazJuTcoSGqYdGze', apiKey),
    getLive('18', apiKey),
    getCredential(apiKey),
  ]);
  const backupWf05 = readJson(path.join(source, 'live-current', 'WF05-live.json'));
  const backupWf18 = readJson(path.join(source, 'live-current', 'WF18-live.json'));
  const currentDiffersFromBackup = JSON.stringify(backupWf05.nodes) !== JSON.stringify(currentWf05.nodes)
    || JSON.stringify(backupWf05.connections) !== JSON.stringify(currentWf05.connections)
    || JSON.stringify(backupWf18.nodes) !== JSON.stringify(currentWf18.nodes)
    || JSON.stringify(backupWf18.connections) !== JSON.stringify(currentWf18.connections);
  if (currentDiffersFromBackup) console.log('current live contains the previously imported Phase 6C graph; using the immutable backup as the live source for regeneration');

  const repositoryWf05 = readJson(path.join(root, 'workflows', '05-generate-scene-images.json'));
  const repositoryWf18 = readJson(path.join(root, 'workflows', '18-ai-generate-image.json'));
  const reconciledWf05 = buildWf05(repositoryWf05, backupWf05);
  const reconciledWf18 = buildWf18(repositoryWf18, backupWf18, credential);

  fs.mkdirSync(output, { recursive: true });
  fs.writeFileSync(path.join(output, 'WF05-reconciled.json'), `${JSON.stringify(reconciledWf05, null, 2)}\n`);
  fs.writeFileSync(path.join(output, 'WF18-reconciled.json'), `${JSON.stringify(reconciledWf18, null, 2)}\n`);
  console.log(JSON.stringify({
    wf05: { id: reconciledWf05.id, active: reconciledWf05.active, nodes: reconciledWf05.nodes.length },
    wf18: { id: reconciledWf18.id, active: reconciledWf18.active, nodes: reconciledWf18.nodes.length },
    credential: { id: credential.id, name: credential.name },
  }));
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
