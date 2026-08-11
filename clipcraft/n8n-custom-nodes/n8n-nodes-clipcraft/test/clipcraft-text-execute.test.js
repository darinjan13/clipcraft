'use strict';

const assert = require('node:assert/strict');
const { createServer } = require('node:http');
const test = require('node:test');

const {
  buildInternalUrl,
  buildNormalizedRequest,
  ClipCraftTextExecute,
  normalizeInternalResponse,
  serializeRequest,
  signBody,
  sendSignedRequest,
} = require('../src/nodes/ClipCraftTextExecute/ClipCraftTextExecute.node.js');
const { ClipCraftInternalApi } = require('../src/credentials/ClipCraftInternalApi.credentials.js');

const input = {
  jobId: '11111111-1111-4111-8111-111111111111',
  requestId: '22222222-2222-4222-8222-222222222222',
  providerId: 'gemini',
  modelId: 'gemini-2.5-flash:variant/test',
  credentialSource: 'stored',
  routingVersion: '1',
  prompt: 'Return JSON: {"ok":true}',
  systemPrompt: 'Return only JSON.',
  temperature: 0.2,
  maxOutputTokens: 2048,
  responseFormat: 'json',
};

test('credential masks the signing secret', () => {
  const credential = new ClipCraftInternalApi();
  const secret = credential.properties.find((property) => property.name === 'signingSecret');

  assert.equal(credential.name, 'clipCraftInternalApi');
  assert.equal(credential.displayName, 'ClipCraft Internal API');
  assert.equal(secret.type, 'string');
  assert.equal(secret.typeOptions.password, true);
});

test('normalizes and serializes the request exactly once', () => {
  const normalized = buildNormalizedRequest(input);
  const rawBody = serializeRequest(normalized);

  assert.equal(rawBody, JSON.stringify(normalized));
  assert.equal(normalized.model_id, input.modelId);
  assert.equal(normalized.operation, 'text_generation');
  assert.deepEqual(JSON.parse(rawBody), normalized);
  assert.equal(rawBody.includes('signingSecret'), false);
});

test('creates the expected HMAC and changes it with signed inputs', () => {
  const body = serializeRequest(buildNormalizedRequest(input));
  const first = signBody('secret', '1700000000', 'nonce-a', body);
  const same = signBody('secret', '1700000000', 'nonce-a', body);

  assert.equal(first, same);
  assert.equal(first.length, 64);
  assert.notEqual(first, signBody('secret', '1700000001', 'nonce-a', body));
  assert.notEqual(first, signBody('secret', '1700000000', 'nonce-b', body));
  assert.notEqual(first, signBody('secret', '1700000000', 'nonce-a', `${body} `));
});

test('matches the backend HMAC golden vector', () => {
  assert.equal(
    signBody(
      'internal-signing-secret',
      '1700000000',
      'node-produced-nonce',
      '{"model_id":"gemini-2.5-flash:variant/test"}',
    ),
    'fd19feac8fd893cf623f6bb3ba1d5a5a8b7f4da6b8b40e6520970883c3d360e8',
  );
});

test('uses a fixed internal path and rejects unsafe base URLs', () => {
  assert.equal(
    buildInternalUrl('http://clipcraft-backend:8000'),
    'http://clipcraft-backend:8000/internal/ai/text/execute',
  );
  for (const value of [
    'file:///tmp/socket',
    'ftp://internal',
    'http://user:pass@internal',
    'http://internal/path',
    'http://internal?query=1',
    'http://internal/#fragment',
    'https://example.com',
    'http://8.8.8.8',
  ]) {
    assert.throws(() => buildInternalUrl(value), /invalid internal API base URL/);
  }
});

test('maps normalized successes and safe errors without transport details', () => {
  const success = normalizeInternalResponse(200, {
    request_id: input.requestId,
    job_id: input.jobId,
    provider_id: 'gemini',
    model_id: input.modelId,
    capability: 'text_generation',
    status: 'completed',
    text: '{"ok":true}',
    finish_reason: 'STOP',
    usage: { promptTokenCount: 2 },
    elapsed_ms: 12.5,
    routing_version: '1',
  });
  const failure = normalizeInternalResponse(429, {
    error: { code: 'AI_RATE_LIMITED', message: 'attacker-controlled provider body', retryable: true },
  });

  assert.equal(success.success, true);
  assert.equal(success.text, '{"ok":true}');
  assert.equal(success.provider, 'gemini');
  assert.deepEqual(failure, {
    success: false,
    status: 'failed',
    statusCode: 429,
    source: 'internal',
    error: { code: 'AI_RATE_LIMITED', message: 'provider rate limit reached', retryable: true },
  });
  assert.equal(JSON.stringify(failure).includes('headers'), false);
});

test('preserves safe internal validation status and source classification', () => {
  const failure = normalizeInternalResponse(422, {
    error: { code: 'AI_EXECUTION_FAILED', message: 'request is invalid', retryable: false },
  });

  assert.deepEqual(failure, {
    success: false,
    status: 'failed',
    statusCode: 422,
    source: 'internal_validation',
    error: { code: 'AI_REQUEST_INVALID', message: 'request is invalid', retryable: false },
  });
});

test('rejects an empty successful response', () => {
  assert.throws(
    () => normalizeInternalResponse(200, { status: 'completed', text: '' }),
    (error) => error.code === 'AI_RESPONSE_EMPTY' && !error.message.includes('secret'),
  );
});

test('signs and transmits the exact same bytes', async () => {
  let received;
  const server = createServer((request, response) => {
    const chunks = [];
    request.on('data', (chunk) => chunks.push(chunk));
    request.on('end', () => {
      received = {
        body: Buffer.concat(chunks),
        headers: request.headers,
        url: request.url,
      };
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({
        request_id: input.requestId,
        job_id: input.jobId,
        provider_id: input.providerId,
        model_id: input.modelId,
        capability: 'text_generation',
        status: 'completed',
        text: 'ok',
        usage: {},
        routing_version: '1',
      }));
    });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  const rawBody = serializeRequest(buildNormalizedRequest(input));

  try {
    const output = await sendSignedRequest({
      baseUrl: `http://127.0.0.1:${port}`,
      signingSecret: 'secret-value',
      rawBody,
      timestamp: '1700000000',
      nonce: 'nonce-fixed',
      timeoutMs: 1000,
    });

    assert.equal(output.text, 'ok');
    assert.equal(received.body.toString('utf8'), rawBody);
    assert.equal(received.url, '/internal/ai/text/execute');
    assert.equal(
      received.headers['x-clipcraft-signature'],
      signBody('secret-value', '1700000000', 'nonce-fixed', rawBody),
    );
    assert.equal(received.headers['content-length'], String(Buffer.byteLength(rawBody)));
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('executes the n8n node against a mocked internal endpoint', async () => {
  const server = createServer((request, response) => {
    request.resume();
    request.on('end', () => {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({
        request_id: input.requestId,
        job_id: input.jobId,
        provider_id: input.providerId,
        model_id: input.modelId,
        status: 'completed',
        text: 'node output',
        usage: {},
        routing_version: '1',
      }));
    });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const parameters = { ...input, timeoutMs: 1000 };
  const context = {
    getInputData: () => [{ json: {} }],
    getCredentials: async () => ({
      baseUrl: `http://127.0.0.1:${server.address().port}`,
      signingSecret: 'secret',
    }),
    getNodeParameter: (name) => parameters[name],
  };

  try {
    const [output] = await ClipCraftTextExecute.prototype.execute.call(context);
    assert.equal(output.length, 1);
    assert.equal(output[0].json.success, true);
    assert.equal(output[0].json.text, 'node output');
    assert.deepEqual(output[0].pairedItem, { item: 0 });
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('generates a unique nonce for every request', async () => {
  const nonces = [];
  const server = createServer((request, response) => {
    nonces.push(request.headers['x-clipcraft-nonce']);
    request.resume();
    request.on('end', () => {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({
        request_id: input.requestId,
        job_id: input.jobId,
        provider_id: input.providerId,
        model_id: input.modelId,
        capability: 'text_generation',
        status: 'completed',
        text: 'ok',
        usage: {},
        routing_version: '1',
      }));
    });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const baseUrl = `http://127.0.0.1:${server.address().port}`;
  const rawBody = serializeRequest(buildNormalizedRequest(input));

  try {
    await sendSignedRequest({ baseUrl, signingSecret: 'secret', rawBody });
    await sendSignedRequest({ baseUrl, signingSecret: 'secret', rawBody });
    assert.equal(nonces.length, 2);
    assert.notEqual(nonces[0], nonces[1]);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('normalizes malformed responses without exposing the body', async () => {
  const server = createServer((request, response) => {
    request.resume();
    request.on('end', () => response.end('provider-secret-body'));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));

  try {
    await assert.rejects(
      sendSignedRequest({
        baseUrl: `http://127.0.0.1:${server.address().port}`,
        signingSecret: 'secret',
        rawBody: serializeRequest(buildNormalizedRequest(input)),
      }),
      (error) => error.code === 'AI_RESPONSE_INVALID'
        && !error.message.includes('provider-secret-body'),
    );
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('normalizes transport timeouts', async () => {
  const server = createServer(() => {});
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));

  try {
    await assert.rejects(
      sendSignedRequest({
        baseUrl: `http://127.0.0.1:${server.address().port}`,
        signingSecret: 'secret',
        rawBody: serializeRequest(buildNormalizedRequest(input)),
        timeoutMs: 1000,
      }),
      (error) => error.code === 'AI_TIMEOUT' && error.retryable === true,
    );
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('rejects oversized requests before opening a connection', async () => {
  await assert.rejects(
    sendSignedRequest({
      baseUrl: 'http://127.0.0.1:1',
      signingSecret: 'secret',
      rawBody: 'x'.repeat(1024 * 1024 + 1),
    }),
    (error) => error.code === 'AI_EXECUTION_FAILED' && error.message === 'request is too large',
  );
});

test('returns a normalized failure without following redirects', async () => {
  let redirected = false;
  const destination = createServer(() => { redirected = true; });
  await new Promise((resolve) => destination.listen(0, '127.0.0.1', resolve));
  const source = createServer((request, response) => {
    request.resume();
    request.on('end', () => {
      response.statusCode = 302;
      response.setHeader('Location', `http://127.0.0.1:${destination.address().port}/secret`);
      response.end(JSON.stringify({ error: { code: 'AI_EXECUTION_FAILED', retryable: false } }));
    });
  });
  await new Promise((resolve) => source.listen(0, '127.0.0.1', resolve));

  try {
    const output = await sendSignedRequest({
      baseUrl: `http://127.0.0.1:${source.address().port}`,
      signingSecret: 'secret',
      rawBody: serializeRequest(buildNormalizedRequest(input)),
    });
    assert.equal(output.success, false);
    assert.equal(redirected, false);
  } finally {
    await new Promise((resolve) => source.close(resolve));
    await new Promise((resolve) => destination.close(resolve));
  }
});

test('rejects oversized responses without exposing response data', async () => {
  const server = createServer((request, response) => {
    request.resume();
    request.on('end', () => response.end('x'.repeat(4 * 1024 * 1024 + 1)));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));

  try {
    await assert.rejects(
      sendSignedRequest({
        baseUrl: `http://127.0.0.1:${server.address().port}`,
        signingSecret: 'secret',
        rawBody: serializeRequest(buildNormalizedRequest(input)),
      }),
      (error) => error.code === 'AI_RESPONSE_INVALID' && !error.message.includes('xxx'),
    );
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
