const crypto = require('crypto');

const secret = process.env.SIGNING_SECRET;
const combos = JSON.parse(process.env.COMBOS || '[]');

async function call(bodyRaw) {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = crypto.randomBytes(16).toString('hex');
  const message = `${timestamp}\n${nonce}\n`;
  const signature = crypto.createHmac('sha256', secret).update(message + bodyRaw, 'utf8').digest('hex');
  const res = await fetch('http://127.0.0.1:8000/internal/ai/text/execute', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-ClipCraft-Timestamp': timestamp,
      'X-ClipCraft-Nonce': nonce,
      'X-ClipCraft-Signature': signature,
    },
    body: bodyRaw,
  });
  const text = await res.text();
  return { status: res.status, body: text };
}

async function main() {
  if (!secret) { console.error('SIGNING_SECRET env required'); process.exit(1); }
  for (const c of combos) {
    const body = JSON.stringify({
      job_id: crypto.randomUUID(),
      provider_id: c.provider,
      model_id: c.model,
      credential_source: c.credentialSource || 'environment',
      operation: 'text_generation',
      input: { prompt: 'OK', temperature: 0.6, max_output_tokens: 100, response_format: 'text' },
      routing_version: c.routingVersion || '1',
      request_id: crypto.randomUUID(),
    });
    const r = await call(body);
    console.log(`[${c.label}] ${c.provider}/${c.model} credentialSource=${c.credentialSource} -> HTTP ${r.status}`);
    if (r.status < 300) console.log('   text:', r.body.slice(0, 120));
    else console.log('   error:', r.body.slice(0, 200));
  }
}
main().catch(e => { console.error(e); process.exit(1); });