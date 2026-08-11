import type { Video } from '@/features/videos/types';

export function PreviewCanvas({ video }: { video: Video }) {
  return <div className="relative mx-auto flex aspect-[9/14] max-h-[680px] w-full max-w-[420px] items-center justify-center overflow-hidden rounded-3xl border border-white/10 bg-[#15131c] shadow-glow">{video.videoUrl ? <video className="absolute inset-0 size-full object-cover" src={video.videoUrl} poster={video.thumbnail || undefined} controls playsInline /> : <>{video.thumbnail ? <img className="absolute inset-0 size-full object-cover" src={video.thumbnail} alt="Generated video preview" /> : <div className="absolute inset-0 bg-aurora" style={{ background: 'linear-gradient(145deg, #28194d, #111116 70%)' }} />}<div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/10" /><div className="relative size-5 animate-spin rounded-full border-2 border-white/20 border-t-white/70" aria-label="Generating preview" /></>}</div>;
}
