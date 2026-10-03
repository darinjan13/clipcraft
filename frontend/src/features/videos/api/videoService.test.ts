import { afterEach, describe, expect, test, vi } from 'vitest';
import { createVideo } from './videoService';

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
