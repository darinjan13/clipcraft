import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Music } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Panel } from '@/components/ui/Panel';
import { useToast } from '@/components/ui/Toast';
import { listMusic } from '@/features/settings/api/settingsService';
import { settingsKeys } from '@/features/settings/api/queryKeys';
import { applyMusicBed } from '@/features/videos/api/videoService';
import { videoKeys } from '@/features/videos/api/queryKeys';
import { MusicBedControl } from '@/features/videos/components/MusicBedControl';

export function AddMusicSection({ videoId }: { videoId: string }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [track, setTrack] = useState('');
  const [volume, setVolume] = useState(50);
  const { data: tracks } = useQuery({ queryKey: settingsKeys.music, queryFn: listMusic, staleTime: 60 * 1000 });

  const mutation = useMutation({
    mutationFn: () => applyMusicBed(videoId, track, volume),
    onSuccess: (updated) => {
      queryClient.setQueryData(videoKeys.detail(videoId), updated);
      queryClient.invalidateQueries({ queryKey: videoKeys.status(videoId) });
      toast('success', 'Music bed added');
    },
    onError: (err: Error) => {
      toast('error', err.message || 'Failed to add music');
    },
  });

  return (
    <Panel className="p-5 sm:p-6">
      <div className="mb-4 flex items-center gap-2">
        <Music className="size-4 text-white/40" />
        <h2 className="text-sm font-semibold text-white/90">Add music to this video</h2>
      </div>
      <p className="mb-4 text-xs leading-5 text-white/50">
        Mix a music bed into the finished video, or pick No music to remove it. Fast — the visuals are not re-rendered.
      </p>
      <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
        <MusicBedControl
          tracks={tracks ?? []}
          track={track}
          volume={volume}
          onTrackChange={(next) => setTrack(next ?? '')}
          onVolumeChange={setVolume}
        />
        <Button
          type="button"
          variant="primary"
          className="w-full sm:w-auto"
          loading={mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {track ? 'Apply music' : 'Remove music'}
        </Button>
      </div>
    </Panel>
  );
}
