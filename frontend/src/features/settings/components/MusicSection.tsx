import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Music2, Trash2, Upload } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { LoadingState } from '@/components/ui/LoadingState';
import { useToast } from '@/components/ui/Toast';
import { deleteMusic, listMusic, uploadMusic } from '../api/settingsService';
import { settingsKeys } from '../api/queryKeys';

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export function MusicSection() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const tracksQuery = useQuery({ queryKey: settingsKeys.music, queryFn: listMusic, staleTime: 30 * 1000 });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadMusic(file),
    onSuccess: (track) => {
      void queryClient.invalidateQueries({ queryKey: settingsKeys.music });
      toast('success', `Added “${track.name}” (${formatDuration(track.duration)})`);
    },
    onError: (error: Error) => toast('error', error.message || 'Upload failed.'),
  });

  const deleteMutation = useMutation({
    mutationFn: (name: string) => deleteMusic(name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: settingsKeys.music });
      setDeleting(null);
      toast('success', 'Track deleted.');
    },
    onError: (error: Error) => {
      setDeleting(null);
      toast('error', error.message || 'Could not delete track.');
    },
  });

  const tracks = tracksQuery.data ?? [];

  return (
    <section aria-labelledby="music-heading" className="space-y-5">
      <div>
        <h2 id="music-heading" className="text-lg font-semibold text-white">Music library</h2>
        <p className="mt-1 text-sm text-white/60">Upload MP3 or WAV beds (max 50MB). Pick one per video in the Generate form.</p>
      </div>
      <div>
        <input
          ref={fileRef}
          type="file"
          accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = '';
            if (file) uploadMutation.mutate(file);
          }}
        />
        <Button type="button" icon={<Upload className="size-4" />} loading={uploadMutation.isPending} onClick={() => fileRef.current?.click()}>
          Upload track
        </Button>
      </div>
      {tracksQuery.isLoading ? (
        <LoadingState label="Loading tracks" />
      ) : tracksQuery.isError ? (
        <div className="rounded-2xl border border-rose-300/15 bg-rose-400/[.06] p-5 text-sm text-rose-100" role="alert">
          Could not load tracks. <button type="button" className="ml-1 underline" onClick={() => void tracksQuery.refetch()}>Try again</button>
        </div>
      ) : tracks.length === 0 ? (
        <EmptyState title="No tracks yet" description="Upload a horror ambience or two to get started." />
      ) : (
        <ul className="divide-y divide-white/[.07] rounded-2xl border border-white/[.08] bg-white/[.025]">
          {tracks.map((track) => (
            <li key={track.name} className="flex items-center gap-3 px-4 py-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-violet-400/10 text-violet-200" aria-hidden="true">
                <Music2 className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-white/90">{track.name}</p>
                <p className="font-mono text-[11px] text-white/40">{formatDuration(track.duration)}</p>
              </div>
              <button
                type="button"
                aria-label={`Delete ${track.name}`}
                disabled={deleteMutation.isPending}
                onClick={() => { setDeleting(track.name); deleteMutation.mutate(track.name); }}
                className="rounded-lg p-2 text-white/40 hover:bg-white/[.07] hover:text-rose-200 disabled:opacity-50"
              >
                <Trash2 className="size-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {deleting && <p className="text-[11px] text-white/30">Deleting…</p>}
    </section>
  );
}
