'use strict';

const {
  INTERNAL_TEXT_PATH,
  SAFE_ERROR_CODES,
  SAFE_ERROR_MESSAGES,
  buildInternalUrl: buildSharedInternalUrl,
  field,
  optionsField,
  safeError,
  sendSignedRequest: sendSharedSignedRequest,
  serializeRequest,
  signBody,
} = require('../../shared/clipcraftInternal');

function buildNormalizedRequest(input) {
  return {
    job_id: String(input.jobId),
    provider_id: String(input.providerId),
    model_id: String(input.modelId),
    credential_source: String(input.credentialSource),
    operation: 'text_generation',
    input: {
      prompt: String(input.prompt),
      ...(input.systemPrompt ? { system_prompt: String(input.systemPrompt) } : {}),
      temperature: Number(input.temperature),
      max_output_tokens: Number(input.maxOutputTokens),
      response_format: String(input.responseFormat),
    },
    routing_version: String(input.routingVersion),
    request_id: String(input.requestId),
  };
}

function normalizeInternalResponse(statusCode, response) {
  if (statusCode >= 200 && statusCode < 300) {
    if (!response || response.status !== 'completed' || typeof response.text !== 'string' || !response.text.trim()) {
      throw safeError('AI_RESPONSE_EMPTY', false, 'provider returned no text');
    }
    return {
      success: true,
      status: 'completed',
      requestId: response.request_id,
      jobId: response.job_id,
      provider: response.provider_id,
      model: response.model_id,
      content: response.text,
      text: response.text,
      finishReason: response.finish_reason ?? null,
      usage: isSafeUsage(response.usage) ? response.usage : {},
      elapsedMs: typeof response.elapsed_ms === 'number' ? response.elapsed_ms : null,
      routingVersion: response.routing_version,
      retryable: false,
    };
  }
  const error = response && response.error && typeof response.error === 'object' ? response.error : {};
  const requestInvalid = statusCode === 422 && error.message === 'request is invalid';
  const code = requestInvalid ? 'AI_REQUEST_INVALID' : (SAFE_ERROR_CODES.has(error.code) ? error.code : 'AI_EXECUTION_FAILED');
  return {
    success: false,
    status: 'failed',
    statusCode,
    source: requestInvalid ? 'internal_validation' : (statusCode === 422 ? 'provider' : 'internal'),
    error: {
      code,
      message: requestInvalid ? 'request is invalid' : SAFE_ERROR_MESSAGES[code],
      retryable: error.retryable === true,
    },
  };
}

function isSafeUsage(value) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.entries(value).every(([key, amount]) => typeof key === 'string' && Number.isInteger(amount));
}

function buildInternalUrl(baseUrl) {
  return buildSharedInternalUrl(baseUrl, INTERNAL_TEXT_PATH);
}

function sendSignedRequest(options) {
  return sendSharedSignedRequest({
    ...options,
    internalPath: INTERNAL_TEXT_PATH,
    normalizeResponse: normalizeInternalResponse,
  });
}

class ClipCraftTextExecute {
  constructor() {
    this.description = {
      displayName: 'ClipCraft Text Execute',
      name: 'clipCraftTextExecute',
      group: ['transform'],
      version: 1,
      description: 'Securely execute Gemini, Cloudflare, or NVIDIA text generation through ClipCraft',
      defaults: { name: 'ClipCraft Text Execute' },
      inputs: ['main'],
      outputs: ['main'],
      credentials: [{ name: 'clipCraftInternalApi', required: true }],
      properties: [
        field('Job ID', 'jobId', 'string', ''),
        field('Request ID', 'requestId', 'string', ''),
        optionsField('Provider', 'providerId', ['gemini', 'cloudflare', 'nvidia'], 'gemini'),
        field('Model ID', 'modelId', 'string', 'gemini-2.5-flash'),
        optionsField('Credential Source', 'credentialSource', ['environment', 'stored'], 'environment'),
        field('Routing Version', 'routingVersion', 'string', '1'),
        field('Prompt', 'prompt', 'string', '', { typeOptions: { rows: 8 } }),
        field('System Prompt', 'systemPrompt', 'string', '', { typeOptions: { rows: 4 } }),
        field('Temperature', 'temperature', 'number', 0.6, { typeOptions: { minValue: 0, maxValue: 2 } }),
        field('Max Output Tokens', 'maxOutputTokens', 'number', 8192, { typeOptions: { minValue: 1, maxValue: 65536 } }),
        optionsField('Response Format', 'responseFormat', ['text', 'json'], 'text'),
        field('Timeout (ms)', 'timeoutMs', 'number', 30000, { typeOptions: { minValue: 1000, maxValue: 130000 } }),
      ],
    };
  }

  async execute() {
    const items = this.getInputData();
    const output = [];
    const credentials = await this.getCredentials('clipCraftInternalApi');
    for (let index = 0; index < items.length; index += 1) {
      try {
        const input = {};
        for (const name of [
          'jobId', 'requestId', 'providerId', 'modelId', 'credentialSource', 'routingVersion',
          'prompt', 'systemPrompt', 'temperature', 'maxOutputTokens', 'responseFormat', 'timeoutMs',
        ]) {
          input[name] = this.getNodeParameter(name, index);
        }
        const rawBody = serializeRequest(buildNormalizedRequest(input));
        const result = await sendSignedRequest({
          baseUrl: credentials.baseUrl,
          signingSecret: credentials.signingSecret,
          rawBody,
          timeoutMs: input.timeoutMs,
        });
        output.push({ json: result, pairedItem: { item: index } });
      } catch (error) {
        output.push({
          json: {
            success: false,
            status: 'failed',
            error: {
              code: SAFE_ERROR_CODES.has(error.code) ? error.code : 'AI_EXECUTION_FAILED',
              message: SAFE_ERROR_CODES.has(error.code) ? error.message : 'internal text execution failed',
              retryable: error.retryable === true,
            },
          },
          pairedItem: { item: index },
        });
      }
    }
    return [output];
  }
}

module.exports = {
  ClipCraftTextExecute,
  buildInternalUrl,
  buildNormalizedRequest,
  normalizeInternalResponse,
  sendSignedRequest,
  serializeRequest,
  signBody,
};
