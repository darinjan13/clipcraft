import { useRef, useState } from 'react';
import { Play, Square } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { musicFileUrl, type MusicTrack } from '@/features/settings/api/settingsService';

interface Props {
  tracks: MusicTrack[];
  track: string;
  volume: number;
  onTrackChange: (track: string | undefined) => void;
  onVolumeChange: (volume: number) => void;
}

export function MusicBedControl({ tracks, track, volume, onTrackChange, onVolumeChange }: Props) {
  const previewRef = useRef<HTMLAudioElement | null>(null);
  const [previewing, setPreviewing] = useState(false);

  const stopPreview = () => {
    previewRef.current?.pause();
    setPreviewing(false);
  };

  const togglePreview = () => {
    const el = previewRef.current;
    if (!el || !track) return;
    if (previewing) {
      stopPreview();
    } else {
      el.volume = volume / 100;
      el.currentTime = 0;
      void el.play().catch(() => setPreviewing(false));
      setPreviewing(true);
    }
  };

  return (
    <div>
      <label>
        <span className="mb-2 block text-xs font-medium text-white/55">Music bed</span>
        <Select
          value={track}
          onChange={(event) => {
            stopPreview();
            onTrackChange(event.target.value || undefined);
          }}
        >
          <option value="">No music</option>
          {tracks.map((item) => (
            <option key={item.name} value={item.name}>
              {item.name}
            </option>
          ))}
        </Select>
      </label>
      {track && (
        <div className="mt-2 flex items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            aria-label={previewing ? 'Stop music preview' : 'Preview music bed'}
            icon={previewing ? <Square className="size-3.5" /> : <Play className="size-3.5" />}
            onClick={togglePreview}
          />
          <input
            type="range"
            min={0}
            max={100}
            value={volume}
            aria-label="Music bed volume"
            className="h-1 flex-1 accent-violet-400"
            onChange={(event) => {
              const next = Number(event.target.value);
              onVolumeChange(next);
              if (previewRef.current) previewRef.current.volume = next / 100;
            }}
          />
          <span className="w-9 text-right font-mono text-[11px] text-white/50">{volume}</span>
          <audio
            ref={previewRef}
            src={musicFileUrl(track)}
            preload="none"
            className="hidden"
            onEnded={() => setPreviewing(false)}
          />
        </div>
      )}
    </div>
  );
}
