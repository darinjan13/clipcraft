alter table public.scenes drop constraint if exists scenes_transition_check;
alter table public.scenes add constraint scenes_transition_check
  check (transition in ('fade', 'crossfade', 'slide_left', 'slide_right', 'blur_dissolve'));
