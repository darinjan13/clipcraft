import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, test, vi } from 'vitest';
import type { Video } from '@/features/videos/types';
import * as videoService from '@/features/videos/api/videoService';
import { ToastProvider } from '@/components/ui/Toast';
import { RenderStatus } from './RenderStatus';

const video: Video = {
  id: 'video-1', title: 'Title', prompt: 'Prompt', status: 'awaiting_audio', progress: 20, duration: 30,
  aspectRatio: '9:16', style: 'Cinematic', createdAt: '2026-08-22T00:00:00Z', thumbnail: '', audio_mode: 'custom_audio',
};

function renderStatus() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <RenderStatus video={video} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe('RenderStatus', () => {
  afterEach(() => vi.restoreAllMocks());

  test('downloads narration and revokes the object URL', async () => {
    const narrationBlob = new Blob(['Narration']);
    const narration = vi.spyOn(videoService, 'getNarration').mockResolvedValue(narrationBlob);
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:narration');
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe('narration.txt');
      expect(this.href).toBe('blob:narration');
    });

    renderStatus();
    fireEvent.click(screen.getByRole('button', { name: /download narration text/i }));

    await waitFor(() => expect(narration).toHaveBeenCalledWith('video-1'));
    expect(createObjectURL).toHaveBeenCalledWith(narrationBlob);
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:narration');
  });

  test('revokes the object URL and toasts when download click fails', async () => {
    vi.spyOn(videoService, 'getNarration').mockResolvedValue(new Blob(['Narration']));
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:narration');
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => { throw new Error('Download blocked'); });

    renderStatus();
    fireEvent.click(screen.getByRole('button', { name: /download narration text/i }));

    expect(await screen.findByText('Failed to download narration text')).toBeInTheDocument();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:narration');
  });
});
