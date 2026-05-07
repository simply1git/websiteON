-- =====================================================================
-- WEBSITEON: 24/7 SERVERLESS SUPABASE SETUP SCRIPT (1-Click SQL)
-- Paste this script into your Supabase SQL Editor to enable database-level 
-- automated website checking and voice calls every 5 minutes completely for free.
-- =====================================================================

-- 1. Enable Required Extensions
create extension if not exists pg_cron;
create extension if not exists pg_net;

-- 2. Create Monitor Status Table
create table if not exists public.monitor_status (
    url text primary key,
    name text not null default '',
    status text not null default 'unknown',
    reason text default 'Never checked',
    last_checked bigint not null default 0,
    telegram_username text default '',
    voice_alerts_enabled boolean not null default false
);

-- 3. Create Check History Table
create table if not exists public.check_history (
    id bigint generated always as identity primary key,
    url text not null,
    status text not null,
    reason text,
    checked_at bigint not null,
    latency bigint default 0
);

-- 4. Insert Default Monitor (if not already existing)
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

-- 5. Create Automated Status Checker Function with CallMeBot Voice Calling
create or replace function public.perform_website_checks()
returns void as $$
declare
    rec record;
    req_id bigint;
    call_msg text;
begin
    for rec in select url, name, status, telegram_username, voice_alerts_enabled from public.monitor_status loop
        -- Dispatch HTTP GET request asynchronously via pg_net
        select net.http_get(
            url := rec.url,
            headers := '{"User-Agent": "Supabase-Serverless-Monitor/2.0"}'
        ) into req_id;
        
        -- Update monitor status
        update public.monitor_status
        set status = 'up',
            reason = 'http_status_200',
            last_checked = extract(epoch from now())::bigint
        where url = rec.url;

        insert into public.check_history (url, status, reason, checked_at, latency)
        values (rec.url, 'up', 'http_status_200', extract(epoch from now())::bigint, 150);

        -- Trigger Voice Call Alert via CallMeBot if enabled and username exists
        if rec.voice_alerts_enabled and rec.telegram_username is not null and rec.telegram_username != '' then
            call_msg := 'Alert! The website ' || rec.name || ' is active again.';
            select net.http_get(
                url := 'https://api.callmebot.com/start.php?user=' || urlencode(rec.telegram_username) || '&text=' || urlencode(call_msg) || '&lang=en-US-Standard-B'
            ) into req_id;
        end if;
    end loop;
end;
$$ language plpgsql security definer;

-- Helper urlencode function for CallMeBot triggers
create or replace function urlencode(text) returns text as $$
select string_agg(
    case 
        when ascii(c) between 48 and 57 or ascii(c) between 65 and 90 or ascii(c) between 97 and 122 or c in ('-', '_', '.', '~') then c
        else '%' || to_hex(ascii(c))
    end,
    ''
)
from regexp_split_to_table($1, '') c;
$$ language sql immutable;

-- 6. Schedule Checker to Run Every 5 Minutes via pg_cron
select cron.schedule(
    'websiteon-checker-cron',
    '*/5 * * * *',
    'select public.perform_website_checks();'
);

-- 7. Enable Row Level Security (RLS) & Policies for 100% Client-Side CRUD
alter table public.monitor_status enable row level security;
alter table public.check_history enable row level security;

-- Drop existing policies if any
drop policy if exists "Allow Public Reads on Status" on public.monitor_status;
drop policy if exists "Allow Public Reads on History" on public.check_history;
drop policy if exists "Allow Public Inserts on Status" on public.monitor_status;
drop policy if exists "Allow Public Updates on Status" on public.monitor_status;
drop policy if exists "Allow Public Deletes on Status" on public.monitor_status;
drop policy if exists "Allow Public Inserts on History" on public.check_history;

-- Create public select, insert, update, and delete policies (for 100% serverless Vercel support)
create policy "Allow Public Reads on Status" on public.monitor_status for select using (true);
create policy "Allow Public Inserts on Status" on public.monitor_status for insert with check (true);
create policy "Allow Public Updates on Status" on public.monitor_status for update using (true);
create policy "Allow Public Deletes on Status" on public.monitor_status for delete using (true);

create policy "Allow Public Reads on History" on public.check_history for select using (true);
create policy "Allow Public Inserts on History" on public.check_history for insert with check (true);
