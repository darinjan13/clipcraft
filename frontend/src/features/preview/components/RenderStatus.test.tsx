import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import type { Video } from '@/features/videos/types';
import * as videoService from '@/features/videos/api/videoService';
import { RenderStatus } from './RenderStatus';

const video: Video = {
  id: 'video-1', title: 'Title', prompt: 'Prompt', status: 'awaiting_audio', progress: 20, duration: 30,
  aspectRatio: '9:16', style: 'Cinematic', createdAt: '2026-08-22T00:00:00Z', thumbnail: '', audio_mode: 'custom_audio',
};

describe('RenderStatus', () => {
  afterEach(() => vi.restoreAllMocks());

  test('downloads narration using a named object URL and revokes it', async () => {
    const narrationBlob = new Blob(['Narration']);
    const narration = vi.spyOn(videoService, 'getNarration').mockResolvedValue(narrationBlob);
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:narration');
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe('clipcraft-narration.txt');
      expect(this.href).toBe('blob:narration');
    });

    render(<RenderStatus video={video} />);
    fireEvent.click(screen.getByRole('button', { name: /download narration text/i }));

    await waitFor(() => expect(narration).toHaveBeenCalledWith('video-1'));
    expect(createObjectURL).toHaveBeenCalledWith(narrationBlob);
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:narration');
  });

  test('revokes the object URL and shows an alert when download click fails', async () => {
    vi.spyOn(videoService, 'getNarration').mockResolvedValue(new Blob(['Narration']));
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:narration');
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => { throw new Error('Download blocked'); });

    render(<RenderStatus video={video} />);
    fireEvent.click(screen.getByRole('button', { name: /download narration text/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Download blocked');
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:narration');
  });
});
