-- Fossle global stats. Paste this whole file into the Supabase SQL editor and click Run.
-- Players can only add one result per dig; nobody can read the raw rows,
-- only the daily totals that fossle_day_stats returns.

create table if not exists public.fossle_results (
  id         bigint generated always as identity primary key,
  day        int        not null check (day between 0 and 100000),
  puzzle     text       not null check (char_length(puzzle) between 1 and 8),
  device     text       not null check (char_length(device) between 8 and 64),
  won        boolean    not null,
  digs       smallint   not null check (digs between 1 and 5),
  hints      smallint   not null default 0 check (hints between 0 and 3),
  first_pos  smallint[] not null check (array_length(first_pos, 1) = 8),
  created_at timestamptz not null default now(),
  unique (day, puzzle, device)
);

create index if not exists fossle_results_day on public.fossle_results (day, puzzle);

alter table public.fossle_results enable row level security;

drop policy if exists "players add results" on public.fossle_results;
create policy "players add results" on public.fossle_results
  for insert to anon with check (true);

grant insert on public.fossle_results to anon;

-- Daily totals: player count, how many digs people needed (1 to 5, then lost),
-- and for each card (newest first) how many placed it right on their first dig
-- plus the average distance from its real layer (positive = placed too deep, i.e. thought older).
create or replace function public.fossle_day_stats(p_day int, p_puzzle text)
returns json
language sql
stable
security definer
set search_path = public
as $$
  with r as (
    select * from fossle_results where day = p_day and puzzle = p_puzzle
  ),
  cards as (
    select k,
           count(*) filter (where r.first_pos[k + 1] = k)          as ok,
           coalesce(round(avg(r.first_pos[k + 1] - k)::numeric, 2), 0) as mean
    from generate_series(0, 7) k
    left join r on true
    group by k
  )
  select json_build_object(
    'players', (select count(*) from r),
    'wins',    (select count(*) from r where won),
    'dist',    json_build_array(
                 (select count(*) from r where won and digs = 1),
                 (select count(*) from r where won and digs = 2),
                 (select count(*) from r where won and digs = 3),
                 (select count(*) from r where won and digs = 4),
                 (select count(*) from r where won and digs = 5),
                 (select count(*) from r where not won)),
    'first_ok',   (select json_agg(ok   order by k) from cards),
    'first_mean', (select json_agg(mean order by k) from cards)
  );
$$;

revoke all on function public.fossle_day_stats(int, text) from public;
grant execute on function public.fossle_day_stats(int, text) to anon;
