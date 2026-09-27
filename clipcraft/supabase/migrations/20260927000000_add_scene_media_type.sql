alter table public.scenes add column if not exists media_type text check (media_type in ('photo', 'video'));
