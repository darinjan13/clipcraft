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

// ---- Build Request: allow gemini/cloudflare image providers, carry model ----
// provider line (same in both Build Request and Build Internal Image Request)
const provFrom = "const provider = source.provider ?? body.provider ?? $env.AI_IMAGE_PROVIDER ?? 'cloudflare';";
const provTo = "const provider = source.provider ?? source.imageProvider ?? source.image_provider ?? body.provider ?? body.imageProvider ?? body.image_provider ?? $env.AI_IMAGE_PROVIDER ?? 'cloudflare';";

// Build Request: model + provider rejection
const brHardFrom = "if (provider !== 'cloudflare') return invalid('UNSUPPORTED_PROVIDER', 'Unsupported image provider: ' + provider);";
const brHardTo = "const SUPPORTED_IMAGE_PROVIDERS = ['gemini', 'cloudflare'];\nif (!SUPPORTED_IMAGE_PROVIDERS.includes(provider)) return invalid('UNSUPPORTED_PROVIDER', 'Unsupported image provider: ' + provider);";

// Build Internal Image Request uses a different invalid signature (context), so we only swap the provider line there.
// ---- Prepare Internal Image Request: providerId/modelId + accept imageProvider/imageModel ----
const pirProvFrom = "const providerId = pick(trigger.providerId, trigger.provider_id, trigger.provider, source.providerId, source.provider_id, source.provider, body.providerId, body.provider_id, body.provider, $env.AI_IMAGE_PROVIDER, 'cloudflare');";
const pirProvTo = "const providerId = pick(trigger.providerId, trigger.provider_id, trigger.provider, trigger.imageProvider, trigger.image_provider, trigger.imageProvider, source.providerId, source.provider_id, source.provider, source.imageProvider, source.image_provider, body.providerId, body.provider_id, body.provider, body.imageProvider, body.image_provider, $env.AI_IMAGE_PROVIDER, 'cloudflare');";

const pirModelFrom = "const modelId = pick(trigger.modelId, trigger.model_id, source.modelId, source.model_id, body.modelId, body.model_id, $env.CLOUDFLARE_IMAGE_MODEL);";
const pirModelTo = "const modelId = pick(trigger.modelId, trigger.model_id, trigger.imageModel, trigger.image_model, source.modelId, source.model_id, source.imageModel, source.image_model, body.modelId, body.model_id, body.imageModel, body.image_model, $env.CLOUDFLARE_IMAGE_MODEL);";

patchNode('Build Internal Image Request', provFrom, provTo);
patchNode('Build Request', provFrom, provTo);
patchNode('Build Request', brHardFrom, brHardTo);
patchNode('Prepare Internal Image Request', pirProvFrom, pirProvTo);
patchNode('Prepare Internal Image Request', pirModelFrom, pirModelTo);

fs.writeFileSync(file, JSON.stringify(data, null, 2) + '\n', 'utf8');
console.log('WROTE', file);