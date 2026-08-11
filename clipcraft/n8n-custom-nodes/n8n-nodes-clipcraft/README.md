# n8n-nodes-clipcraft

Private ClipCraft n8n nodes for n8n 2.29.7 and Node.js 22.22 or newer.

## Included types

- Node: `ClipCraft Text Execute`
- Node: `ClipCraft Image Execute`
- Credential: `ClipCraft Internal API`

The credential stores only the private backend base URL and HMAC signing secret. Provider credentials remain in FastAPI.

## Build

```sh
npm test
npm run build
npm pack
```

The nodes serialize each normalized request once, sign those exact UTF-8 bytes, and send the same bytes to their private image or text endpoint using Node's built-in HTTP client. The image node returns n8n BinaryData after validating PNG/JPEG magic bytes. Neither node exposes the signing secret, signature, nonce, request headers, or raw response.

## Installation

The Docker image copies the built package to `/opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft` and sets `N8N_CUSTOM_EXTENSIONS=/opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft/dist`. This location is outside `/root/.n8n`, so the persistent n8n data volume does not hide the package.

Set and retain a strong `N8N_ENCRYPTION_KEY` before creating credentials. In n8n, create a `ClipCraft Internal API` credential, set the private FastAPI base URL reachable from the n8n network (for example, `http://clipcraft-backend:8000`), and enter the same HMAC secret configured as `N8N_INTERNAL_SIGNING_SECRET` in FastAPI. n8n stores both fields encrypted; the environment examples do not create this credential automatically.

The default `clipcraft-backend` hostname assumes the backend is attached to the n8n Docker network with that alias. Use the deployment's private service name when its topology differs.

WF17 is intentionally unchanged in Checkpoint 5A. A later approved checkpoint must add the node to WF17 and reference an encrypted `ClipCraft Internal API` credential record.
