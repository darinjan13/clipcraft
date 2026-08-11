const crypto = require('crypto');

const secret = process.env.SIGNING_SECRET;
const bodyRaw = process.env.BODY_RAW; // pre-built JSON string

async function main() {
  if (!secret) { console.error('SIGNING_SECRET env required'); process.exit(1); }
  if (!bodyRaw) { console.error('BODY_RAW env required'); process.exit(1); }
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
  console.log('HTTP', res.status);
  console.log(text);
}

main().catch(e => { console.error(e); process.exit(1); });