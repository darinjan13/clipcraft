'use strict';

const {
  INTERNAL_IMAGE_PATH,
  MAX_IMAGE_RESPONSE_BYTES,
  SAFE_ERROR_CODES,
  SAFE_ERROR_MESSAGES,
  field,
  optionsField,
  safeError,
  sendSignedRequest,
  serializeRequest,
} = require('../../shared/clipcraftInternal');

const MAX_DECODED_IMAGE_BYTES = 4 * 1024 * 1024;
const PNG_SIGNATURE = Buffer.from('89504e470d0a1a0a', 'hex');
const JPEG_SIGNATURE = Buffer.from('ffd8ff', 'hex');

function buildNormalizedRequest(input) {
  const imageInput = {
    prompt: String(input.prompt),
    scene_id: String(input.sceneId),
  };
  if (input.sceneIndex !== undefined && input.sceneIndex !== null && input.sceneIndex !== '') {
    imageInput.scene_index = Number(input.sceneIndex);
  }
  for (const [source, target] of [
    ['width', 'width'],
    ['height', 'height'],
    ['seed', 'seed'],
    ['steps', 'steps'],
  ]) {
    if (input[source] !== undefined && input[source] !== null && input[source] !== '') {
      imageInput[target] = Number(input[source]);
    }
  }
  return {
    job_id: String(input.jobId),
    provider_id: String(input.providerId),
    model_id: String(input.modelId),
    credential_source: String(input.credentialSource),
    operation: 'image_generation',
    input: imageInput,
    routing_version: String(input.routingVersion),
    request_id: String(input.requestId),
  };
}

function normalizeImageResponse(statusCode, response) {
  if (statusCode >= 200 && statusCode < 300) {
    if (!response || response.status !== 'completed') {
      throw safeError('AI_RESPONSE_EMPTY', false, 'provider returned no image');
    }
    if (typeof response.image_base64 !== 'string' || !response.image_base64.trim()) {
      throw safeError('AI_RESPONSE_EMPTY', false, 'provider returned no image');
    }
    const image = decodeImage(response.image_base64);
    const { mimeType, extension } = detectImageType(image);
    return {
      success: true,
      status: 'completed',
      requestId: response.request_id,
      jobId: response.job_id,
      sceneId: response.scene_id,
      sceneIndex: typeof response.scene_index === 'number' ? response.scene_index : null,
      provider: response.provider_id,
      model: response.model_id,
      type: 'image',
      format: extension,
      mimeType,
      extension,
      fileName: `image.${extension}`,
      width: typeof response.width === 'number' ? response.width : null,
      height: typeof response.height === 'number' ? response.height : null,
      elapsedMs: typeof response.elapsed_ms === 'number' ? response.elapsed_ms : null,
      routingVersion: response.routing_version,
      imageBuffer: image,
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

function decodeImage(value) {
  const normalized = value.trim();
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(normalized) || normalized.length % 4 !== 0) {
    throw safeError('AI_RESPONSE_INVALID', false, 'provider response is invalid');
  }
  const padding = normalized.endsWith('==') ? 2 : normalized.endsWith('=') ? 1 : 0;
  const estimatedSize = (normalized.length * 3) / 4 - padding;
  if (estimatedSize > MAX_DECODED_IMAGE_BYTES) {
    throw safeError('AI_RESPONSE_INVALID', false, 'provider response is invalid');
  }
  const decoded = Buffer.from(normalized, 'base64');
  if (decoded.length === 0 || decoded.length > MAX_DECODED_IMAGE_BYTES) {
    throw safeError('AI_RESPONSE_INVALID', false, 'provider response is invalid');
  }
  if (decoded.toString('base64') !== normalized) {
    throw safeError('AI_RESPONSE_INVALID', false, 'provider response is invalid');
  }
  return decoded;
}

function detectImageType(image) {
  if (image.length >= PNG_SIGNATURE.length && image.subarray(0, PNG_SIGNATURE.length).equals(PNG_SIGNATURE)) {
    return { mimeType: 'image/png', extension: 'png' };
  }
  if (image.length >= JPEG_SIGNATURE.length && image.subarray(0, JPEG_SIGNATURE.length).equals(JPEG_SIGNATURE)) {
    return { mimeType: 'image/jpeg', extension: 'jpg' };
  }
  throw safeError('AI_RESPONSE_INVALID', false, 'provider response is invalid');
}

class ClipCraftImageExecute {
  constructor() {
    this.description = {
      displayName: 'ClipCraft Image Execute',
      name: 'clipCraftImageExecute',
      group: ['transform'],
      version: 1,
      description: 'Securely execute Cloudflare image generation through ClipCraft',
      defaults: { name: 'ClipCraft Image Execute' },
      inputs: ['main'],
      outputs: ['main'],
      credentials: [{ name: 'clipCraftInternalApi', required: true }],
      properties: [
        field('Job ID', 'jobId', 'string', ''),
        field('Scene ID', 'sceneId', 'string', ''),
        field('Scene Index', 'sceneIndex', 'number', null, { required: false, typeOptions: { minValue: 0 } }),
        field('Request ID', 'requestId', 'string', ''),
        optionsField('Provider', 'providerId', ['cloudflare'], 'cloudflare'),
        field('Model ID', 'modelId', 'string', '@cf/black-forest-labs/flux-1-schnell'),
        optionsField('Credential Source', 'credentialSource', ['environment', 'stored'], 'environment'),
        field('Routing Version', 'routingVersion', 'string', '1'),
        field('Prompt', 'prompt', 'string', '', { typeOptions: { rows: 8 } }),
        field('Width', 'width', 'number', 512, { required: false, typeOptions: { minValue: 1, maxValue: 2048 } }),
        field('Height', 'height', 'number', 512, { required: false, typeOptions: { minValue: 1, maxValue: 2048 } }),
        field('Seed', 'seed', 'number', null, { required: false, typeOptions: { minValue: 0, maxValue: 4294967295 } }),
        field('Steps', 'steps', 'number', null, { required: false, typeOptions: { minValue: 1, maxValue: 50 } }),
        field('Timeout (ms)', 'timeoutMs', 'number', 30000, { typeOptions: { minValue: 1000, maxValue: 120000 } }),
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
          'jobId', 'sceneId', 'requestId', 'providerId', 'modelId', 'credentialSource',
          'routingVersion', 'prompt', 'width', 'height', 'seed', 'steps', 'sceneIndex', 'timeoutMs',
        ]) {
          input[name] = this.getNodeParameter(name, index);
        }
        const rawBody = serializeRequest(buildNormalizedRequest(input));
        const result = await sendSignedRequest({
          baseUrl: credentials.baseUrl,
          signingSecret: credentials.signingSecret,
          rawBody,
          internalPath: INTERNAL_IMAGE_PATH,
          normalizeResponse: normalizeImageResponse,
          maxResponseBytes: MAX_IMAGE_RESPONSE_BYTES,
          timeoutMs: input.timeoutMs,
        });
        if (!result.success) {
          output.push({ json: result, pairedItem: { item: index } });
          continue;
        }
        const binary = await this.helpers.prepareBinaryData(result.imageBuffer, result.fileName, result.mimeType);
        output.push({
          json: {
            success: true,
            status: result.status,
            requestId: result.requestId,
            jobId: result.jobId,
            sceneId: result.sceneId,
            sceneIndex: result.sceneIndex,
            provider: result.provider,
            model: result.model,
            type: result.type,
            format: result.format,
            mimeType: result.mimeType,
            width: result.width,
            height: result.height,
            elapsedMs: result.elapsedMs,
            routingVersion: result.routingVersion,
            retryCount: 0,
            timestamp: new Date().toISOString(),
            retryable: false,
          },
          binary: { image: binary },
          pairedItem: { item: index },
        });
      } catch (error) {
        output.push({
          json: {
            success: false,
            status: 'failed',
            error: {
              code: SAFE_ERROR_CODES.has(error.code) ? error.code : 'AI_EXECUTION_FAILED',
              message: SAFE_ERROR_CODES.has(error.code) ? SAFE_ERROR_MESSAGES[error.code] : 'internal image execution failed',
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
  ClipCraftImageExecute,
  buildNormalizedRequest,
  decodeImage,
  detectImageType,
  normalizeImageResponse,
};
