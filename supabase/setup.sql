-- =====================================================================
-- WEBSITEON: SUPABASE DATABASE SCHEMA SETUP SCRIPT
-- Paste this script into your Supabase SQL Editor to initialize your
-- data tables securely for the WebsiteON serverless platform.
-- =====================================================================

-- 0. Kill the old flawed cron job if it exists
select cron.unschedule('website-check-cron') 
where exists (
    select 1 from cron.job where jobname = 'website-check-cron'
);

-- 1. Clean Up Old Schemas (Forces Recreation)
drop table if exists public.check_history cascade;
drop table if exists public.monitor_status cascade;

-- 2. Create Monitor Status Table
create table public.monitor_status (
    url text primary key,
    name text not null default '',
    status text not null default 'unknown',
    reason text default 'Never checked',
    last_checked bigint not null default 0,
    telegram_username text default '',
    voice_alerts_enabled boolean not null default false
);

-- 3. Create Check History Table
create table public.check_history (
    id bigint generated always as identity primary key,
    url text not null,
    status text not null,
    reason text,
    checked_at bigint not null,
    latency bigint default 0
);

-- 4. Enable Row Level Security (RLS) & Policies
alter table public.monitor_status enable row level security;
alter table public.check_history enable row level security;

-- Drop existing policies if any
drop policy if exists "Allow Public Reads on Status" on public.monitor_status;
drop policy if exists "Allow Public Reads on History" on public.check_history;
drop policy if exists "Allow Public Inserts on Status" on public.monitor_status;
drop policy if exists "Allow Public Updates on Status" on public.monitor_status;
drop policy if exists "Allow Public Deletes on Status" on public.monitor_status;
drop policy if exists "Allow Public Inserts on History" on public.check_history;

-- Create public select, insert, update, and delete policies
create policy "Allow Public Reads on Status" on public.monitor_status for select using (true);
create policy "Allow Public Inserts on Status" on public.monitor_status for insert with check (true);
create policy "Allow Public Updates on Status" on public.monitor_status for update using (true);
create policy "Allow Public Deletes on Status" on public.monitor_status for delete using (true);

create policy "Allow Public Reads on History" on public.check_history for select using (true);
create policy "Allow Public Inserts on History" on public.check_history for insert with check (true);

-- 5. Insert Default Monitor Data
insert into public.monitor_status (url, name, status, reason, last_checked, telegram_username, voice_alerts_enabled)
values (
    'https://vtu.internyet.in/dashboard/student/applied-internships', 
    'VTU Applied Internships', 
    'unknown', 
    'Initial Setup', 
    extract(epoch from now())::bigint,
    '',
    false
)
on conflict (url) do nothing;
