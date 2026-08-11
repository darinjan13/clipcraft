const VOICE_WORDS_PER_MINUTE = {
  'Warm narrator': 140,
  'Studio neutral': 132,
  'Energetic guide': 132,
};
const PREFERRED_SCENE_SECONDS = 9;

function requireDuration(duration) {
  const value = Number(duration);
  if (!Number.isFinite(value) || value <= 0) throw new Error('INVALID_REQUESTED_DURATION');
  return value;
}

function targetSceneCount(duration) {
  return Math.ceil(requireDuration(duration) / PREFERRED_SCENE_SECONDS);
}

function narrationTargets(duration, voiceTone = 'Warm narrator') {
  const voiceWordsPerMinute = VOICE_WORDS_PER_MINUTE[voiceTone] || VOICE_WORDS_PER_MINUTE['Warm narrator'];
  const targetWords = Math.round(requireDuration(duration) * voiceWordsPerMinute / 60);
  return {
    voiceWordsPerMinute,
    targetWords,
    minWords: Math.floor(targetWords * 0.98),
    maxWords: Math.ceil(targetWords * 1.02),
  };
}

function normalizeSceneDurations(scenes, duration) {
  const requestedDuration = requireDuration(duration);
  if (!Array.isArray(scenes) || scenes.length === 0) throw new Error('NO_SCENES');

  const each = Math.round(requestedDuration / scenes.length * 100) / 100;
  let assigned = 0;
  return scenes.map((scene, index) => {
    const durationSeconds = index === scenes.length - 1
      ? Math.round((requestedDuration - assigned) * 100) / 100
      : each;
    assigned += durationSeconds;
    return { ...scene, durationSeconds };
  });
}

function extractNarration(script) {
  if (!script || typeof script !== 'object') return '';
  const fullNarration = String(script.fullNarration || '').trim();
  if (fullNarration) return fullNarration;
  return Array.isArray(script.scenes)
    ? script.scenes.map((scene) => String(scene.narration || '').trim()).filter(Boolean).join(' ')
    : '';
}

function withinDurationTolerance(actual, requested, sceneTotal) {
  const actualDuration = Number(actual);
  const requestedDuration = requireDuration(requested);
  const timelineDuration = requireDuration(sceneTotal);
  if (!Number.isFinite(actualDuration) || actualDuration <= 0) return false;
  const shortTolerance = Math.max(3, requestedDuration * 0.05);
  return actualDuration >= requestedDuration - shortTolerance
    && actualDuration <= requestedDuration + 2
    && actualDuration <= timelineDuration + 2;
}

module.exports = {
  extractNarration,
  narrationTargets,
  normalizeSceneDurations,
  targetSceneCount,
  withinDurationTolerance,
};
