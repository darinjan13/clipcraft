const assert = require('node:assert/strict');
const test = require('node:test');

const API_KEY = process.env.N8N_API_KEY;
const BASE_URL = process.env.N8N_BASE_URL;
const WF04 = 'dWTF2UGXX3R73PDW';
const WF06 = 'UhWkv3GLHVSpWrMe';

if (!API_KEY || !BASE_URL) throw new Error('N8N_API_KEY and N8N_BASE_URL are required');

async function workflow(id) {
  const response = await fetch(`${BASE_URL}/api/v1/workflows/${id}`, {
    headers: { 'X-N8N-API-KEY': API_KEY },
  });
  assert.equal(response.status, 200);
  return response.json();
}

function codeNode(source, name) {
  const node = source.nodes.find((item) => item.name === name);
  assert.ok(node, `missing ${name}`);
  return new Function('$input', '$', '$env', node.parameters.jsCode);
}

function selector(values) {
  return (name) => ({
    first() {
      const value = values[name];
      if (value instanceof Error) throw value;
      return { json: value };
    },
  });
}

function scriptContent(targetWords, sceneCount) {
  const words = Array.from({ length: targetWords }, (_, index) => (
    index === targetWords - 1 ? 'complete.' : `word${index + 1}`
  ));
  const scenes = [];
  let cursor = 0;
  for (let index = 0; index < sceneCount; index += 1) {
    const remainingScenes = sceneCount - index;
    const take = Math.ceil((words.length - cursor) / remainingScenes);
    scenes.push({
      narration: words.slice(cursor, cursor + take).join(' '),
      caption: `Scene ${index + 1}`,
      imagePrompt: `Visual ${index + 1}`,
      durationSeconds: index % 2 === 0 ? 2 : 10,
      motion: index === 1 ? 'static' : 'zoom_in',
      transition: index === 0 ? 'cut' : 'crossfade',
    });
    cursor += take;
  }
  return { title: 'Test', description: 'Test description', scenes };
}

test('live WF04 and WF06 enforce duration invariants without provider calls', async () => {
  const [wf04, wf06] = await Promise.all([workflow(WF04), workflow(WF06)]);
  const buildPrompt = codeNode(wf04, 'Build Prompt');
  const validateOutput = codeNode(wf04, 'Validate Output');
  const extractNarration = codeNode(wf06, 'Extract Narration Text');
  const expected = [
    { duration: 30, words: 70, scenes: 4 },
    { duration: 45, words: 105, scenes: 5 },
    { duration: 60, words: 140, scenes: 7 },
    { duration: 90, words: 210, scenes: 10 },
  ];

  for (const item of expected) {
    const job = {
      id: `job-${item.duration}`,
      brief_json: {
        duration: item.duration,
        topic: 'Duration test',
        voiceTone: 'Warm narrator',
        textProvider: 'gemini',
        textModel: 'gemini-2.5-flash',
        imageProvider: 'cloudflare',
        imageModel: 'flux',
      },
    };
    const promptResult = buildPrompt(
      { first: () => ({ json: [job] }) },
      selector({ Validate: { requestedDuration: item.duration } }),
      {},
    )[0].json;
    assert.equal(promptResult.targetWords, item.words);
    assert.equal(promptResult.targetSceneCount, item.scenes);

    const content = scriptContent(item.words, item.scenes);
    const validation = validateOutput(
      { first: () => ({ json: { result: JSON.stringify(content), model: 'test' } }) },
      selector({
        'Build Prompt': promptResult,
        'Build Word Count Revision': new Error('not executed'),
      }),
      {},
    )[0].json;
    assert.equal(validation.scriptValid, true);
    assert.equal(validation.sceneCount, item.scenes);
    assert.ok(Math.abs(validation.sceneDurationTotal - item.duration) <= 0.01);
    assert.ok(validation.content.scenes.every((scene) => (
      ['fade', 'crossfade', 'slide_left', 'slide_right'].includes(scene.transition)
    )));
    assert.ok(validation.content.scenes.every((scene) => (
      ['zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down'].includes(scene.motion)
    )));

    const extracted = extractNarration(
      { first: () => ({ json: [{ ...job, script_json: validation.content }] }) },
      selector({}),
      {},
    )[0].json;
    assert.equal(extracted.text, validation.content.fullNarration);
    assert.equal(extracted.wordCount, item.words);
    assert.equal(extracted.sceneDuration, item.duration);
    assert.equal(extracted.ttsVoice, 'af_heart');
    assert.equal(extracted.text.includes('Visual'), false);
  }
});

test('live WF04 rejects the old five-scene 90-second response', async () => {
  const wf04 = await workflow(WF04);
  const buildPrompt = codeNode(wf04, 'Build Prompt');
  const validateOutput = codeNode(wf04, 'Validate Output');
  const job = { id: 'old-failure', brief_json: { duration: 90, topic: 'Test' } };
  const context = buildPrompt(
    { first: () => ({ json: [job] }) },
    selector({ Validate: { requestedDuration: 90 } }),
    {},
  )[0].json;
  const validation = validateOutput(
    { first: () => ({ json: { result: JSON.stringify(scriptContent(210, 5)) } }) },
    selector({
      'Build Prompt': context,
      'Build Word Count Revision': new Error('not executed'),
    }),
    {},
  )[0].json;

  assert.equal(validation.sceneCountValid, false);
  assert.equal(validation.scriptValid, false);
});

test('live WF04 skips Gemini when a valid script already exists', async () => {
  const wf04 = await workflow(WF04);
  const buildPrompt = codeNode(wf04, 'Build Prompt');
  const existingScript = scriptContent(210, 10);
  existingScript.scenes = existingScript.scenes.map((scene) => ({ ...scene, durationSeconds: 9 }));
  existingScript.fullNarration = existingScript.scenes.map((scene) => scene.narration).join(' ');
  const job = {
    id: 'existing-script',
    brief_json: { duration: 90, topic: 'Test', voiceTone: 'Warm narrator' },
    script_json: existingScript,
  };
  const result = buildPrompt(
    { first: () => ({ json: [job] }) },
    selector({ Validate: { requestedDuration: 90 } }),
    {},
  )[0].json;

  assert.equal(result.skipScript, true);
  assert.equal(result.sceneCount, 10);
});

test('live WF04 does not skip an invalid existing five-scene script', async () => {
  const wf04 = await workflow(WF04);
  const buildPrompt = codeNode(wf04, 'Build Prompt');
  const job = {
    id: 'invalid-existing-script',
    brief_json: { duration: 90, topic: 'Test', voiceTone: 'Warm narrator' },
    script_json: scriptContent(210, 5),
  };
  const result = buildPrompt(
    { first: () => ({ json: [job] }) },
    selector({ Validate: { requestedDuration: 90 } }),
    {},
  )[0].json;

  assert.equal(result.skipScript, false);
});

test('live WF04 does not trust stale fullNarration when scene narration is short', async () => {
  const wf04 = await workflow(WF04);
  const buildPrompt = codeNode(wf04, 'Build Prompt');
  const script = scriptContent(20, 10);
  script.scenes = script.scenes.map((scene) => ({ ...scene, durationSeconds: 9 }));
  script.fullNarration = Array.from({ length: 210 }, (_, index) => `stale${index}`).join(' ') + '.';
  const result = buildPrompt(
    { first: () => ({ json: [{
      id: 'stale-narration',
      brief_json: { duration: 90, topic: 'Test', voiceTone: 'Warm narrator' },
      script_json: script,
    }] }) },
    selector({ Validate: { requestedDuration: 90 } }),
    {},
  )[0].json;

  assert.equal(result.skipScript, false);
});

test('live WF04 does not skip invalid individual scene durations', async () => {
  const wf04 = await workflow(WF04);
  const buildPrompt = codeNode(wf04, 'Build Prompt');
  const script = scriptContent(210, 10);
  script.scenes = script.scenes.map((scene, index) => ({
    ...scene,
    durationSeconds: index === 0 ? 1 : index === 1 ? 17 : 9,
  }));
  script.fullNarration = script.scenes.map((scene) => scene.narration).join(' ');
  const result = buildPrompt(
    { first: () => ({ json: [{
      id: 'invalid-individual-durations',
      brief_json: { duration: 90, topic: 'Test', voiceTone: 'Warm narrator' },
      script_json: script,
    }] }) },
    selector({ Validate: { requestedDuration: 90 } }),
    {},
  )[0].json;

  assert.equal(result.skipScript, false);
});

test('live WF06 derives missing duration metadata from selected voice', async () => {
  const wf06 = await workflow(WF06);
  const extractNarration = codeNode(wf06, 'Extract Narration Text');
  const script = scriptContent(210, 10);
  script.fullNarration = script.scenes.map((scene) => scene.narration).join(' ');
  script.scenes = script.scenes.map((scene) => ({ ...scene, durationSeconds: 9 }));
  const result = extractNarration(
    { first: () => ({ json: [{
      id: 'fallback-voice-rate',
      brief_json: { duration: 90, voiceTone: 'Warm narrator' },
      script_json: script,
    }] }) },
    selector({}),
    {},
  )[0].json;

  assert.equal(result.targetWords, 210);
  assert.equal(result.ttsVoice, 'af_heart');
});

test('live WF06 always speaks canonical scene narration', async () => {
  const wf06 = await workflow(WF06);
  const extractNarration = codeNode(wf06, 'Extract Narration Text');
  const script = scriptContent(210, 10);
  script.scenes = script.scenes.map((scene) => ({ ...scene, durationSeconds: 9 }));
  const canonical = script.scenes.map((scene) => scene.narration).join(' ');
  script.fullNarration = Array.from({ length: 210 }, (_, index) => `stale${index}`).join(' ') + '.';
  script.durationValidation = { voiceWordsPerMinute: 140 };
  const result = extractNarration(
    { first: () => ({ json: [{
      id: 'canonical-narration',
      brief_json: { duration: 90, voiceTone: 'Warm narrator' },
      script_json: script,
    }] }) },
    selector({}),
    {},
  )[0].json;

  assert.equal(result.text, canonical);
});

test('live WF06 rejects nonnumeric scene durations', async () => {
  const wf06 = await workflow(WF06);
  const extractNarration = codeNode(wf06, 'Extract Narration Text');
  const script = scriptContent(210, 10);
  script.fullNarration = script.scenes.map((scene) => scene.narration).join(' ');
  script.scenes = script.scenes.map((scene, index) => ({
    ...scene,
    durationSeconds: index === 0 ? 'bad' : 10,
  }));

  assert.throws(() => extractNarration(
    { first: () => ({ json: [{
      id: 'invalid-scene-duration',
      brief_json: { duration: 90, voiceTone: 'Warm narrator' },
      script_json: script,
    }] }) },
    selector({}),
    {},
  ), /INVALID_SCENE_DURATION/);
});

test('live WF06 serializes the complete TTS body as JSON', async () => {
  const wf06 = await workflow(WF06);
  const callTts = wf06.nodes.find((item) => item.name === 'Call TTS');

  assert.match(callTts.parameters.jsonBody, /JSON\.stringify/);
  assert.doesNotMatch(callTts.parameters.jsonBody, /text\.replace/);
});

test('live WF06 lease covers long local TTS synthesis', async () => {
  const wf06 = await workflow(WF06);
  const heartbeat = wf06.nodes.find((item) => item.name === 'Heartbeat Stage Lease');

  assert.ok(heartbeat);
  assert.match(heartbeat.parameters.jsonBody, /p_lease_seconds:\s*360/);
});
