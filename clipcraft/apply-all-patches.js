const fs = require('fs');

// Patch 1: findSubworkflowStart to accept workflowTrigger
let utilsPath = '/usr/local/lib/node_modules/n8n/dist/utils.js';
let utils = fs.readFileSync(utilsPath, 'utf8');
utils = utils.replace(
  "const executeWorkflowTriggerNode = nodes.find((node) => node.type === 'n8n-nodes-base.executeWorkflowTrigger');",
  "const executeWorkflowTriggerNode = nodes.find((node) => node.type === 'n8n-nodes-base.executeWorkflowTrigger' || node.type === 'n8n-nodes-base.workflowTrigger');"
);
fs.writeFileSync(utilsPath, utils);
console.log('OK: patched findSubworkflowStart');

// Patch 2: Add debug logging to EWTrigger execute()
let ewtPath = '/usr/local/lib/node_modules/n8n/node_modules/n8n-nodes-base/dist/nodes/ExecuteWorkflow/ExecuteWorkflowTrigger/ExecuteWorkflowTrigger.node.js';
let ewt = fs.readFileSync(ewtPath, 'utf8');
ewt = ewt.replace('async execute() {', 'async execute() { console.log("DBG:EWT execute()");');
ewt = ewt.replace(
  "return [inputData];",
  "console.log('DBG:EWT returning', inputData.length, 'items with', Object.keys(inputData[0]||{}).length, 'keys each'); return [inputData];"
);
fs.writeFileSync(ewtPath, ewt);
console.log('OK: patched EWTrigger');

// Patch 3: Add debug logging to engine connection iteration
let enginePath = '/usr/local/lib/node_modules/n8n/node_modules/n8n-core/dist/execution-engine/workflow-execute.js';
let engine = fs.readFileSync(enginePath, 'utf8');
// Before connection iteration, log what we're checking
engine = engine.replace(
  "if (Object.hasOwn(workflow.connectionsBySourceNode, executionNode.name)) {",
  "console.log('DBG:Checking connections for', executionNode.name, '- hasConns:', Object.hasOwn(workflow.connectionsBySourceNode, executionNode.name), '- keys:', Object.keys(workflow.connectionsBySourceNode).join(',')); if (Object.hasOwn(workflow.connectionsBySourceNode, executionNode.name)) {"
);
// Log addNodeToBeExecuted calls
engine = engine.replace(
  "this.addNodeToBeExecuted(workflow, connectionData, parseInt(outputIndex, 10), executionNode.name, nodeSuccessData, runIndex);",
  "console.log('DBG:addNodeToBeExecuted', connectionData.node, 'outputIndex:', outputIndex, 'dataLen:', nodeSuccessData?.[outputIndex]?.length); this.addNodeToBeExecuted(workflow, connectionData, parseInt(outputIndex, 10), executionNode.name, nodeSuccessData, runIndex);"
);
// Log when loop ends
engine = engine.replace(
  "if (this.runExecutionData.executionData.nodeExecutionStack.length === 0 &&",
  "console.log('DBG:Stack empty?', this.runExecutionData.executionData.nodeExecutionStack.length, 'waiting:', Object.keys(this.runExecutionData.executionData.waitingExecution || {}).length); if (this.runExecutionData.executionData.nodeExecutionStack.length === 0 &&"
);
fs.writeFileSync(enginePath, engine);
console.log('OK: patched engine');
