import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Grid2X2, List, Search } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { LoadingState } from '@/components/ui/LoadingState';
import { VideoCard } from '../components/VideoCard';
import { listVideos } from '@/features/videos/api/videoService';
import { videoKeys } from '@/features/videos/api/queryKeys';
import { useNavigate } from 'react-router-dom';

const PAGE_SIZE = 12;

export function LibraryPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [grid, setGrid] = useState(true);
  const [page, setPage] = useState(1);
  const { data, isLoading, isError } = useQuery({ queryKey: videoKeys.all, queryFn: listVideos });
  const videos = useMemo(
    () =>
      (data ?? []).filter(
        (video) =>
          (filter === 'all' || video.status === filter) &&
          `${video.title} ${video.prompt}`.toLowerCase().includes(search.toLowerCase()),
      ),
    [data, filter, search],
  );
  const totalPages = Math.max(1, Math.ceil(videos.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageVideos = videos.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const rangeStart = videos.length === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(safePage * PAGE_SIZE, videos.length);

  return (
    <div className="space-y-8">
      <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
        <div>
          <p className="eyebrow">Archive / 02</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white">Your library</h1>
          <p className="mt-3 text-sm text-white/45">A quiet place for everything you have made.</p>
        </div>
        <Button variant="primary" onClick={() => navigate('/generate')}>
          New video
        </Button>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-white/30" />
          <Input
            className="pl-9"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
            placeholder="Search your videos..."
          />
        </div>
        <div className="flex gap-2">
          <Select
            className="w-40"
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value);
              setPage(1);
            }}
          >
            <option value="all">All videos</option>
            <option value="completed">Completed</option>
            <option value="rendering">Rendering</option>
            <option value="queued">Queued</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </Select>
          <Button
            aria-label="Toggle list view"
            variant="secondary"
            icon={grid ? <List className="size-4" /> : <Grid2X2 className="size-4" />}
            onClick={() => setGrid(!grid)}
          />
        </div>
      </div>
      {isLoading ? (
        <LoadingState label="Loading your library" />
      ) : isError ? (
        <EmptyState
          title="Library unavailable"
          description="Could not load your videos. Check that the backend is running and try again."
        />
      ) : videos.length === 0 ? (
        <EmptyState
          title="Nothing here yet"
          description="Try a different filter or make your first video."
          action={
            <Button variant="primary" onClick={() => navigate('/generate')}>
              Start creating
            </Button>
          }
        />
      ) : (
        <div className={grid ? 'grid gap-5 sm:grid-cols-2 xl:grid-cols-3' : 'grid gap-4'}>
          {pageVideos.map((video) => (
            <VideoCard key={video.id} video={video} />
          ))}
        </div>
      )}
      {!isLoading && !isError && totalPages > 1 && (
        <div className="flex flex-wrap items-center justify-between gap-4">
          <p className="text-xs text-white/40">
            Showing {rangeStart}–{rangeEnd} of {videos.length}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              disabled={safePage <= 1}
              onClick={() => setPage(safePage - 1)}
            >
              Previous
            </Button>
            <span className="min-w-20 text-center text-xs text-white/50">
              Page {safePage} of {totalPages}
            </span>
            <Button
              variant="secondary"
              disabled={safePage >= totalPages}
              onClick={() => setPage(safePage + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
