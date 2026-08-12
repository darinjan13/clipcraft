'use strict';

const { createHmac, randomUUID } = require('node:crypto');
const { lookup } = require('node:dns').promises;
const http = require('node:http');
const https = require('node:https');
const { isIP } = require('node:net');

const INTERNAL_TEXT_PATH = '/internal/ai/text/execute';
const INTERNAL_IMAGE_PATH = '/internal/ai/image/execute';
const MAX_REQUEST_BYTES = 1024 * 1024;
const MAX_RESPONSE_BYTES = 4 * 1024 * 1024;
const MAX_IMAGE_RESPONSE_BYTES = 8 * 1024 * 1024;
const SAFE_ERROR_CODES = new Set([
  'INTERNAL_AUTH_REQUIRED',
  'INTERNAL_SIGNATURE_INVALID',
  'INTERNAL_REQUEST_REPLAYED',
  'AI_PROVIDER_UNKNOWN',
  'AI_PROVIDER_DISABLED',
  'AI_PROVIDER_UNAVAILABLE',
  'AI_MODEL_UNKNOWN',
  'AI_MODEL_NOT_ALLOWED',
  'AI_CREDENTIAL_MISSING',
  'AI_CREDENTIAL_INVALID',
  'AI_PERMISSION_DENIED',
  'AI_QUOTA_EXCEEDED',
  'AI_RATE_LIMITED',
  'AI_TIMEOUT',
  'AI_RESPONSE_BLOCKED',
  'AI_RESPONSE_EMPTY',
  'AI_RESPONSE_INVALID',
  'AI_REQUEST_INVALID',
  'AI_EXECUTION_FAILED',
]);
const SAFE_ERROR_MESSAGES = {
  INTERNAL_AUTH_REQUIRED: 'internal authentication required',
  INTERNAL_SIGNATURE_INVALID: 'internal signature is invalid',
  INTERNAL_REQUEST_REPLAYED: 'internal request was replayed',
  AI_PROVIDER_UNKNOWN: 'provider is unknown',
  AI_PROVIDER_DISABLED: 'provider is disabled',
  AI_PROVIDER_UNAVAILABLE: 'provider is unavailable',
  AI_MODEL_UNKNOWN: 'model is unknown',
  AI_MODEL_NOT_ALLOWED: 'model is not allowed',
  AI_CREDENTIAL_MISSING: 'provider credential is unavailable',
  AI_CREDENTIAL_INVALID: 'provider credential is invalid',
  AI_PERMISSION_DENIED: 'provider permission was denied',
  AI_QUOTA_EXCEEDED: 'provider quota was exceeded',
  AI_RATE_LIMITED: 'provider rate limit reached',
  AI_TIMEOUT: 'provider request timed out',
  AI_RESPONSE_BLOCKED: 'provider response was blocked',
  AI_RESPONSE_EMPTY: 'provider returned no text',
  AI_RESPONSE_INVALID: 'provider response is invalid',
  AI_REQUEST_INVALID: 'request is invalid',
  AI_EXECUTION_FAILED: 'provider execution failed',
};

function serializeRequest(request) {
  const rawBody = JSON.stringify(request);
  if (Buffer.byteLength(rawBody, 'utf8') > MAX_REQUEST_BYTES) {
    throw safeError('AI_EXECUTION_FAILED', false, 'request is too large');
  }
  return rawBody;
}

function signBody(signingSecret, timestamp, nonce, rawBody) {
  if (typeof signingSecret !== 'string' || signingSecret.length === 0) {
    throw safeError('INTERNAL_AUTH_REQUIRED', false, 'internal authentication required');
  }
  return createHmac('sha256', signingSecret)
    .update(`${timestamp}\n${nonce}\n`, 'utf8')
    .update(Buffer.from(rawBody, 'utf8'))
    .digest('hex');
}

function buildInternalUrl(baseUrl, internalPath = INTERNAL_TEXT_PATH) {
  let parsed;
  try {
    parsed = new URL(String(baseUrl));
  } catch {
    throw new Error('invalid internal API base URL');
  }
  if (!['http:', 'https:'].includes(parsed.protocol)
    || parsed.username
    || parsed.password
    || parsed.search
    || parsed.hash
    || !['', '/'].includes(parsed.pathname)
    || !isPrivateHostname(parsed.hostname)) {
    throw new Error('invalid internal API base URL');
  }
  parsed.pathname = internalPath;
  return parsed.toString().replace(/\/$/, '');
}

function isPrivateHostname(hostname) {
  const value = hostname.toLowerCase().replace(/^\[|\]$/g, '');
  if (value === 'localhost' || value === '::1' || value === 'host.docker.internal') return true;
  if (!value.includes('.') || value.endsWith('.internal') || value.endsWith('.local')) return true;
  const parts = value.split('.').map(Number);
  if (parts.length === 4 && parts.every((part) => Number.isInteger(part) && part >= 0 && part <= 255)) {
    return parts[0] === 10
      || parts[0] === 127
      || (parts[0] === 192 && parts[1] === 168)
      || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31);
  }
  return value.startsWith('fc') || value.startsWith('fd') || value.startsWith('fe80:');
}

function isPrivateAddress(address) {
  const value = address.toLowerCase().replace(/^::ffff:/, '');
  if (!isIP(value)) return false;
  if (value === '::1') return true;
  if (value.includes(':')) return value.startsWith('fc') || value.startsWith('fd') || value.startsWith('fe80:');
  const parts = value.split('.').map(Number);
  return parts[0] === 10
    || parts[0] === 127
    || (parts[0] === 192 && parts[1] === 168)
    || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31);
}

async function resolvePrivateAddress(hostname, timeoutMs) {
  const bareHostname = hostname.replace(/^\[|\]$/g, '');
  if (isIP(bareHostname)) {
    if (!isPrivateAddress(bareHostname)) throw new Error('invalid internal API base URL');
    return { address: bareHostname, family: isIP(bareHostname) };
  }
  let addresses;
  let timer;
  try {
    addresses = await Promise.race([
      lookup(bareHostname, { all: true, verbatim: true }),
      new Promise((_, reject) => {
        timer = setTimeout(
          () => reject(safeError('AI_TIMEOUT', true, 'internal API timed out')),
          timeoutMs,
        );
        timer.unref();
      }),
    ]);
  } catch (error) {
    if (timer) clearTimeout(timer);
    if (SAFE_ERROR_CODES.has(error.code)) throw error;
    throw safeError('AI_PROVIDER_UNAVAILABLE', true, 'internal API is unavailable');
  }
  if (timer) clearTimeout(timer);
  if (!addresses.length || addresses.some(({ address }) => !isPrivateAddress(address))) {
    throw new Error('invalid internal API base URL');
  }
  return addresses[0];
}

function safeError(code, retryable, message) {
  const error = new Error(message);
  error.code = code;
  error.retryable = retryable;
  return error;
}

async function sendSignedRequest({
  baseUrl,
  signingSecret,
  rawBody,
  internalPath = INTERNAL_TEXT_PATH,
  normalizeResponse,
  maxResponseBytes = MAX_RESPONSE_BYTES,
  timestamp = String(Math.floor(Date.now() / 1000)),
  nonce = randomUUID(),
  timeoutMs = 30_000,
}) {
  const startedAt = Date.now();
  const boundedTimeout = Math.max(1000, Math.min(Number(timeoutMs) || 30_000, 130_000));
  const url = new URL(buildInternalUrl(baseUrl, internalPath));
  const resolvedAddress = await resolvePrivateAddress(url.hostname, boundedTimeout);
  const body = Buffer.from(rawBody, 'utf8');
  if (body.length > MAX_REQUEST_BYTES) {
    throw safeError('AI_EXECUTION_FAILED', false, 'request is too large');
  }
  const signature = signBody(signingSecret, timestamp, nonce, rawBody);
  const client = url.protocol === 'https:' ? https : http;
  const remainingTimeout = boundedTimeout - (Date.now() - startedAt);
  if (remainingTimeout <= 0) {
    throw safeError('AI_TIMEOUT', true, 'internal API timed out');
  }

  return new Promise((resolve, reject) => {
    let settled = false;
    let request;
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(deadline);
      callback(value);
    };
    const deadline = setTimeout(() => {
      request.destroy(safeError('AI_TIMEOUT', true, 'internal API timed out'));
    }, remainingTimeout);
    deadline.unref();
    request = client.request({
      protocol: url.protocol,
      hostname: url.hostname,
      lookup: (_hostname, _options, callback) => callback(
        null,
        resolvedAddress.address,
        resolvedAddress.family,
      ),
      port: url.port || undefined,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': String(body.length),
        'X-ClipCraft-Timestamp': timestamp,
        'X-ClipCraft-Nonce': nonce,
        'X-ClipCraft-Signature': signature,
      },
      timeout: remainingTimeout,
    }, (response) => {
      const chunks = [];
      let size = 0;
      response.on('data', (chunk) => {
        size += chunk.length;
        if (size > maxResponseBytes) {
          response.destroy(safeError('AI_RESPONSE_INVALID', false, 'internal response is too large'));
          return;
        }
        chunks.push(chunk);
      });
      response.on('end', () => {
        let parsed;
        try {
          parsed = JSON.parse(Buffer.concat(chunks).toString('utf8'));
        } catch {
          finish(reject, safeError('AI_RESPONSE_INVALID', false, 'internal response is invalid'));
          return;
        }
        try {
          finish(resolve, normalizeResponse(response.statusCode || 500, parsed));
        } catch (error) {
          finish(reject, error);
        }
      });
      response.on('error', (error) => finish(
        reject,
        SAFE_ERROR_CODES.has(error.code)
          ? error
          : safeError('AI_PROVIDER_UNAVAILABLE', true, 'internal API is unavailable'),
      ));
    });
    request.on('timeout', () => request.destroy(safeError('AI_TIMEOUT', true, 'internal API timed out')));
    request.on('error', (error) => {
      if (SAFE_ERROR_CODES.has(error.code)) {
        finish(reject, error);
      } else {
        finish(reject, safeError('AI_PROVIDER_UNAVAILABLE', true, 'internal API is unavailable'));
      }
    });
    request.end(body);
  });
}

function field(displayName, name, type, defaultValue, extra = {}) {
  return { displayName, name, type, default: defaultValue, required: name !== 'systemPrompt', ...extra };
}

function optionsField(displayName, name, values, defaultValue) {
  return {
    displayName,
    name,
    type: 'options',
    default: defaultValue,
    required: true,
    options: values.map((value) => ({ name: value, value })),
  };
}

module.exports = {
  INTERNAL_TEXT_PATH,
  INTERNAL_IMAGE_PATH,
  MAX_REQUEST_BYTES,
  MAX_RESPONSE_BYTES,
  MAX_IMAGE_RESPONSE_BYTES,
  SAFE_ERROR_CODES,
  SAFE_ERROR_MESSAGES,
  buildInternalUrl,
  field,
  isPrivateAddress,
  isPrivateHostname,
  optionsField,
  resolvePrivateAddress,
  safeError,
  sendSignedRequest,
  serializeRequest,
  signBody,
};
