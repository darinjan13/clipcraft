import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Check, Download, MoreHorizontal, RefreshCcw, Square, X } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { DropdownMenu } from '@/components/ui/DropdownMenu';
import { LoadingState } from '@/components/ui/LoadingState';
import { EmptyState } from '@/components/ui/EmptyState';
import { useToast } from '@/components/ui/Toast';
import { PreviewCanvas } from '../components/PreviewCanvas';
import { RenderStatus } from '../components/RenderStatus';
import { getVideo, getVideoStatus, renameVideo, regenerateVideo, duplicateVideo, deleteVideo, downloadVideo, cancelVideo } from '@/features/videos/api/videoService';
import { videoKeys } from '@/features/videos/api/queryKeys';
import { getActivePollInterval } from '../pipeline';

export function PreviewPage() {
  const { videoId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [hidden, setHidden] = useState(typeof document !== 'undefined' ? document.hidden : false);

  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showStopModal, setShowStopModal] = useState(false);
  const [isStopping, setIsStopping] = useState(false);

  const editRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handler = () => setHidden(document.hidden);
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, []);

  useEffect(() => {
    if (editing && editRef.current) {
      editRef.current.focus();
      editRef.current.select();
    }
  }, [editing]);

  const { data: video, isLoading, isError } = useQuery({
    queryKey: videoKeys.detail(videoId),
    queryFn: () => getVideo(videoId),
    enabled: Boolean(videoId),
  });

  const { data: pipeline } = useQuery({
    queryKey: videoKeys.status(videoId),
    queryFn: () => getVideoStatus(videoId),
    enabled: Boolean(videoId),
    refetchInterval: (query) => getActivePollInterval(query.state.data?.status ?? 'queued', hidden),
    refetchIntervalInBackground: true,
  });

  useEffect(() => {
    if (pipeline?.status === 'completed' && !video?.videoUrl) {
      queryClient.invalidateQueries({ queryKey: videoKeys.detail(videoId) });
    }
  }, [pipeline?.status, video?.videoUrl, queryClient, videoId]);

  const renameMutation = useMutation({
    mutationFn: (title: string) => renameVideo(videoId, title),
    onSuccess: (updated) => {
      queryClient.setQueryData(videoKeys.detail(videoId), updated);
      toast('success', 'Title updated');
    },
    onError: (err: Error) => {
      toast('error', err.message || 'Failed to rename');
    },
  });

  const isActive = video && !['completed', 'failed', 'cancelled'].includes(video.status);
  const isCompleted = video?.status === 'completed';
  const isDoingRegenerate = isRegenerating;

  const handleStop = async () => {
    setIsStopping(true);
    setShowStopModal(false);
    try {
      await cancelVideo(videoId);
      toast('success', 'Generation stopped');
      if (video) {
        queryClient.setQueryData(videoKeys.detail(videoId), { ...video, status: 'cancelled' as const });
      }
      queryClient.invalidateQueries({ queryKey: videoKeys.status(videoId) });
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Failed to stop generation');
    } finally {
      setIsStopping(false);
    }
  };

  const handleRegenerate = async () => {
    if (isDoingRegenerate) return;
    setIsRegenerating(true);
    try {
      const result = await regenerateVideo(videoId);
      toast('success', 'Regeneration started');
      queryClient.invalidateQueries({ queryKey: videoKeys.all });
      navigate(`/library/${result.id}`);
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Failed to regenerate');
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleExport = () => {
    if (!isCompleted) return;
    downloadVideo(videoId);
  };

  const handleStartRename = () => {
    setEditValue(video?.title ?? '');
    setEditing(true);
  };

  const handleSaveRename = () => {
    const title = editValue.trim();
    if (!title || !video || title === video.title) {
      setEditing(false);
      return;
    }
    renameMutation.mutate(title);
    setEditing(false);
  };

  const handleCancelRename = () => {
    setEditing(false);
  };

  const handleDuplicate = async () => {
    try {
      const result = await duplicateVideo(videoId);
      toast('success', 'Duplicate created');
      queryClient.invalidateQueries({ queryKey: videoKeys.all });
      navigate(`/library/${result.id}`);
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Failed to duplicate');
    }
  };

  const handleCopyPrompt = () => {
    if (!video?.prompt) return;
    navigator.clipboard.writeText(video.prompt).then(
      () => toast('success', 'Prompt copied'),
      () => toast('error', 'Failed to copy'),
    );
  };

  const handleDelete = async () => {
    setShowDeleteModal(false);
    try {
      await deleteVideo(videoId);
      toast('success', 'Video deleted');
      queryClient.invalidateQueries({ queryKey: videoKeys.all });
      queryClient.removeQueries({ queryKey: videoKeys.detail(videoId) });
      navigate('/library');
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Failed to delete');
    }
  };

  if (isLoading) return <LoadingState label="Loading preview" />;
  if (isError || !video) return <EmptyState title="Preview not found" description="This video is no longer available." />;

  return (
    <div className="space-y-8">
      <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-center">
        <div>
          <Link to="/library" className="mb-4 inline-flex items-center gap-2 text-xs text-white/40 hover:text-white">
            <ArrowLeft className="size-3.5" />Back to library
          </Link>
          <p className="eyebrow">Preview / 03</p>
          {editing ? (
            <div className="mt-3 flex items-center gap-2">
              <input
                ref={editRef}
                className="h-10 rounded-lg border border-white/10 bg-black/20 px-3 text-lg font-semibold tracking-tight text-white outline-none focus:border-violet-300/50"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveRename();
                  if (e.key === 'Escape') handleCancelRename();
                }}
                onBlur={handleSaveRename}
              />
              <button onClick={handleSaveRename} className="rounded-lg p-1.5 text-emerald-400 hover:bg-white/[.07]">
                <Check className="size-4" />
              </button>
              <button onClick={handleCancelRename} className="rounded-lg p-1.5 text-white/50 hover:bg-white/[.07] hover:text-white">
                <X className="size-4" />
              </button>
            </div>
          ) : (
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white">{video.title}</h1>
          )}
        </div>
        <div className="flex gap-2">
          {isActive ? (
            <Button
              variant="danger"
              icon={<Square className="size-4" />}
              loading={isStopping}
              disabled={isStopping}
              onClick={() => setShowStopModal(true)}
            >
              Stop
            </Button>
          ) : (
            <Button
              variant="secondary"
              icon={<RefreshCcw className="size-4" />}
              loading={isDoingRegenerate}
              disabled={isDoingRegenerate}
              onClick={handleRegenerate}
            >
              Regenerate
            </Button>
          )}
          <Button
            variant="primary"
            icon={<Download className="size-4" />}
            disabled={!isCompleted}
            onClick={handleExport}
          >
            Export MP4
          </Button>
          <DropdownMenu
            trigger={<Button variant="ghost" icon={<MoreHorizontal className="size-4" />} />}
            items={[
              { label: 'Rename', onClick: handleStartRename },
              { label: 'Duplicate', onClick: handleDuplicate },
              { label: 'Copy Prompt', onClick: handleCopyPrompt },
              'separator',
              { label: 'Delete', onClick: () => setShowDeleteModal(true), danger: true },
            ]}
          />
        </div>
      </div>
      <div className="grid items-start gap-7 xl:grid-cols-[minmax(300px,.82fr)_minmax(380px,1.18fr)]">
        <PreviewCanvas video={video} />
        <RenderStatus video={video} pipeline={pipeline} />
      </div>
      <Modal
        open={showStopModal}
        onClose={() => setShowStopModal(false)}
        title="Stop generating this video?"
        description="The current process will stop. Any completed assets may be preserved."
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowStopModal(false)}>Keep going</Button>
            <Button variant="danger" onClick={handleStop}>Stop</Button>
          </>
        }
      />
      <Modal
        open={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        title="Delete this video?"
        description="This action cannot be undone. The video and all its generated assets will be permanently removed."
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowDeleteModal(false)}>Cancel</Button>
            <Button variant="danger" onClick={handleDelete}>Delete</Button>
          </>
        }
      />
    </div>
  );
}
