'use strict';

class ClipCraftInternalApi {
  constructor() {
    this.name = 'clipCraftInternalApi';
    this.displayName = 'ClipCraft Internal API';
    this.documentationUrl = 'https://docs.n8n.io/integrations/creating-nodes/';
    this.properties = [
      {
        displayName: 'Base URL',
        name: 'baseUrl',
        type: 'string',
        default: 'http://clipcraft-backend:8000',
        required: true,
      },
      {
        displayName: 'HMAC Signing Secret',
        name: 'signingSecret',
        type: 'string',
        typeOptions: { password: true },
        default: '',
        required: true,
      },
    ];
  }
}

module.exports = { ClipCraftInternalApi };
