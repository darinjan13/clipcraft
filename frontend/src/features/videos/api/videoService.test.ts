import { afterEach, describe, expect, test, vi } from 'vitest';
import { createVideo, slugifyTitle } from './videoService';

describe('slugifyTitle', () => {
  test('strips filesystem-illegal characters and trims', () => {
    expect(slugifyTitle('The Midnight Scratch: Part 2?')).toBe('The Midnight Scratch Part 2');
    expect(slugifyTitle('  ')).toBe('clipcraft-video');
    expect(slugifyTitle('A/B\\C*D"E<F>G|H')).toBe('ABCDEFGH');
  });
});

describe('createVideo', () => {
  afterEach(() => vi.unstubAllGlobals());

  test('sends audio mode and narration export style', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ thumbnail: '' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await createVideo({
      title: 'Title', prompt: 'Prompt', duration: '30', style: 'Cinematic', voice: 'Warm narrator', captions: 'Clean', aspectRatio: '9:16',
      audio_mode: 'custom_audio', narration_export_style: 'expressive',
    });

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      audio_mode: 'custom_audio', narration_export_style: 'expressive',
    });
  });
});
