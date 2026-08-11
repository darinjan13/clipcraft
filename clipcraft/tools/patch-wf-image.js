const fs = require('fs');

const file = process.argv[2];
const data = JSON.parse(fs.readFileSync(file, 'utf8'));

function patchNode(name, from, to) {
  const node = data.nodes.find(n => n.name === name);
  if (!node) { console.error(`NODE NOT FOUND: ${name}`); process.exit(1); }
  const code = node.parameters.jsCode;
  if (typeof code !== 'string') { console.error(`no jsCode on ${name}`); process.exit(1); }
  if (!code.includes(from)) {
    console.error(`FROM NOT FOUND in ${name}`);
    console.error('=== EXPECTED ==='); console.error(from);
    console.error('=== ACTUAL ==='); console.error(code);
    process.exit(1);
  }
  node.parameters.jsCode = code.replace(from, to);
  console.log(`patched ${name}`);
}

// ---- Prepare Items: carry image provider/model from the job ----
const piFrom = [
  "const scenes = $input.first().json;",
  "if (!Array.isArray(scenes) || scenes.length === 0) return [];",
  "return scenes.map(s => ({ json: { scene_id: s.id, scene_index: s.scene_index, image_prompt: s.image_prompt, job_id: s.job_id, request_id: uuidV4() } }));"
].join('\n');

const piTo = [
  "const scenes = $input.first().json;",
  "const job = $('Validate').first()?.json ?? {};",
  "const brief = job.brief_json && typeof job.brief_json === 'object' ? job.brief_json : {};",
  "const imageProvider = job.image_provider ?? brief.imageProvider ?? brief.image_provider ?? null;",
  "const imageModel = job.image_model ?? brief.imageModel ?? brief.image_model ?? null;",
  "if (!Array.isArray(scenes) || scenes.length === 0) return [];",
  "return scenes.map(s => ({ json: { scene_id: s.id, scene_index: s.scene_index, image_prompt: s.image_prompt, job_id: s.job_id, request_id: uuidV4(), imageProvider, imageModel } }));"
].join('\n');

patchNode('Prepare Items', piFrom, piTo);

fs.writeFileSync(file, JSON.stringify(data, null, 2) + '\n', 'utf8');
console.log('WROTE', file);