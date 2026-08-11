const fs = require('fs');

const files = [
  'workflows/05-generate-scene-images.json',
  'workflows/18-ai-generate-image.json',
  'backups/n8n-recovery/20260801-231151Z/workflow-exports/reconciled/WF05-reconciled.json',
  'backups/n8n-recovery/20260801-231151Z/workflow-exports/reconciled/WF18-reconciled.json',
];

for (const file of files) {
  const workflow = JSON.parse(fs.readFileSync(file, 'utf8'));
  let replacements = 0;
  for (const node of workflow.nodes) {
    if (typeof node.parameters?.jsCode !== 'string') continue;
    const before = node.parameters.jsCode;
    node.parameters.jsCode = before.replace(
      "const { randomUUID } = require('crypto');",
      "const uuidV4 = () => { const bytes = new Uint8Array(16); for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256); bytes[6] = (bytes[6] & 0x0f) | 0x40; bytes[8] = (bytes[8] & 0x3f) | 0x80; return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('').replace(/^(........)(....)(....)(....)(............)$/, '$1-$2-$3-$4-$5'); };",
    ).replaceAll('randomUUID()', 'uuidV4()');
    if (node.parameters.jsCode !== before) replacements += 1;
  }
  if (replacements === 0) throw new Error(`No crypto import found in ${file}`);
  fs.writeFileSync(file, `${JSON.stringify(workflow, null, 2)}\n`);
  console.log(`${file}: ${replacements}`);
}
