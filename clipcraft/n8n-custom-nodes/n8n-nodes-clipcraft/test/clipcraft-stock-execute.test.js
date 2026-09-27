'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const {
  ClipCraftStockExecute,
  buildNormalizedRequest,
  normalizeStockResponse,
} = require('../src/nodes/ClipCraftStockExecute/ClipCraftStockExecute.node.js');
const { ClipCraftInternalApi } = require('../src/credentials/ClipCraftInternalApi.credentials.js');

const input = {
  jobId: '11111111-1111-4111-8111-111111111111',
  sceneId: 'scene-1',
  sceneIndex: 3,
  requestId: '22222222-2222-4222-8222-222222222222',
  providerId: 'pexels',
  mediaType: 'photo',
  orientation: 'portrait',
  query: 'rainy window',
  credentialSource: 'stored',
  routingVersion: '1',
  durationSeconds: 5,
};

test('reuses the existing encrypted credential type', () => {
  const credential = new ClipCraftInternalApi();
  const node = new ClipCraftStockExecute();
  assert.equal(credential.name, 'clipCraftInternalApi');
  assert.deepEqual(node.description.credentials, [{ name: 'clipCraftInternalApi', required: true }]);
});

test('builds the normalized stock request', () => {
  const normalized = buildNormalizedRequest(input);

  assert.deepEqual(normalized, {
    job_id: input.jobId,
    provider_id: 'pexels',
    credential_source: 'stored',
    operation: 'stock_media',
    input: {
      query: input.query,
      media_type: input.mediaType,
      orientation: input.orientation,
      scene_id: input.sceneId,
      scene_index: input.sceneIndex,
      duration_seconds: input.durationSeconds,
    },
    routing_version: input.routingVersion,
    request_id: input.requestId,
  });
});

test('maps a completed stock response to file metadata', () => {
  const result = normalizeStockResponse(200, {
    request_id: input.requestId,
    job_id: input.jobId,
    scene_id: input.sceneId,
    scene_index: input.sceneIndex,
    media_type: 'photo',
    capability: 'stock_media',
    status: 'completed',
    local_path: '/data/jobs/job/scene-03.jpg',
    mime_type: 'image/jpeg',
    file_size: 12345,
    routing_version: '1',
  });

  assert.equal(result.success, true);
  assert.equal(result.localPath, '/data/jobs/job/scene-03.jpg');
  assert.equal(result.mimeType, 'image/jpeg');
  assert.equal(result.provider, 'pexels');
  assert.equal(result.retryable, false);
});

test('passes the provider through to the normalized request', () => {
  const normalized = buildNormalizedRequest({ ...input, provider: 'pixabay' });

  assert.equal(normalized.provider_id, 'pixabay');
});

test('defaults the provider to pexels for backward compatibility', () => {
  const { provider, ...rest } = input;
  const normalized = buildNormalizedRequest(rest);

  assert.equal(normalized.provider_id, 'pexels');
});

test('surfaces the response provider instead of assuming pexels', () => {
  const result = normalizeStockResponse(200, {
    request_id: input.requestId,
    job_id: input.jobId,
    provider_id: 'pixabay',
    scene_id: input.sceneId,
    scene_index: input.sceneIndex,
    media_type: 'photo',
    capability: 'stock_media',
    status: 'completed',
    local_path: '/data/jobs/job/scene-03.jpg',
    mime_type: 'image/jpeg',
    file_size: 12345,
    routing_version: '1',
  });

  assert.equal(result.provider, 'pixabay');
});

test('maps a provider failure without leaking details', () => {
  const result = normalizeStockResponse(429, {
    error: { code: 'AI_RATE_LIMITED', message: 'custom text', retryable: true },
  });

  assert.equal(result.success, false);
  assert.equal(result.error.code, 'AI_RATE_LIMITED');
  assert.equal(result.error.retryable, true);
});
