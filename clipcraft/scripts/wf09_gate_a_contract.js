const EXPECTED_JOB_ID = '11111111-1111-4111-8111-111111111111';
const EXPECTED_LEASE_TOKEN = '22222222-2222-4222-8222-222222222222';
const EXPECTED_RUN_TOKEN = '33333333-3333-4333-8333-333333333333';
const EXPECTED_STAGE_RUN_ID = '44444444-4444-4444-8444-444444444444';

const UNWRAP_CODE = "const input = $json.body ?? $json; return [{json: input, pairedItem: {item: 0}}];";
const BEGIN_CODE = `return [{json: {state: 'STARTED', stage_run_id: '${EXPECTED_STAGE_RUN_ID}', run_token: '${EXPECTED_RUN_TOKEN}', output: null}, pairedItem: {item: 0}}];`;
const RESERVE_CODE = "return [{json: {permitted: true, attempt_number: 1, remaining: 2}, pairedItem: {item: 0}}];";
const HEARTBEAT_CODE = "return [{json: {ok: true, cancel_requested: false}, pairedItem: {item: 0}}];";
const RENDER_CODE = "const input = $json; return [{json: {...input, success: true, videoUrl: '/probe/video.mp4', thumbnailUrl: '/probe/thumb.jpg'}, pairedItem: {item: 0}}];";
const BUILD_RESPONSE_CODE = "const input = $json; return [{json: {success: true, jobId: input.jobId, stage: input.stage, itemKey: input.itemKey, attemptNumber: input.attemptNumber, pipelineRevision: input.pipelineRevision, videoUrl: input.videoUrl, thumbnailUrl: input.thumbnailUrl, inputHash: input.inputHash, runToken: input.runToken}, pairedItem: {item: 0}}];";
const FINALIZE_CODE = `
const items = $input.all();
if (items.length !== 1) throw new Error('FINALIZATION_INPUT_COUNT_INVALID');
const input = items[0].json;
const hashNodeInputHash = $('Hash Stage Input').first().json.inputHash;
const runTokenMatches = input.runToken === '${EXPECTED_RUN_TOKEN}';
const inputHashMatches = typeof input.inputHash === 'string' && /^[0-9a-f]{64}$/.test(input.inputHash) && input.inputHash === hashNodeInputHash;
const identityMatches = input.jobId === '${EXPECTED_JOB_ID}' && input.stage === 'render' && input.itemKey === 'job' && input.attemptNumber === 1 && input.pipelineRevision === 1;
if (!runTokenMatches || !inputHashMatches || !identityMatches) throw new Error('WF09_GATE_A_FAILED');
return [{json: {gateA: true, finalizationBoundaryReached: true, runTokenMatches, inputHashMatches, identityMatches, jobId: input.jobId, stage: input.stage, itemKey: input.itemKey, attemptNumber: input.attemptNumber, pipelineRevision: input.pipelineRevision, videoUrl: input.videoUrl, thumbnailUrl: input.thumbnailUrl, inputHash: input.inputHash, runToken: input.runToken}, pairedItem: {item: 0}}];`;

module.exports = {
  EXPECTED_JOB_ID,
  EXPECTED_LEASE_TOKEN,
  EXPECTED_STAGE_RUN_ID,
  EXPECTED_RUN_TOKEN,
  UNWRAP_CODE,
  BEGIN_CODE,
  RESERVE_CODE,
  HEARTBEAT_CODE,
  RENDER_CODE,
  BUILD_RESPONSE_CODE,
  FINALIZE_CODE,
};
