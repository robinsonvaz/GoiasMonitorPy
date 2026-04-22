-- ============================================================
-- Monitor Goiás - Cron Job Configuration
-- Generated: 2026-04-03
-- ============================================================
-- 
-- Pré-requisitos:
--   1. Extensão pg_cron habilitada (pg_catalog schema)
--   2. Extensão pg_net habilitada (extensions schema)
--   3. Aplicação Flask local em execução (porta 5000)
--
-- Este script agenda a coleta automática de notícias a cada 6 horas
-- (00:00, 06:00, 12:00, 18:00 UTC).
--
-- IMPORTANTE: ajuste a URL local caso a aplicação rode em outra porta
-- ou host. Este exemplo usa endpoint HTTP local.
-- ============================================================

-- Habilitar extensões necessárias
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

-- Agendar coleta de notícias a cada 6 horas
SELECT cron.schedule(
  'collect-news-every-6h',
  '0 */6 * * *',
  $$
  SELECT net.http_post(
    url := 'http://127.0.0.1:5000/api/collect-news',
    headers := '{"Content-Type": "application/json"}'::jsonb,
    body := '{}'::jsonb
  ) AS request_id;
  $$
);

-- ============================================================
-- Comandos úteis para gerenciar cron jobs:
-- ============================================================

-- Listar todos os jobs agendados:
-- SELECT * FROM cron.job;

-- Verificar execuções recentes:
-- SELECT * FROM cron.job_run_details ORDER BY start_time DESC LIMIT 20;

-- Desativar um job (sem remover):
-- UPDATE cron.job SET active = false WHERE jobname = 'collect-news-every-6h';

-- Remover um job:
-- SELECT cron.unschedule('collect-news-every-6h');

-- Alterar frequência para a cada 3 horas:
-- SELECT cron.unschedule('collect-news-every-6h');
-- SELECT cron.schedule('collect-news-every-3h', '0 */3 * * *', $$ ... $$);
