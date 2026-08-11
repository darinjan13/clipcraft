'use strict';

const assert = require('node:assert/strict');
const { createServer } = require('node:http');
const test = require('node:test');

const {
  ClipCraftImageExecute,
  buildNormalizedRequest,
  normalizeImageResponse,
} = require('../src/nodes/ClipCraftImageExecute/ClipCraftImageExecute.node.js');
const { serializeRequest, signBody } = require('../src/shared/clipcraftInternal.js');
const { ClipCraftInternalApi } = require('../src/credentials/ClipCraftInternalApi.credentials.js');

const input = {
  jobId: '11111111-1111-4111-8111-111111111111',
  sceneId: 'scene-1',
  sceneIndex: 3,
  requestId: '22222222-2222-4222-8222-222222222222',
  providerId: 'cloudflare',
  modelId: '@cf/black-forest-labs/flux-1-schnell',
  credentialSource: 'environment',
  routingVersion: '1',
  prompt: 'A cinematic cat',
  width: 512,
  height: 512,
  seed: 7,
  steps: 4,
};

const PNG = Buffer.from('89504e470d0a1a0a00000000', 'hex');
const JPEG = Buffer.from('ffd8ffe000104a4649460001ffd9', 'hex');

function responseBody(image, overrides = {}) {
  return {
    request_id: input.requestId,
    job_id: input.jobId,
    provider_id: input.providerId,
    model_id: input.modelId,
    capability: 'image_generation',
    status: 'completed',
    image_base64: image.toString('base64'),
    format: 'png',
    width: input.width,
    height: input.height,
    scene_id: input.sceneId,
    scene_index: input.sceneIndex,
    elapsed_ms: 12.5,
    routing_version: input.routingVersion,
    ...overrides,
  };
}

function nodeContext(parameters, credentials = {}) {
  return {
    getInputData: () => [{ json: {} }],
    getCredentials: async () => ({
      baseUrl: credentials.baseUrl,
      signingSecret: credentials.signingSecret || 'secret',
    }),
    getNodeParameter: (name) => parameters[name],
    helpers: {
      prepareBinaryData: async (data, fileName, mimeType) => ({
        data: data.toString('base64'),
        fileName,
        mimeType,
      }),
    },
  };
}

async function withServer(handler, callback) {
  const server = createServer(handler);
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  try {
    return await callback(`http://127.0.0.1:${server.address().port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

test('reuses the existing encrypted credential type', () => {
  const credential = new ClipCraftInternalApi();
  const node = new ClipCraftImageExecute();
  assert.equal(credential.name, 'clipCraftInternalApi');
  assert.deepEqual(node.description.credentials, [{ name: 'clipCraftInternalApi', required: true }]);
});

test('builds the normalized image request without credentials or prompt aliases', () => {
  const normalized = buildNormalizedRequest(input);

  assert.deepEqual(normalized, {
    job_id: input.jobId,
    provider_id: input.providerId,
    model_id: input.modelId,
    credential_source: input.credentialSource,
    operation: 'image_generation',
    input: {
      prompt: input.prompt,
      scene_id: input.sceneId,
      scene_index: input.sceneIndex,
      width: input.width,
      height: input.height,
      seed: input.seed,
      steps: input.steps,
    },
    routing_version: input.routingVersion,
    request_id: input.requestId,
  });
  assert.equal(serializeRequest(normalized).includes('signingSecret'), false);
});

test('shares deterministic HMAC signing with the text node contract', () => {
  const body = serializeRequest(buildNormalizedRequest(input));
  const first = signBody('secret', '1700000000', 'nonce-a', body);
  assert.equal(first, signBody('secret', '1700000000', 'nonce-a', body));
  assert.notEqual(first, signBody('secret', '1700000001', 'nonce-a', body));
  assert.equal(first.length, 64);
});

test('normalizes PNG into metadata plus n8n binary input', () => {
  const result = normalizeImageResponse(200, responseBody(PNG));

  assert.equal(result.success, true);
  assert.equal(result.mimeType, 'image/png');
  assert.equal(result.width, 512);
  assert.equal(result.height, 512);
  assert.equal(result.imageBuffer.equals(PNG), true);
  assert.equal(JSON.stringify(result).includes(PNG.toString('base64')), false);
});

test('normalizes JPEG and preserves its MIME type', () => {
  const result = normalizeImageResponse(200, responseBody(JPEG, { format: 'jpeg' }));

  assert.equal(result.mimeType, 'image/jpeg');
  assert.equal(result.imageBuffer.equals(JPEG), true);
});

test('rejects invalid base64, empty images, unsupported MIME, and oversized images', () => {
  assert.throws(() => normalizeImageResponse(200, responseBody(PNG, { image_base64: 'not-base64!' })), (error) => error.code === 'AI_RESPONSE_INVALID');
  assert.throws(() => normalizeImageResponse(200, responseBody(PNG, { image_base64: '' })), (error) => error.code === 'AI_RESPONSE_EMPTY');
  assert.throws(() => normalizeImageResponse(200, responseBody(Buffer.from('plain text'))), (error) => error.code === 'AI_RESPONSE_INVALID');
  const oversized = Buffer.concat([Buffer.from('89504e470d0a1a0a', 'hex'), Buffer.alloc(4 * 1024 * 1024)]);
  assert.throws(() => normalizeImageResponse(200, responseBody(oversized)), (error) => error.code === 'AI_RESPONSE_INVALID');
});

test('normalizes quota, invalid credential, timeout, and replay errors without provider bodies', () => {
  for (const [statusCode, code] of [[402, 'AI_QUOTA_EXCEEDED'], [401, 'AI_CREDENTIAL_INVALID'], [504, 'AI_TIMEOUT'], [401, 'INTERNAL_REQUEST_REPLAYED']]) {
    const result = normalizeImageResponse(statusCode, { error: { code, message: 'provider secret body', retryable: true } });
    assert.equal(result.success, false);
    assert.equal(result.error.code, code);
    assert.equal(result.error.message.includes('provider secret body'), false);
  }
});

test('executes against a normalized endpoint and returns BinaryData metadata', async () => {
  await withServer((request, response) => {
    const chunks = [];
    request.on('data', (chunk) => chunks.push(chunk));
    request.on('end', () => {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify(responseBody(PNG)));
    });
  }, async (baseUrl) => {
    const parameters = { ...input, timeoutMs: 1000 };
    const [output] = await ClipCraftImageExecute.prototype.execute.call(nodeContext(parameters, { baseUrl }));
    assert.equal(output.length, 1);
    assert.equal(output[0].json.success, true);
    assert.equal(output[0].json.provider, 'cloudflare');
    assert.equal(output[0].json.model, input.modelId);
    assert.equal(output[0].json.mimeType, 'image/png');
    assert.equal(output[0].json.width, input.width);
    assert.equal(output[0].json.height, input.height);
    assert.equal(output[0].json.sceneIndex, input.sceneIndex);
    assert.equal(output[0].json.type, 'image');
    assert.equal(output[0].json.format, 'png');
    assert.equal(output[0].json.retryCount, 0);
    assert.equal(typeof output[0].json.timestamp, 'string');
    assert.equal(output[0].json.routingVersion, '1');
    assert.equal(output[0].binary.image.mimeType, 'image/png');
    assert.equal(Buffer.from(output[0].binary.image.data, 'base64').equals(PNG), true);
    assert.equal(JSON.stringify(output[0].json).includes(input.prompt), false);
    assert.equal(JSON.stringify(output[0].json).includes(PNG.toString('base64')), false);
    assert.deepEqual(output[0].pairedItem, { item: 0 });
  });
});

test('uses exact signed request bytes and private image path', async () => {
  await withServer((request, response) => {
    const chunks = [];
    request.on('data', (chunk) => chunks.push(chunk));
    request.on('end', () => {
      const body = Buffer.concat(chunks).toString('utf8');
      assert.equal(request.url, '/internal/ai/image/execute');
      assert.equal(request.headers['x-clipcraft-signature'], signBody('secret', request.headers['x-clipcraft-timestamp'], request.headers['x-clipcraft-nonce'], body));
      response.end(JSON.stringify(responseBody(PNG)));
    });
  }, async (baseUrl) => {
    const parameters = { ...input, timeoutMs: 1000 };
    await ClipCraftImageExecute.prototype.execute.call(nodeContext(parameters, { baseUrl }));
  });
});

test('normalizes timeout and never exposes secrets, prompts, or image bytes', async () => {
  await withServer(() => {}, async (baseUrl) => {
    const parameters = { ...input, timeoutMs: 1000 };
    const [output] = await ClipCraftImageExecute.prototype.execute.call(nodeContext(parameters, { baseUrl, signingSecret: 'top-secret' }));
    assert.equal(output[0].json.success, false);
    assert.equal(output[0].json.error.code, 'AI_TIMEOUT');
    const serialized = JSON.stringify(output[0]);
    assert.equal(serialized.includes('top-secret'), false);
    assert.equal(serialized.includes(input.prompt), false);
    assert.equal(serialized.includes(PNG.toString('base64')), false);
  });
});

test('returns normalized provider failures without attempting binary conversion', async () => {
  await withServer((request, response) => {
    request.resume();
    request.on('end', () => {
      response.statusCode = 402;
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ error: { code: 'AI_QUOTA_EXCEEDED', message: 'provider secret body', retryable: false } }));
    });
  }, async (baseUrl) => {
    const parameters = { ...input, timeoutMs: 1000 };
    const [output] = await ClipCraftImageExecute.prototype.execute.call(nodeContext(parameters, { baseUrl }));
    assert.equal(output[0].json.success, false);
    assert.equal(output[0].json.error.code, 'AI_QUOTA_EXCEEDED');
    assert.equal(output[0].json.error.message, 'provider quota was exceeded');
    assert.equal(output[0].binary, undefined);
  });
});
