const assert = require('node:assert/strict');
const test = require('node:test');

const {
  extractNarration,
  narrationTargets,
  normalizeSceneDurations,
  targetSceneCount,
  withinDurationTolerance,
} = require('./duration-logic');

const cases = [
  { duration: 30, words: 70, scenes: 4 },
  { duration: 45, words: 105, scenes: 5 },
  { duration: 60, words: 140, scenes: 7 },
  { duration: 90, words: 210, scenes: 10 },
];

for (const expected of cases) {
  test(`${expected.duration}s calculates narration and scene targets`, () => {
    assert.equal(narrationTargets(expected.duration).targetWords, expected.words);
    assert.equal(targetSceneCount(expected.duration), expected.scenes);
  });

  test(`${expected.duration}s normalized scenes sum to requested duration`, () => {
    const scenes = Array.from({ length: expected.scenes }, (_, index) => ({
      index: index + 1,
      durationSeconds: index % 2 === 0 ? 2 : 10,
    }));
    const normalized = normalizeSceneDurations(scenes, expected.duration);
    const total = normalized.reduce((sum, scene) => sum + scene.durationSeconds, 0);

    assert.ok(Math.abs(total - expected.duration) < 0.001);
    assert.ok(normalized.every((scene) => scene.durationSeconds >= 4));
    assert.ok(normalized.every((scene) => scene.durationSeconds <= 10));
  });
}

test('duration scaling has no five-scene cap', () => {
  assert.equal(targetSceneCount(60), 7);
  assert.equal(targetSceneCount(90), 10);
});

test('narration targets use measured voice-specific speaking rates', () => {
  assert.equal(narrationTargets(90, 'Warm narrator').targetWords, 210);
  assert.equal(narrationTargets(90, 'Studio neutral').targetWords, 198);
  assert.equal(narrationTargets(90, 'Energetic guide').targetWords, 198);
  assert.deepEqual(
    narrationTargets(90, 'Warm narrator'),
    { voiceWordsPerMinute: 140, targetWords: 210, minWords: 205, maxWords: 215 },
  );
});

test('extractNarration sends only intended narration text', () => {
  const script = {
    fullNarration: 'One intended sentence. A second intended sentence.',
    scenes: [{ narration: 'scene narration', imagePrompt: 'metadata must not leak' }],
    durationValidation: { targetWords: 8 },
  };

  const text = extractNarration(script);

  assert.equal(text, script.fullNarration);
  assert.equal(text.includes('imagePrompt'), false);
  assert.equal(text.includes('metadata must not leak'), false);
});

test('extractNarration falls back to concatenated scene narration', () => {
  assert.equal(
    extractNarration({ scenes: [{ narration: 'First.' }, { narration: 'Second.' }] }),
    'First. Second.',
  );
});

test('TTS duration tolerance rejects the verified 258 second mismatch', () => {
  assert.equal(withinDurationTolerance(87.8, 90, 90), true);
  assert.equal(withinDurationTolerance(82, 90, 90), false);
  assert.equal(withinDurationTolerance(91.5, 90, 90), true);
  assert.equal(withinDurationTolerance(95, 90, 90), false);
  assert.equal(withinDurationTolerance(258.65, 90, 90), false);
});
