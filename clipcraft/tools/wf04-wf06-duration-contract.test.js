const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const workflows = path.resolve(__dirname, '..', 'workflows');
const workflow = (name) => JSON.parse(fs.readFileSync(path.join(workflows, name), 'utf8'));
const node = (source, name) => source.nodes.find((item) => item.name === name);
const run = (source, name, input, selected = {}) => new Function('$input', '$', '$env', node(source, name).parameters.jsCode)(
  { first: () => ({ json: input }) },
  (selectedName) => ({ first: () => ({ json: Array.isArray(selected[selectedName]) ? selected[selectedName][0] : selected[selectedName] }), all: () => (selected[selectedName] || []).map((json) => ({ json })) }),
  {},
);
const runWithRequire = (source, name, selected, require) => new Function('$input', '$', '$env', 'require', node(source, name).parameters.jsCode)(
  { first: () => ({ json: {} }) },
  (selectedName) => ({ first: () => ({ json: selected[selectedName] }) }),
  {}, require,
);
const canonicalHash = (value) => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');

function script(words, scenes) {
  const tokens = Array.from({ length: words }, (_, index) => `word${index}`);
  let cursor = 0;
  return {
    title: 'Duration contract',
    description: 'Local contract fixture',
    scenes: Array.from({ length: scenes }, (_, index) => ({
      narration: tokens.slice(cursor, cursor += Math.ceil((words - cursor) / (scenes - index))).join(' '),
      caption: `Caption ${index}`,
      imagePrompt: `Prompt ${index}`,
      durationSeconds: 5,
      motion: 'zoom_in',
      transition: 'crossfade',
    })),
  };
}

test('WF04 repository export keeps activeVersion graph and fullScenes validation in parity', () => {
  const wf04 = workflow('04-generate-script-and-scenes.json');

  assert.equal(canonicalHash(wf04.activeVersion.nodes), canonicalHash(wf04.nodes));
  assert.equal(canonicalHash(wf04.activeVersion.connections), canonicalHash(wf04.connections));
  assert.match(node(wf04, 'Validate Output').parameters.jsCode, /Array\.isArray\(content\.fullScenes\)/);
  assert.match(node(wf04.activeVersion, 'Validate Output').parameters.jsCode, /Array\.isArray\(content\.fullScenes\)/);
});

test('WF04 Build Prompt requires one valid JSON object without presentation wrappers', () => {
  const wf04 = workflow('04-generate-script-and-scenes.json');
  const prompt = node(wf04, 'Build Prompt').parameters.jsCode;

  assert.match(prompt, /one valid JSON object only/i);
  assert.match(prompt, /no markdown fences/i);
  assert.match(prompt, /no headings/i);
  assert.match(prompt, /no extra prose/i);
});

test('WF04 accepts each inclusive estimated-duration range and persists exact diagnostics', () => {
  const wf04 = workflow('04-generate-script-and-scenes.json');
  for (const [requestedDuration, words, scenes, minimumDuration, maximumDuration] of [
    [30, 105, 6, 30, 45], [45, 143, 9, 45, 65], [60, 198, 12, 60, 85], [90, 280, 19, 90, 120],
  ]) {
    const job = { id: `job-${requestedDuration}`, brief_json: { duration: requestedDuration, topic: 'Test', voiceTone: 'Warm narrator', contentStyle: 'clear', visualStyle: 'editorial' } };
    const configuration = run(wf04, 'Duration Configuration', [job])[0].json;
    const prompt = run(wf04, 'Build Prompt', configuration, { Validate: {}, 'Duration Configuration': configuration })[0].json;
    const validated = run(wf04, 'Validate Output', { result: JSON.stringify(script(words, scenes)) }, { 'Build Prompt': prompt })[0].json;
    assert.equal(validated.wordCountValid, true);
    assert.deepEqual(validated.content.durationValidation, {
      requestedDuration, minimumDuration, maximumDuration,
      estimatedDurationSeconds: Math.round((words * 60 / 140) * 100) / 100,
      wordCount: words,
      voiceWordsPerMinute: 140,
    });
    assert.equal(Math.round(validated.content.scenes.reduce((total, scene) => total + scene.durationSeconds, 0) * 100) / 100, Math.round((words * 60 / 140) * 100) / 100);
  }
});

test('WF04 normalizes a valid provider fullScenes array to canonical scenes', () => {
  const wf04 = workflow('04-generate-script-and-scenes.json');
  const job = { id: 'job-full-scenes', brief_json: { duration: 30, topic: 'Test', voiceTone: 'Warm narrator', contentStyle: 'clear', visualStyle: 'editorial' } };
  const configuration = run(wf04, 'Duration Configuration', [job])[0].json;
  const prompt = run(wf04, 'Build Prompt', configuration, { Validate: {}, 'Duration Configuration': configuration })[0].json;
  const providerContent = script(105, 6);
  providerContent.fullScenes = providerContent.scenes;
  delete providerContent.scenes;

  const validated = run(wf04, 'Validate Output', {
    result: JSON.stringify(providerContent),
  }, { 'Build Prompt': prompt })[0].json;

  assert.equal(Array.isArray(validated.content.scenes), true);
  assert.equal(validated.content.scenes.length, 6);
  assert.equal(validated.wordCountValid, true);
});

test('WF04 preserves sparse supported delivery metadata through canonical script and scene rows', () => {
  const wf04 = workflow('04-generate-script-and-scenes.json');
  const configuration = run(wf04, 'Duration Configuration', [{
    id: 'job-delivery',
    brief_json: { duration: 30, topic: 'Test', voiceTone: 'Warm narrator', contentStyle: 'clear', visualStyle: 'editorial' },
  }])[0].json;
  const prompt = run(wf04, 'Build Prompt', configuration, { Validate: {}, 'Duration Configuration': configuration })[0].json;
  const validated = run(wf04, 'Validate Output', {
    result: JSON.stringify({
      title: 'Delivery contract',
      description: 'Local contract fixture',
      scenes: Array.from({ length: 6 }, (_, index) => ({
        narration: `Scene ${index} has enough words for duration validation`,
        caption: `Caption ${index}`,
        imagePrompt: `Prompt ${index}`,
        durationSeconds: 5,
        motion: 'zoom_in',
        transition: 'crossfade',
        ...(index === 0 ? { delivery: 'dramatic' } : index === 1 ? { delivery: 'elevenlabs:whisper' } : {}),
      })),
    }),
  }, { 'Build Prompt': prompt })[0].json;

  assert.equal(validated.content.scenes[0].delivery, 'dramatic');
  assert.equal(Object.hasOwn(validated.content.scenes[1], 'delivery'), false);

  const rows = run(wf04, 'Prepare Scene Rows', {}, { 'Validate Output': validated });
  assert.equal(Object.hasOwn(rows[0].json, 'delivery'), false);
  assert.equal(Object.hasOwn(rows[1].json, 'delivery'), false);
});

test('WF06 consumes WF04 durationValidation and has no independent exact word or selected-duration gate', () => {
  const wf04 = workflow('04-generate-script-and-scenes.json');
  const wf06 = workflow('06-generate-narration.json');
  const job = { id: 'job-30-maximum', brief_json: { duration: 30, voiceTone: 'Warm narrator', contentStyle: 'clear', visualStyle: 'editorial' } };
  const configuration = run(wf04, 'Duration Configuration', [job])[0].json;
  const prompt = run(wf04, 'Build Prompt', configuration, { Validate: {}, 'Duration Configuration': configuration })[0].json;
  const validated = run(wf04, 'Validate Output', { result: JSON.stringify(script(105, 6)) }, { 'Build Prompt': prompt })[0].json;
  const extracted = run(wf06, 'Extract Narration Text', [{ ...job, script_json: validated.content }])[0].json;

  assert.equal(extracted.minimumDuration, 30);
  assert.equal(extracted.maximumDuration, 45);
  assert.equal(extracted.estimatedDurationSeconds, 45);
  assert.equal(extracted.wordCount, 105);
  assert.doesNotMatch(node(wf06, 'Extract Narration Text').parameters.jsCode, /NARRATION_WORD_COUNT_MISMATCH|SCENE_DURATION_MISMATCH/);
});

test('WF04 terminal duration failure finalizes the leased stage with documented diagnostics', () => {
  const wf04 = workflow('04-generate-script-and-scenes.json');
  const error = node(wf04, 'Word Count Validation Error').parameters.jsCode;
  const finalize = node(wf04, 'Finalize Provider Failure').parameters.jsonBody;
  const terminalBranch = wf04.connections['Word Count Revision Allowed?'].main[1][0].node;

  assert.equal(terminalBranch, 'Word Count Validation Error');
  assert.equal(wf04.connections['Word Count Validation Error'].main[0][0].node, 'Finalize Provider Failure');
  for (const key of ['requestedDuration', 'minimumDuration', 'maximumDuration', 'estimatedDurationSeconds', 'wordCount', 'revision']) assert.match(error, new RegExp(key));
  assert.match(error, /NARRATION_DURATION_OUT_OF_RANGE/);
  assert.match(finalize, /NARRATION_DURATION_OUT_OF_RANGE|errorCode/);
  assert.match(finalize, /code: \$json\.errorCode/);
  assert.match(finalize, /p_retryable: !\$json\.errorCode/);
});

test('WF06 persists corrected automatic timing while custom audio remains authoritative', () => {
  const wf06 = workflow('06-generate-narration.json');
  const prepare = node(wf06, 'Prepare Effective Duration').parameters.jsCode;
  const persist = node(wf06, 'Persist Effective Duration').parameters;

  assert.match(prepare, /audioMode === 'custom_audio'/);
  assert.match(prepare, /corrected_duration/);
  assert.match(persist.url, /video_jobs\?id=eq/);
  assert.match(persist.jsonBody, /effective_duration/);
  assert.equal(wf06.connections['Save Asset Record'].main[0][0].node, 'Prepare Effective Duration');
});

test('WF04 uses one executable duration configuration node for prompt and persisted validation', () => {
  const wf04 = workflow('04-generate-script-and-scenes.json');
  const configuration = run(wf04, 'Duration Configuration', {} )[0].json;
  const prompt = node(wf04, 'Build Prompt').parameters.jsCode;

  assert.deepEqual(configuration.durationRanges, { 30: [30, 45], 45: [45, 65], 60: [60, 85], 90: [90, 120] });
  assert.match(prompt, /Duration Configuration/);
  assert.doesNotMatch(prompt, /30:\s*\[30,\s*45\]/);
});

test('WF07 and WF08 scale automatic timelines to persisted effective duration', () => {
  const scenes = [
    { scene_index: 1, narration: 'One', caption: 'One', duration_seconds: 5, video_jobs: { audio_mode: 'automatic', effective_duration: 42 } },
    { scene_index: 2, narration: 'Two', caption: 'Two', duration_seconds: 5, video_jobs: { audio_mode: 'automatic', effective_duration: 42 } },
  ];
  const wf07 = workflow('07-build-captions.json');
  const captions = run(wf07, 'Generate ASS File', {}, { 'Get Scenes': scenes, 'Validate Input': { jobId: 'job' } })[0];
  const wf08 = workflow('08-build-render-manifest.json');
  const manifest = run(wf08, 'Build Manifest', {}, { 'Get Job': { id: 'job', audio_mode: 'automatic', effective_duration: 42 }, 'Get Scenes': scenes })[0].json.manifest;

  assert.match(Buffer.from(captions.binary.data.data, 'base64').toString('utf8'), /0:00:42\.00/);
  assert.equal(manifest.duration, 42);
  assert.equal(manifest.scenes.reduce((total, scene) => total + scene.duration, 0), 42);
});

test('WF07 and WF08 repository exports keep activeVersion graphs in parity', () => {
  for (const filename of ['07-build-captions.json', '08-build-render-manifest.json']) {
    const source = workflow(filename);
    assert.equal(canonicalHash(source.activeVersion.nodes), canonicalHash(source.nodes));
    assert.equal(canonicalHash(source.activeVersion.connections), canonicalHash(source.connections));
  }
});

test('WF06 re-probes corrected audio and rejects corrections beyond its safe threshold', () => {
  const correction = node(workflow('06-generate-narration.json'), 'Correct Audio Duration').parameters.jsCode;
  assert.match(correction, /verifiedDuration/);
  assert.match(correction, /AUDIO_DURATION_CORRECTION_UNSAFE/);
});

test('WF06 repository export keeps the duration-correcting graph in activeVersion parity', () => {
  const wf06 = workflow('06-generate-narration.json');

  assert.equal(canonicalHash(wf06.activeVersion.nodes), canonicalHash(wf06.nodes));
  assert.equal(canonicalHash(wf06.activeVersion.connections), canonicalHash(wf06.connections));
  assert.match(node(wf06.activeVersion, 'Correct Audio Duration').parameters.jsCode, /MINIMUM_DURATION_TOLERANCE_SECONDS = 0\.5/);
});

test('WF06 correction output supplies a numeric file size to the automatic asset record', () => {
  const wf06 = workflow('06-generate-narration.json');
  const fsMock = { existsSync: () => true, copyFileSync: () => {}, unlinkSync: () => {}, statSync: () => ({ size: 123456 }) };
  const corrected = runWithRequire(wf06, 'Correct Audio Duration', {
    'Validate Input': { jobId: 'job' },
    'Extract Narration Text': { minimumDuration: 30, maximumDuration: 45 },
  }, (moduleName) => moduleName === 'fs' ? fsMock : { spawnSync: () => ({ status: 0, stdout: '42\n' }) })[0].json;

  assert.equal(corrected.file_size, 123456);
  assert.match(node(wf06, 'Save Asset Record').parameters.jsonBody, /\$json\.file_size/);
  assert.equal(Number.isFinite(corrected.file_size), true);
});

test('WF06 accepts a 29.97-second automatic probe at the 30-second minimum without overstating duration', () => {
  const wf06 = workflow('06-generate-narration.json');
  const fsMock = { existsSync: () => true, copyFileSync: () => {}, unlinkSync: () => {}, statSync: () => ({ size: 123456 }) };
  const runCorrection = (durations) => {
    let probeIndex = 0;
    return runWithRequire(wf06, 'Correct Audio Duration', {
      'Validate Input': { jobId: 'job-boundary' },
      'Extract Narration Text': { minimumDuration: 30, maximumDuration: 45 },
    }, (moduleName) => moduleName === 'fs' ? fsMock : {
      spawnSync: (command) => command === 'ffprobe'
        ? { status: 0, stdout: `${durations[probeIndex++] ?? durations.at(-1)}\n` }
        : { status: 0, stdout: '' },
    })[0].json;
  };

  const boundary = runCorrection([29.97, 29.97]);
  assert.equal(boundary.corrected_duration, 29.97);

  const corrected = runCorrection([20, 30]);
  assert.equal(corrected.corrected_duration, 30);

  assert.throws(() => runCorrection([10]), /AUDIO_DURATION_CORRECTION_UNSAFE/);
  assert.throws(() => runCorrection([45.01, 45.01]), /NARRATION_DURATION_OUT_OF_RANGE/);
});
