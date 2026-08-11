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

const buildIn = [
  "if (provider !== 'cloudflare') return invalid('UNSUPPORTED_PROVIDER', 'Unsupported text provider: ' + provider);",
  "const accountId = $env.CLOUDFLARE_ACCOUNT_ID;",
  "const model = $env.CLOUDFLARE_TEXT_MODEL;",
  "const token = $env.CLOUDFLARE_AI_TOKEN;",
  "if (!accountId || !model || !token) return invalid('PROVIDER_CONFIG_MISSING', 'Cloudflare AI credentials are not configured', provider);",
  "const messages = [];",
  "if (systemPrompt.trim()) messages.push({ role: 'system', content: systemPrompt });",
  "messages.push({ role: 'user', content: prompt });",
  "return [{ json: { isValid: true, provider, url: 'https://api.cloudflare.com/client/v4/accounts/' + accountId + '/ai/run/' + model, headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' }, body: { messages, max_tokens: 5000, temperature: 0.6 } } }];"
].join('\n');

const buildTo = [
  "const SUPPORTED_TEXT_PROVIDERS = ['gemini', 'cloudflare'];",
  "if (!SUPPORTED_TEXT_PROVIDERS.includes(provider)) return invalid('UNSUPPORTED_PROVIDER', 'Unsupported text provider: ' + provider);",
  "const messages = [];",
  "if (systemPrompt.trim()) messages.push({ role: 'system', content: systemPrompt });",
  "messages.push({ role: 'user', content: prompt });",
  "if (provider === 'cloudflare') {",
  "  const accountId = $env.CLOUDFLARE_ACCOUNT_ID;",
  "  const model = $env.CLOUDFLARE_TEXT_MODEL;",
  "  const token = $env.CLOUDFLARE_AI_TOKEN;",
  "  if (!accountId || !model || !token) return invalid('PROVIDER_CONFIG_MISSING', 'Cloudflare AI credentials are not configured', provider);",
  "  return [{ json: { isValid: true, provider, url: 'https://api.cloudflare.com/client/v4/accounts/' + accountId + '/ai/run/' + model, headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' }, body: { messages, max_tokens: 5000, temperature: 0.6 } } }];",
  "}",
  "return [{ json: { isValid: true, provider, url: null, headers: {}, body: { messages, max_tokens: 5000, temperature: 0.6 } } }];"
].join('\n');

const pirFrom = "const modelId = input.modelId ?? source.modelId ?? body.modelId ?? $env.CLOUDFLARE_TEXT_MODEL ?? 'gemini-2.5-flash';";
const pirTo = "const modelId = input.modelId ?? input.textModel ?? input.text_model ?? source.modelId ?? source.textModel ?? source.text_model ?? body.modelId ?? body.textModel ?? body.text_model ?? $env.CLOUDFLARE_TEXT_MODEL ?? 'gemini-2.5-flash';";

patchNode('Build Request', buildIn, buildTo);
patchNode('Prepare Internal Request', pirFrom, pirTo);

fs.writeFileSync(file, JSON.stringify(data, null, 2) + '\n', 'utf8');
console.log('WROTE', file);