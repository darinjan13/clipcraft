const fs = require('fs');

const files = [
  'workflows/05-generate-scene-images.json',
  'workflows/18-ai-generate-image.json',
  'backups/n8n-recovery/20260801-231151Z/workflow-exports/reconciled/WF05-reconciled.json',
  'backups/n8n-recovery/20260801-231151Z/workflow-exports/reconciled/WF18-reconciled.json',
];

for (const file of files) {
  const workflow = JSON.parse(fs.readFileSync(file, 'utf8'));
  let cryptoReplacements = 0;
  for (const node of workflow.nodes) {
    if (typeof node.parameters?.jsCode !== 'string') continue;
    const before = node.parameters.jsCode;
    node.parameters.jsCode = before.replaceAll(
      "const crypto = require('crypto');",
       "const crypto = require('crypto');",
    );
    if (node.parameters.jsCode !== before) cryptoReplacements += 1;
  }

  if (file.endsWith('18-ai-generate-image.json') || file.endsWith('WF18-reconciled.json')) {
    const normalize = workflow.nodes.find((node) => node.name === 'Normalize Response');
    const before = normalize.parameters.jsCode;
    normalize.parameters.jsCode = before
      .replace("const request = $('Build Request').first()?.json ?? {};", "const provider = input.providerResponse?.provider ?? input.provider ?? 'cloudflare';")
      .replaceAll("request.provider || 'cloudflare'", 'provider')
      .replaceAll('request.provider', 'provider');
    if (normalize.parameters.jsCode === before) throw new Error(`Normalize Response was not updated in ${file}`);
  }

  fs.writeFileSync(file, `${JSON.stringify(workflow, null, 2)}\n`);
  console.log(`${file}: crypto=${cryptoReplacements}`);
}
