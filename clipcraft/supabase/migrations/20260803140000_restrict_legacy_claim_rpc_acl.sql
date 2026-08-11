-- Keep the legacy claim RPC for service-role callers, but remove browser-role
-- access now that the staged worker uses the fenced claim contract.

revoke all on function public.claim_next_video_job(text)
  from public, anon, authenticated;

grant execute on function public.claim_next_video_job(text)
  to service_role;
