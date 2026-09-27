import type { Video } from '@/features/videos/types';

export function PreviewCanvas({ video }: { video: Video }) {
  // Match the box to the video's aspect ratio so the frame is never cropped
  // in-page. The video uses object-contain (not cover) so browser fullscreen
  // letterboxes instead of zoom-cropping - burned-in captions near the frame
  // edges stay visible on any screen shape.
  const aspectClass = video.aspectRatio === '16:9' ? 'aspect-[16/9]' : video.aspectRatio === '1:1' ? 'aspect-[1/1]' : 'aspect-[9/16]';
  return <div className={`relative mx-auto flex ${aspectClass} max-h-[680px] w-full max-w-[420px] items-center justify-center overflow-hidden rounded-3xl border border-white/10 bg-[#15131c] shadow-glow`}>{video.videoUrl ? <video className="absolute inset-0 size-full object-contain" src={video.videoUrl} poster={video.thumbnail || undefined} controls playsInline /> : <>{video.thumbnail ? <img className="absolute inset-0 size-full object-cover" src={video.thumbnail} alt="Generated video preview" /> : <div className="absolute inset-0 bg-aurora" style={{ background: 'linear-gradient(145deg, #28194d, #111116 70%)' }} />}<div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/10" /><div className="relative size-5 animate-spin rounded-full border-2 border-white/20 border-t-white/70" aria-label="Generating preview" /></>}</div>;
}
