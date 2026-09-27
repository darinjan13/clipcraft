'use strict';

const {
  INTERNAL_STOCK_PATH,
  SAFE_ERROR_CODES,
  SAFE_ERROR_MESSAGES,
  field,
  optionsField,
  safeError,
  sendSignedRequest,
  serializeRequest,
} = require('../../shared/clipcraftInternal');

function buildNormalizedRequest(input) {
  const stockInput = {
    query: String(input.query),
    media_type: String(input.mediaType || 'photo'),
    orientation: String(input.orientation || 'portrait'),
    scene_id: String(input.sceneId),
  };
  if (input.sceneIndex !== undefined && input.sceneIndex !== null && input.sceneIndex !== '') {
    stockInput.scene_index = Number(input.sceneIndex);
  }
  if (input.durationSeconds !== undefined && input.durationSeconds !== null && input.durationSeconds !== '') {
    stockInput.duration_seconds = Number(input.durationSeconds);
  }
  return {
    job_id: String(input.jobId),
    provider_id: String(input.provider || 'pexels'),
    credential_source: String(input.credentialSource || 'stored'),
    operation: 'stock_media',
    input: stockInput,
    routing_version: String(input.routingVersion),
    request_id: String(input.requestId),
  };
}

function normalizeStockResponse(statusCode, response, input = {}) {
  if (statusCode >= 200 && statusCode < 300) {
    if (!response || response.status !== 'completed') {
      throw safeError('AI_RESPONSE_EMPTY', false, 'provider returned no stock asset');
    }
    if (typeof response.local_path !== 'string' || !response.local_path.trim()) {
      throw safeError('AI_RESPONSE_EMPTY', false, 'provider returned no stock asset');
    }
    return {
      success: true,
      status: 'completed',
      requestId: response.request_id,
      jobId: response.job_id,
      sceneId: response.scene_id,
      sceneIndex: typeof response.scene_index === 'number' ? response.scene_index : null,
      provider: response.provider_id || input.provider || 'pexels',
      mediaType: response.media_type,
      type: 'stock',
      localPath: response.local_path,
      mimeType: response.mime_type || null,
      fileSize: typeof response.file_size === 'number' ? response.file_size : null,
      width: typeof response.width === 'number' ? response.width : null,
      height: typeof response.height === 'number' ? response.height : null,
      duration: typeof response.duration === 'number' ? response.duration : null,
      elapsedMs: typeof response.elapsed_ms === 'number' ? response.elapsed_ms : null,
      routingVersion: response.routing_version,
      retryable: false,
    };
  }
  const error = response && response.error && typeof response.error === 'object' ? response.error : {};
  const code = SAFE_ERROR_CODES.has(error.code) ? error.code : 'AI_EXECUTION_FAILED';
  return {
    success: false,
    status: 'failed',
    error: {
      code,
      message: SAFE_ERROR_MESSAGES[code],
      retryable: error.retryable === true,
    },
  };
}

class ClipCraftStockExecute {
  constructor() {
    this.description = {
      displayName: 'ClipCraft Stock Execute',
      name: 'clipCraftStockExecute',
      group: ['transform'],
      version: 1,
      description: 'Securely fetch stock media through ClipCraft',
      defaults: { name: 'ClipCraft Stock Execute' },
      inputs: ['main'],
      outputs: ['main'],
      credentials: [{ name: 'clipCraftInternalApi', required: true }],
      properties: [
        field('Job ID', 'jobId', 'string', ''),
        field('Scene ID', 'sceneId', 'string', ''),
        field('Scene Index', 'sceneIndex', 'number', null, { required: false, typeOptions: { minValue: 0 } }),
        field('Request ID', 'requestId', 'string', ''),
        optionsField('Provider', 'provider', ['pexels', 'pixabay'], 'pexels'),
        optionsField('Media Type', 'mediaType', ['photo', 'video'], 'photo'),
        optionsField('Orientation', 'orientation', ['landscape', 'portrait', 'square'], 'portrait'),
        field('Query', 'query', 'string', '', { typeOptions: { rows: 4 } }),
        field('Duration (seconds)', 'durationSeconds', 'number', null, { required: false, typeOptions: { minValue: 0 } }),
        optionsField('Credential Source', 'credentialSource', ['environment', 'stored'], 'stored'),
        field('Routing Version', 'routingVersion', 'string', '1'),
        field('Timeout (ms)', 'timeoutMs', 'number', 60000, { typeOptions: { minValue: 1000, maxValue: 130000 } }),
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
          'jobId', 'sceneId', 'requestId', 'provider', 'mediaType', 'orientation', 'query',
          'durationSeconds', 'sceneIndex', 'credentialSource', 'routingVersion', 'timeoutMs',
        ]) {
          input[name] = this.getNodeParameter(name, index);
        }
        const rawBody = serializeRequest(buildNormalizedRequest(input));
        const result = await sendSignedRequest({
          baseUrl: credentials.baseUrl,
          signingSecret: credentials.signingSecret,
          rawBody,
          internalPath: INTERNAL_STOCK_PATH,
          normalizeResponse: (statusCode, response) => normalizeStockResponse(statusCode, response, input),
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
              message: SAFE_ERROR_CODES.has(error.code) ? SAFE_ERROR_MESSAGES[error.code] : 'internal stock execution failed',
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
  ClipCraftStockExecute,
  buildNormalizedRequest,
  normalizeStockResponse,
};
