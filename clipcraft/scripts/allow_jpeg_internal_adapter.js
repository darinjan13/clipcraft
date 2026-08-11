const fs = require('fs');

const files = [
  'workflows/18-ai-generate-image.json',
  'backups/n8n-recovery/20260801-231151Z/workflow-exports/reconciled/WF18-reconciled.json',
];

for (const file of files) {
  const workflow = JSON.parse(fs.readFileSync(file, 'utf8'));
  const node = workflow.nodes.find((item) => item.name === 'Adapt Internal Image Result');
  const before = node.parameters.jsCode;
  node.parameters.jsCode = before.replace(
    "if (input.mimeType && input.mimeType !== 'image/png') return failure('AI_RESPONSE_INVALID');",
    "if (input.mimeType && !['image/png', 'image/jpeg'].includes(input.mimeType)) return failure('AI_RESPONSE_INVALID');",
  );
  if (node.parameters.jsCode === before) throw new Error(`Adapter was not updated in ${file}`);
  fs.writeFileSync(file, `${JSON.stringify(workflow, null, 2)}\n`);
  console.log(file);
}
