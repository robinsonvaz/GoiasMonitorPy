-- ============================================================
-- Monitor Goiás - Database Schema & Data Dump
-- Generated: 2026-04-05
-- ============================================================

-- ===================
-- ENUMS
-- ===================

CREATE TYPE public.news_sentiment AS ENUM ('positivo', 'negativo', 'neutro');

CREATE TYPE public.news_classification AS ENUM (
  'midia_negativa', 'nomeacao', 'exoneracao', 'substituicao',
  'troca', 'movimentacao', 'acao_judicial', 'outro'
);

-- ===================
-- TABLES
-- ===================

-- Profiles
CREATE TABLE public.profiles (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id uuid NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name text,
  avatar_url text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view all profiles" ON public.profiles FOR SELECT TO authenticated USING (true);
CREATE POLICY "Users can insert own profile" ON public.profiles FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own profile" ON public.profiles FOR UPDATE TO authenticated USING (auth.uid() = user_id);

-- Monitored Entities
CREATE TABLE public.monitored_entities (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  name text NOT NULL,
  entity_type text NOT NULL DEFAULT 'orgao',
  description text,
  keywords text[] DEFAULT '{}',
  is_active boolean NOT NULL DEFAULT true,
  created_by uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.monitored_entities ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can view entities" ON public.monitored_entities FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can create entities" ON public.monitored_entities FOR INSERT TO authenticated WITH CHECK (auth.uid() = created_by);
CREATE POLICY "Creators can update entities" ON public.monitored_entities FOR UPDATE TO authenticated USING (auth.uid() = created_by);
CREATE POLICY "Creators can delete entities" ON public.monitored_entities FOR DELETE TO authenticated USING (auth.uid() = created_by);

-- News Items
CREATE TABLE public.news_items (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  entity_id uuid REFERENCES public.monitored_entities(id) ON DELETE SET NULL,
  title text NOT NULL,
  content text,
  source_url text,
  source_name text,
  classification news_classification NOT NULL DEFAULT 'outro',
  sentiment news_sentiment NOT NULL DEFAULT 'neutro',
  people_mentioned text[] DEFAULT '{}',
  published_at timestamptz,
  collected_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_news_items_entity ON public.news_items (entity_id);
CREATE INDEX idx_news_items_sentiment ON public.news_items (sentiment);
CREATE INDEX idx_news_items_classification ON public.news_items (classification);
CREATE INDEX idx_news_items_collected ON public.news_items (collected_at DESC);

ALTER TABLE public.news_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can view news" ON public.news_items FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can insert news" ON public.news_items FOR INSERT TO authenticated WITH CHECK (auth.uid() IS NOT NULL);

-- Alerts
CREATE TABLE public.alerts (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  news_item_id uuid REFERENCES public.news_items(id) ON DELETE CASCADE,
  title text NOT NULL,
  message text,
  alert_type text NOT NULL DEFAULT 'info',
  is_read boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_alerts_user ON public.alerts (user_id);
CREATE INDEX idx_alerts_unread ON public.alerts (user_id, is_read) WHERE is_read = false;

ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own alerts" ON public.alerts FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Authenticated users can create alerts" ON public.alerts FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own alerts" ON public.alerts FOR UPDATE TO authenticated USING (auth.uid() = user_id);

-- ===================
-- FUNCTIONS
-- ===================

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS trigger LANGUAGE plpgsql SET search_path TO 'public' AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public' AS $$
BEGIN
  INSERT INTO public.profiles (user_id, full_name)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data ->> 'full_name', NEW.email));
  RETURN NEW;
END;
$$;

-- ===================
-- TRIGGERS
-- ===================

CREATE TRIGGER update_entities_updated_at
  BEFORE UPDATE ON public.monitored_entities
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_profiles_updated_at
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Trigger on auth.users to auto-create profile (applied via Supabase dashboard)
-- CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users
--   FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ===================
-- EXTENSIONS
-- ===================

CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

-- ============================================================
-- DATA DUMP
-- ============================================================

-- ===================
-- profiles
-- ===================

INSERT INTO public.profiles (id, user_id, full_name, avatar_url, created_at, updated_at) VALUES
  ('36e51e13-e530-46df-8cc6-137f7890ca39', '660f63cf-69ca-4364-819d-b9577b8f3b15', 'Robinson Vespucio Vaz ', NULL, '2026-04-01T18:15:59.671823+00:00', '2026-04-01T18:15:59.671823+00:00');

-- ===================
-- monitored_entities
-- ===================

INSERT INTO public.monitored_entities (id, name, entity_type, description, keywords, is_active, created_by, created_at, updated_at) VALUES
  ('31a40ccf-36cd-4e08-b4a6-2e3787cbb31f', 'CGE-GO', 'orgao', 'Controladoria-Geral do Estado de Goiás', ARRAY['CGE Goiás','Controladoria-Geral do Estado de Goiás','Controladoria de Goiás','Controladoria Geral','Controladoria do Estado de Goiás'], true, '660f63cf-69ca-4364-819d-b9577b8f3b15', '2026-04-01T18:29:56.847041+00:00', '2026-04-04T23:46:48.823045+00:00');

INSERT INTO public.monitored_entities (id, name, entity_type, description, keywords, is_active, created_by, created_at, updated_at) VALUES
  ('cd9aea18-6914-42ba-a445-493895143fb0', 'SES-GO', 'orgao', NULL, ARRAY['Secretaria de Saúde de Goiás','saúde Goiás','secretário de saúde de goias','secretária de saúde de Goiás'], true, '660f63cf-69ca-4364-819d-b9577b8f3b15', '2026-04-02T11:40:34.436493+00:00', '2026-04-05T15:17:21.464216+00:00');

INSERT INTO public.monitored_entities (id, name, entity_type, description, keywords, is_active, created_by, created_at, updated_at) VALUES
  ('6750488b-4124-4cb5-b4e7-04e8f469724d', 'Ronaldo Caiado', 'outro', 'Governador', ARRAY['Ronaldo Caiado','Ronaldo Ramos Caiado','Governador de Goiás','Ex-Governador de Goiás','Deputado','Deputado Federal','Deputado Estaual','Senador'], true, '660f63cf-69ca-4364-819d-b9577b8f3b15', '2026-04-02T11:48:48.053889+00:00', '2026-04-03T11:28:33.361717+00:00');

INSERT INTO public.monitored_entities (id, name, entity_type, description, keywords, is_active, created_by, created_at, updated_at) VALUES
  ('4d7fcf64-66ec-49a7-8bc9-59138b2a26b0', 'Daniel Vilela', 'outro', NULL, ARRAY['Vice-Governador','Vice','Governador','Deputado','Deputado Estadual','Deputado Federal'], true, '660f63cf-69ca-4364-819d-b9577b8f3b15', '2026-04-03T11:27:31.569528+00:00', '2026-04-04T23:49:11.541509+00:00');

INSERT INTO public.monitored_entities (id, name, entity_type, description, keywords, is_active, created_by, created_at, updated_at) VALUES
  ('77db7951-a82c-494b-a644-74d67f5119fa', 'Governo de Goiás ', 'outro', 'Geral do Governo', ARRAY['Governo de Goiás','Governo do Estado de Goiás'], true, '660f63cf-69ca-4364-819d-b9577b8f3b15', '2026-04-04T13:46:22.199776+00:00', '2026-04-05T15:16:03.401551+00:00');

INSERT INTO public.monitored_entities (id, name, entity_type, description, keywords, is_active, created_by, created_at, updated_at) VALUES
  ('251e4910-5f4e-4ea4-a820-776f9f0bfcae', 'SEDUC-GO', 'orgao', 'Secretaria da Educação do Estado de Goiás', ARRAY['SEDUC Goiás','Secretaria da Educação de Goiás','secretária de educação de Goiás','secretário de educação de Goiás','Fátima Gavioli'], true, '660f63cf-69ca-4364-819d-b9577b8f3b15', '2026-04-04T13:49:12.042915+00:00', '2026-04-04T23:51:47.276525+00:00');

INSERT INTO public.monitored_entities (id, name, entity_type, description, keywords, is_active, created_by, created_at, updated_at) VALUES
  ('c21eb35f-6dfa-4c1d-bfc1-fc3dbbc0b7a5', 'Secretaria da Retomada', 'orgao', 'Secretaria da Retomada', ARRAY['SER-GO','Secretaria de Estão da Retomada','Retomada Goiás','secretário da Retomada','secretário César Moura','César Augusto Sotkeviciene Moura'], true, '660f63cf-69ca-4364-819d-b9577b8f3b15', '2026-04-04T13:52:58.435953+00:00', '2026-04-05T15:10:21.270887+00:00');

INSERT INTO public.monitored_entities (id, name, entity_type, description, keywords, is_active, created_by, created_at, updated_at) VALUES
  ('f7d497ee-e3c2-46b1-be7a-80a0283d415d', 'GOINFRA', 'autarquia', 'Agência Goiana de Infraestrutura e Transportes', ARRAY['Agência Goiana de Infraestrutura e Transportes','rodovias Goiás','obras rodoviárias'], true, '660f63cf-69ca-4364-819d-b9577b8f3b15', '2026-04-05T15:09:58.135246+00:00', '2026-04-05T15:09:58.135246+00:00');

INSERT INTO public.monitored_entities (id, name, entity_type, description, keywords, is_active, created_by, created_at, updated_at) VALUES
  ('f3b68d61-f145-4abc-8964-e70f5772e374', 'Goiás Turismo', 'autarquia', 'Agência Estadual de Turismo', ARRAY['Agência Estadual de Turismo','Roberto Naves e Siqueira','Roberto Naves','presidente'], true, '660f63cf-69ca-4364-819d-b9577b8f3b15', '2026-04-05T15:15:23.568152+00:00', '2026-04-05T15:15:23.568152+00:00');

-- ===================
-- news_items
-- ===================

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('e91d361a-9ef9-4609-ab49-3be56674fee9', '31a40ccf-36cd-4e08-b4a6-2e3787cbb31f', 'Controladoria - Portal Goiás', 'A página da Controladoria Geral do Estado (CGE-GO) no Portal Goiás apresenta os principais destaques da instituição, incluindo programas como o Compliance Público e Municipal, Embaixadores da Cidadania e Estudantes de Atitude. O portal também oferece acesso a ferramentas como o Portal da Transparência, Portal das Corregedorias e Ouvidoria, além de divulgar as últimas notícias da CGE-GO.', 'https://goias.gov.br/controladoria/', 'goias.gov.br', 'outro', 'positivo', ARRAY[]::text[], NULL, '2026-04-02T11:56:41.918265+00:00', '2026-04-02T11:56:41.918265+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('3b90cf6b-9f15-4f3f-b3dc-5fec429d68cb', '31a40ccf-36cd-4e08-b4a6-2e3787cbb31f', 'Quem entra e quem sai: veja as trocas possíveis e as já confirmadas no secretariado de Daniel Vilela', 'Daniel Vilela, ao assumir o governo de Goiás, anunciou mudanças em seu secretariado, com algumas trocas já confirmadas e outras em análise. Entre as alterações, destacam-se as substituições na Secretaria de Administração, Controladoria-Geral do Estado (CGE), Secretaria da Educação, Agência Goiana de Infraestrutura e Transportes (Goinfra) e Secretaria da Economia.', 'https://www.jornalopcao.com.br/ultimas-noticias/quem-entra-e-quem-sai-veja-as-trocas-possiveis-e-as-ja-confirmadas-no-secretariado-de-daniel-vilela-810712/', 'jornalopcao.com.br', 'substituicao', 'neutro', ARRAY['Daniel Vilela','Maguito Vilela','Ronaldo Caiado','Alan Farias Tavares','Francisco Sérvulo','Marcos Tadeu','Antônio Flávio de Oliveira','Fátima Gavioli','Helena Bezerra','Pedro Sales','Eliane Baltazar','Renata Noleto'], NULL, '2026-04-02T11:56:44.419318+00:00', '2026-04-02T11:56:44.419318+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('42d8d7c4-45aa-4f1d-a9e6-d625259db1c4', '31a40ccf-36cd-4e08-b4a6-2e3787cbb31f', 'Goiás: Daniel Vilela promove mudanças no secretariado e aposta em renovação da gestão', 'O vice-governador de Goiás, Daniel Vilela, está promovendo uma mini reforma administrativa no secretariado do estado. As mudanças incluem o aproveitamento de auxiliares, trocas estratégicas e indicações políticas, com o objetivo de dinamizar a gestão governamental.', 'https://sdnews.com.br/noticia/15538/goias-daniel-vilela-promove-mudancas-no-secretariado-e-aposta-em-renovacao-da-gestao.amp', 'sdnews.com.br', 'movimentacao', 'positivo', ARRAY['Daniel Vilela'], NULL, '2026-04-02T11:56:46.338863+00:00', '2026-04-02T11:56:46.338863+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('785a91db-73d1-49cf-ba70-0077a6c4aabf', '31a40ccf-36cd-4e08-b4a6-2e3787cbb31f', 'Talles Barreto requer título de cidadania para servidora pública', 'O deputado Talles Barreto (UB) propôs a concessão do Título de Cidadania Goiana à servidora pública Vânia Cristina Gonçalves da Silva, que atua como gerente de auditoria de monitoramento na Controladoria-Geral do Estado de Goiás (CGE-GO). A proposta reconhece a trajetória profissional e os serviços prestados por Vânia Gonçalves ao estado. O projeto de lei está em análise na Comissão de Constituição, Justiça e Redação (CCJ) da Assembleia Legislativa de Goiás.', 'https://portal.al.go.leg.br/noticias/163497/talles-barreto-requer-titulo-de-cidadania-para-servidora-publica', 'portal.al.go.leg.br', 'outro', 'positivo', ARRAY['Talles Barreto','Vânia Cristina Gonçalves da Silva'], NULL, '2026-04-02T11:56:47.99182+00:00', '2026-04-02T11:56:47.99182+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('da7654bf-5776-4ba0-9670-c62bbb32f97f', '31a40ccf-36cd-4e08-b4a6-2e3787cbb31f', 'Daniel aponta mais ajustes no secretariado', 'O governador de Goiás, Daniel Vilela, está realizando ajustes em seu secretariado, com 15 trocas no primeiro escalão até o momento. As mudanças incluem a nomeação de Antônio Flávio de Oliveira para a Controladoria-Geral do Estado (CGE) e uma dança das cadeiras nas Secretarias da Economia e da Administração (Sead), além da Goiás Parcerias. O governador busca oxigenar a gestão e elevar o padrão de qualidade na prestação de serviços.', 'https://www.seacgoias.com.br/seac/noticias/3245-daniel-aponta-mais-ajustes-no-secretariado/', 'seacgoias.com.br', 'movimentacao', 'neutro', ARRAY['Daniel Vilela','Antônio Flávio de Oliveira','Marcos Tadeu Andrade','Sérvulo Nogueira','Renata Lacerda Noleto','Alan Tavares','Diego de Oliveira Soares','Márcio Corrêa','Luiz Antônio de Oliveira Rosa','Francisco Jr'], NULL, '2026-04-02T11:56:49.926062+00:00', '2026-04-02T11:56:49.926062+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('deaf0753-e881-4a7f-bbe5-0ed05d217193', 'cd9aea18-6914-42ba-a445-493895143fb0', 'Governo de Goiás dobra número de UTIs certificadas e alcança reconhecimento nacional em qualidade assistencial', 'O Governo de Goiás dobrou o número de UTIs certificadas, alcançando reconhecimento nacional pela qualidade assistencial. A notícia destaca o avanço na saúde do estado, com foco na melhoria dos serviços de terapia intensiva.', 'https://goias.gov.br/saude/governo-de-goias-dobra-numero-de-utis-certificadas-e-alcanca-reconhecimento-nacional-em-qualidade-assistencial/', 'goias.gov.br', 'outro', 'positivo', ARRAY[]::text[], NULL, '2026-04-02T11:56:52.225217+00:00', '2026-04-02T11:56:52.225217+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('552c8ab3-c4ff-431a-8a94-2f64d36ed6d8', 'cd9aea18-6914-42ba-a445-493895143fb0', 'Confira funcionamento das unidades estaduais de saúde no feriado', 'A Secretaria de Estado da Saúde (SES) de Goiás divulgou o funcionamento das unidades estaduais de saúde durante o ponto facultativo e o feriado da Sexta-Feira Santa. Hospitais estaduais manterão atendimentos de urgência e emergência, enquanto serviços administrativos, consultas e exames ambulatoriais serão suspensos, com retorno na segunda-feira.', 'https://agenciacoradenoticias.go.gov.br/confira-funcionamento-das-unidades-estaduais-de-saude-no-feriado-2/', 'agenciacoradenoticias.go.gov.br', 'outro', 'neutro', ARRAY[]::text[], NULL, '2026-04-02T11:56:53.745096+00:00', '2026-04-02T11:56:53.745096+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('95fb9574-4955-47d0-a1c9-df2369e11572', 'cd9aea18-6914-42ba-a445-493895143fb0', 'Agir avança em projeto de maturidade digital e apresenta resultados à SES-GO', 'A Associação de Gestão, Inovação e Resultados em Saúde (Agir) apresentou à Secretaria de Estado da Saúde de Goiás (SES-GO) os avanços de seu projeto de maturidade digital e o progresso das unidades de saúde para a certificação HIMSS. O encontro contou com a presença de representantes da Agir e da SES-GO, que discutiram os benefícios da implementação de tecnologias e processos digitais, visando aprimorar a segurança e a qualidade do atendimento hospitalar.', 'https://www.agirsaude.org.br/noticia/view/4243/agir-avanca-em-projeto-de-maturidade-digital-e-apresenta-resultados-a-ses-go', 'agirsaude.org.br', 'outro', 'positivo', ARRAY['Guillermo Sócrates','Kelvin Cantarelli','Ana Paula Kenes','Thyago Gregório','Priscila Martins','Ana Carolina Rezende Abrahão','Luiselena Luna Esmeraldo','Amanda Melo','Diana Ferreira','Wermerson Rodrigues da Silva','Janaína Santos Rodrigues'], NULL, '2026-04-02T11:56:55.500697+00:00', '2026-04-02T11:56:55.500697+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('af3d1f92-acfd-49bc-9a27-c9070ad66b2c', '6750488b-4124-4cb5-b4e7-04e8f469724d', 'Ronaldo Caiado é escolhido pelo PSD como candidato à Presidência da República em 2026', 'O governador de Goiás, Ronaldo Caiado, foi anunciado pelo PSD como seu candidato à Presidência da República em 2026. Médico, líder ruralista e político experiente, Caiado construiu sua carreira com base em pautas conservadoras, agronegócio e segurança pública. A escolha gerou divergências internas no partido, com o governador do Rio Grande do Sul, Eduardo Leite, criticando a decisão por manter a polarização política.', 'https://www.jota.info/eleicoes/quem-e-ronaldo-caiado-escolhido-pelo-psd-para-ser-candidato-a-presidente', 'jota.info', 'outro', 'neutro', ARRAY['Ronaldo Caiado','Gilberto Kassab','Eduardo Leite'], NULL, '2026-04-02T11:56:57.906949+00:00', '2026-04-02T11:56:57.906949+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('2697fa32-7ee7-40f0-ac73-15d7ff38846a', '6750488b-4124-4cb5-b4e7-04e8f469724d', 'Caiado diz que precisa ''ampliar bases'' ao deixar governo de Goiás para tentar Presidência', 'Ronaldo Caiado, ao deixar o governo de Goiás, expressou a necessidade de ''ampliar bases'' em sua campanha para a Presidência. Ele minimizou a adesão inicial tímida de lideranças do PSD à sua candidatura, prometendo trabalhar para expandir seu apoio. A notícia aborda a estratégia política de Caiado e sua transição do governo estadual para a corrida presidencial.', 'https://valor.globo.com/politica/noticia/2026/03/31/caiado-diz-que-precisa-ampliar-bases-ao-deixar-governo-de-gois-para-tentar-presidncia.ghtml', 'valor.globo.com', 'outro', 'neutro', ARRAY['Ronaldo Caiado','Joelmir Tavares'], NULL, '2026-04-02T11:56:59.637543+00:00', '2026-04-02T11:56:59.637543+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('b792b10d-8f36-4215-9995-5e9cb06a0c7e', '6750488b-4124-4cb5-b4e7-04e8f469724d', 'Quem é Ronaldo Caiado, aposta do PSD para o Planalto em 2026', 'A notícia aborda o perfil de Ronaldo Caiado, governador de Goiás, e sua possível candidatura à presidência da República em 2026 pelo PSD. O texto explora sua trajetória política e as expectativas em torno de sua postulação ao cargo máximo do executivo federal.', 'https://www.congressoemfoco.com.br/noticia/117684/quem-e-ronaldo-caiado-aposta-do-psd-para-o-planalto-em-2026', 'congressoemfoco.com.br', 'outro', 'neutro', ARRAY['Ronaldo Caiado'], NULL, '2026-04-02T11:57:01.134614+00:00', '2026-04-02T11:57:01.134614+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('07b98da5-fc1a-4173-a118-e899f20e0c4c', '6750488b-4124-4cb5-b4e7-04e8f469724d', 'Ronaldo Caiado será o candidato do PSD', 'O governador de Goiás, Ronaldo Caiado, será anunciado como o candidato do PSD à Presidência da República. O anúncio está confirmado para as próximas horas, em uma entrevista coletiva em São Paulo.', 'https://platobr.com.br/ronaldo-caiado-sera-o-candidato-do-psd', 'platobr.com.br', 'outro', 'positivo', ARRAY['Ronaldo Caiado'], NULL, '2026-04-02T11:57:02.37117+00:00', '2026-04-02T11:57:02.37117+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('71efd97c-8af4-4f36-ae75-b4a4af130d89', '6750488b-4124-4cb5-b4e7-04e8f469724d', 'Eleições 2026: quem é Ronaldo Caiado, pré-candidato à presidência?', 'A notícia aborda a pré-candidatura de Ronaldo Caiado à presidência da República nas eleições de 2026. O governador de Goiás se lançou à disputa ainda em 2025 e trocou de partido. O texto apresenta a trajetória política de Caiado.', 'https://exame.com/brasil/eleicoes-2026-quem-e-ronaldo-caiado-pre-candidato-a-presidencia/', 'exame.com', 'outro', 'neutro', ARRAY['Ronaldo Caiado'], NULL, '2026-04-03T11:29:27.297114+00:00', '2026-04-03T11:29:27.297114+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('f1e76c47-68ea-42e7-b988-d4f296f2991b', '6750488b-4124-4cb5-b4e7-04e8f469724d', 'Autoridades dos três Poderes compõem mesa na posse do governador', 'A notícia detalha a composição da mesa de autoridades na sessão solene de posse do governador de Goiás, Ronaldo Caiado. Diversos representantes dos poderes Executivo, Legislativo e Judiciário, tanto estaduais quanto municipais e federais, estiveram presentes. Familiares do governador e do vice-governador também foram mencionados.', 'https://portal.al.go.leg.br/noticias/163526/autoridades-dos-tres-poderes-compoem-mesa-na-posse-do-governador', 'portal.al.go.leg.br', 'outro', 'positivo', ARRAY['Bruno Peixoto','Luciene Gontijo','Ronaldo Ramos Caiado','Gracinha Caiado','Daniel Elias Carvalho Vilela','Iara Netto Vilela','Leandro Crispim','Luciene Camargo','Sandro Mabel','Coronel Claudia','Vanderlan Cardoso','Flávia Morais','Eugênio José Cesário Rosa','Luiz Cláudio Veiga Braga','Cyro Terra','Allan Montoni Joos','Sebastião Tejota','Joaquim Alves de Castro Neto','José Délio Alves Júnior','Paulo Vitor Avelar','Ana Vitória Caiado','Marcela Caiado','Maria Caiado','Alexandre Hsiung','Vanessa Vilela','Miguel Vilela','Maria Laura Netto da Costa Vilela','Frederico Netto da Costa Vilela','Sandra Regina Carvalho Vilela','Tayrone de Melo'], NULL, '2026-04-03T11:29:29.867757+00:00', '2026-04-03T11:29:29.867757+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('8a3bf211-801e-4913-988d-d76431fd61fb', '4d7fcf64-66ec-49a7-8bc9-59138b2a26b0', 'Daniel Vilela toma posse como governador do Estado de Goiás', 'Daniel Vilela assumiu o governo de Goiás em sessão solene na Assembleia Legislativa, após a desincompatibilização de Ronaldo Caiado para disputar a Presidência. Em seu discurso, Vilela destacou a continuidade da gestão, os avanços do estado e o compromisso com o desenvolvimento, emocionando-se com a conquista e agradecendo a confiança de Caiado.', 'https://portal.al.go.leg.br/noticias/163542/daniel-vilela-toma-posse-como-governador-do-estado-de-goias', 'portal.al.go.leg.br', 'substituicao', 'positivo', ARRAY['Daniel Vilela','Ronaldo Caiado','Iara Netto Vilela','Bruno Peixoto','Maguito Vilela','Iris Rezende Machado'], NULL, '2026-04-03T11:30:02.688313+00:00', '2026-04-03T11:30:02.688313+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('c99c4b36-8079-4e29-b04c-c591608720e2', '4d7fcf64-66ec-49a7-8bc9-59138b2a26b0', 'Daniel Vilela assume Governo de Goiás após Caiado lançar pré-candidatura à Presidência', 'Com a pré-candidatura de Ronaldo Caiado à Presidência, Daniel Vilela, atual vice-governador, deve assumir o Governo de Goiás. A mudança já era esperada e ocorrerá após Caiado deixar oficialmente o cargo até o próximo sábado (4). Vilela, que já foi vereador, deputado estadual e federal, será empossado como governador do estado.', 'https://g1.globo.com/go/goias/eleicoes/2026/noticia/2026/03/30/com-pre-candidatura-de-caiado-a-presidencia-vice-daniel-vilela-deve-assumir-governo-de-goias.ghtml', 'g1.globo.com', 'movimentacao', 'positivo', ARRAY['Daniel Vilela','Ronaldo Caiado','Gilberto Kassab'], NULL, '2026-04-03T11:30:04.944984+00:00', '2026-04-03T11:30:04.944984+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('4a4f4c95-e597-48e6-8b13-d504b2dd3dfa', '4d7fcf64-66ec-49a7-8bc9-59138b2a26b0', 'Daniel Vilela assume Governo nesta terça-feira, 31, na Alego', 'Daniel Vilela assumirá o Governo de Goiás em 31 de março, após a desincompatibilização de Ronaldo Caiado para concorrer à Presidência. A solenidade de posse ocorrerá no Plenário Iris Rezende da Alego, com a presença de diversas autoridades. A cerimônia formaliza a continuidade administrativa do Poder Executivo estadual.', 'https://portal.al.go.leg.br/noticias/163462/daniel-vilela-toma-posse-nesta-terca-feira-31-na-assembleia', 'portal.al.go.leg.br', 'nomeacao', 'positivo', ARRAY['Daniel Vilela','Ronaldo Caiado','Iara Netto Vilela','Bruno Peixoto','Gracinha Caiado','Iris Rezende','Maguito Vilela'], NULL, '2026-04-03T11:30:06.678121+00:00', '2026-04-03T11:30:06.678121+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('8943f07f-8fc0-458f-9528-ed79a1b2cbf1', '4d7fcf64-66ec-49a7-8bc9-59138b2a26b0', 'Daniel Vilela é empossado Governador de Goiás', 'Daniel Vilela foi empossado como o novo governador de Goiás em 31 de março de 2026, após a renúncia de Ronaldo Caiado. A cerimônia, realizada na Assembleia Legislativa, contou com a presença de diversas autoridades e discursos que destacaram a trajetória de Caiado e os compromissos de Vilela com o estado.', 'https://www.youtube.com/watch?v=BGRkSqIRF68', 'youtube.com', 'nomeacao', 'positivo', ARRAY['Daniel Vilela','Bruno Peixoto','Ronaldo Caiado','Maguito Vilela','Amilton Filho','Monalisa Carneiro'], NULL, '2026-04-03T11:30:08.445139+00:00', '2026-04-03T11:30:08.445139+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('967738f7-688e-4e16-90b6-dc9054c280e9', '31a40ccf-36cd-4e08-b4a6-2e3787cbb31f', 'Governo promove mudanças no primeiro escalão', 'O Governo de Goiás anunciou mudanças no primeiro escalão a partir de abril, com o governador Daniel Vilela promovendo trocas pontuais que visam manter o perfil técnico da equipe e a continuidade das políticas públicas. As alterações incluem novos nomes para o Gabinete de Políticas Sociais, Secretaria da Economia, Secretaria da Educação e Secretaria da Infraestrutura, além da Secretaria da Administração.', 'https://agenciacoradenoticias.go.gov.br/governo-promove-mudancas-no-primeiro-escalao/?amp', 'agenciacoradenoticias.go.gov.br', 'movimentacao', 'positivo', ARRAY['Daniel Vilela','Iara Netto Vilela','Gracinha Caiado','Renata Lacerda','Sérvulo Nogueira','Helena da Costa Bezerra','Fátima Gavioli','Ricardo de Oliveira Silva','Adib Elias'], NULL, '2026-04-03T12:00:29.774705+00:00', '2026-04-03T12:00:29.774705+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('74972b59-5e15-419c-908e-13acd1184f7f', 'cd9aea18-6914-42ba-a445-493895143fb0', 'Sindsaúde/GO emite nota de posicionamento sobre crise no Hospital e Maternidade Célia Câmara', 'O Sindsaúde Goiás expressa preocupação com a crise no Hospital e Maternidade Célia Câmara, devido à falta de compromisso da Prefeitura de Goiânia e da Sociedade Beneficente São José (SBSJ). O contrato com a SBSJ foi suspenso e a gestão provisória foi repassada ao Instituto Patris, com o Secretário Municipal de Saúde de Goiânia, Luiz Gaspar Pellizzer, garantindo o pagamento das verbas rescisórias para cerca de 250 trabalhadores. A situação é agravada pela renovação do contrato emergencial com a SBSJ, mesmo com a SMS ciente da execução incompleta dos serviços, e pela redução dos repasses financeiros da Prefeitura às maternidades geridas por Organizações Sociais.', 'https://sindsaude.com.br/sindsaude-go-emite-nota-de-posicionamento-sobre-crise-no-hospital-e-maternidade-celia-camara/', 'sindsaude.com.br', 'midia_negativa', 'negativo', ARRAY['Luiz Gaspar Pellizzer'], NULL, '2026-04-03T12:01:36.496855+00:00', '2026-04-03T12:01:36.496855+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('9e10f0c2-0de9-4d0e-89bf-baa34d0fa7b8', 'cd9aea18-6914-42ba-a445-493895143fb0', 'Parceria entre Ministério da Saúde, SES-GO e instituições viabiliza Carreta Roda-Hans em municípios de Goiás', 'Uma parceria entre o Ministério da Saúde, a Secretaria de Estado da Saúde de Goiás (SES-GO) e outras instituições possibilitou a implementação da Carreta Roda-Hans em diversos municípios goianos. O projeto visa levar atendimento e diagnóstico de hanseníase para a população, reforçando a saúde pública no estado. A iniciativa demonstra um esforço conjunto para combater a doença e promover a saúde em Goiás.', 'https://goias.gov.br/saude/parceria-entre-ministerio-da-saude-ses-go-e-instituicoes-viabiliza-carreta-roda-hans-em-municipios-de-goias/', 'goias.gov.br', 'outro', 'positivo', ARRAY[]::text[], NULL, '2026-04-03T12:01:38.17915+00:00', '2026-04-03T12:01:38.17915+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('7f752d35-b6a1-431f-a0a1-0170ae1de974', 'cd9aea18-6914-42ba-a445-493895143fb0', 'Hospital e Maternidade Célia Câmara troca de gestão', 'A Secretaria Municipal de Saúde de Goiânia (SMS) suspendeu preventivamente o contrato com a Sociedade Beneficente São José (SBSJ), que administrava o Hospital e Maternidade Célia Câmara. A gestão da unidade foi assumida provisoriamente pelo Instituto Patris. A decisão ocorreu após uma reunião de urgência para discutir o restabelecimento dos atendimentos médicos na unidade.', 'https://www.jornalopcao.com.br/ultimas-noticias/hospital-e-maternidade-celia-camara-troca-de-gestao-apos-decisao-da-secretaria-de-saude-de-goiania-811173/', 'jornalopcao.com.br', 'movimentacao', 'neutro', ARRAY[]::text[], NULL, '2026-04-03T12:01:39.591177+00:00', '2026-04-03T12:01:39.591177+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('6a06c465-5a2d-4339-b6ec-e663eb593b3f', '6750488b-4124-4cb5-b4e7-04e8f469724d', 'Ronaldo Caiado será lançado pré-candidato ao Planalto por Kassab', 'O governador de Goiás, Ronaldo Caiado, será lançado como pré-candidato à presidência da República por Gilberto Kassab. O anúncio oficial está previsto para ocorrer em São Paulo. Esta movimentação política indica a entrada de Caiado na corrida presidencial.', 'https://oglobo.globo.com/politica/noticia/2026/03/30/ronaldo-caiado-sera-lancado-pre-candidato-ao-planalto-por-kassab.ghtml', 'oglobo.globo.com', 'outro', 'positivo', ARRAY['Ronaldo Caiado','Gilberto Kassab'], NULL, '2026-04-04T12:00:14.228888+00:00', '2026-04-04T12:00:14.228888+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('9f2b5c8b-9e5e-4f34-96b6-8ba4adc92b4f', '6750488b-4124-4cb5-b4e7-04e8f469724d', 'Lula, Flávio, Caiado e mais: veja quem deve concorrer a presidente neste ano', 'A notícia apresenta uma lista de possíveis candidatos à presidência da República, incluindo Luiz Inácio Lula da Silva, Flávio Bolsonaro e Ronaldo Caiado. Ronaldo Caiado, governador de Goiás, é mencionado como pré-candidato ao Palácio do Planalto, tendo deixado o governo do estado para essa finalidade e sido escolhido pelo PSD para a disputa.', 'https://noticias.r7.com/eleicoes/2026/fotos/lula-flavio-caiado-e-mais-veja-quem-deve-concorrer-a-presidente-neste-ano-04042026/', 'noticias.r7.com', 'outro', 'neutro', ARRAY['Luiz Inácio Lula da Silva','Flávio Nantes Bolsonaro','Ronaldo Ramos Caiado','Geraldo Alckmin','Jair Bolsonaro','Gilberto Kassab','Romeu Zema Neto'], NULL, '2026-04-04T12:00:15.756229+00:00', '2026-04-04T12:00:15.756229+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('51e23ee6-7168-45e8-b137-74882362386f', '4d7fcf64-66ec-49a7-8bc9-59138b2a26b0', 'Daniel Vilela é o novo governador de Goiás', 'A notícia informa sobre a posse de Daniel Vilela como o novo governador de Goiás. No entanto, o conteúdo principal da página é sobre a política de cookies do site, não fornecendo detalhes sobre a posse ou o novo governo.', 'https://goias.gov.br/daniel-vilela-e-o-novo-governador-de-goias/', 'goias.gov.br', 'outro', 'neutro', ARRAY['Daniel Vilela'], NULL, '2026-04-04T12:00:31.676941+00:00', '2026-04-04T12:00:31.676941+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('0bc7352e-ec02-4b03-8199-312d1287d053', '31a40ccf-36cd-4e08-b4a6-2e3787cbb31f', 'Daniel Vilela promove 15 mudanças no secretariado e redefine primeiro escalão', 'O governador Daniel Vilela (MDB) realizou 15 mudanças no secretariado estadual, redefinindo o primeiro escalão do governo de Goiás. As alterações ocorrem principalmente devido à desincompatibilização de auxiliares que disputarão as eleições, mas também incluem remanejamentos e escolhas próprias do novo governador. As mudanças abrangem áreas estratégicas como Economia, Educação, Infraestrutura, Segurança e Desenvolvimento.', 'https://www.jornalopcao.com.br/politica/daniel-vilela-promove-15-mudancas-no-secretariado-e-redefine-primeiro-escalao-811381/', 'jornalopcao.com.br', 'movimentacao', 'neutro', ARRAY['Daniel Vilela','Paulo Henrique da Farmácia','Roberto Naves','Iara Netto Vilela','Gracinha Caiado','Renata Lacerda','Sérvulo Nogueira','Eliane Simon','Ronaldo Caiado'], NULL, '2026-04-04T13:42:39.389959+00:00', '2026-04-04T13:42:39.389959+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('576931df-7266-45d5-a719-20103fefa76d', 'cd9aea18-6914-42ba-a445-493895143fb0', 'Secretaria de saúde afirma que atendimento no Célia Câmara volta à normalidade em 10 dias', 'A Secretaria de Saúde de Goiás informou que o atendimento na maternidade Célia Câmara será normalizado em dez dias. A Organização Social (OS) responsável pela administração da maternidade foi substituída após sérios problemas relacionados à falta de médicos. A medida visa restabelecer a qualidade dos serviços prestados à população.', 'https://globoplay.globo.com/v/14491497/', 'globoplay.globo.com', 'movimentacao', 'positivo', ARRAY[]::text[], NULL, '2026-04-04T13:42:48.659867+00:00', '2026-04-04T13:42:48.659867+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('2b5de5c6-dfa4-4661-9edd-0a5a96fbd503', '77db7951-a82c-494b-a644-74d67f5119fa', 'Ronaldo Caiado deixa governo de Goiás; Daniel Vilela assume cargo', 'Ronaldo Caiado deixou o governo de Goiás para se dedicar à pré-candidatura à Presidência pelo PSD. Em seu lugar, o vice-governador Daniel Vilela (MDB) assumiu o cargo em cerimônia na Assembleia Legislativa de Goiás (Alego). A transição ocorreu de forma rápida e sem discursos, com Daniel Vilela prestando juramento e assinando o documento de posse.', 'https://g1.globo.com/go/goias/eleicoes/2026/noticia/2026/03/31/ronaldo-caiado-deixa-governo-e-transfere-cargo-a-daniel-vilela.ghtml', 'g1.globo.com', 'substituicao', 'neutro', ARRAY['Ronaldo Caiado','Daniel Vilela'], NULL, '2026-04-04T13:55:37.581957+00:00', '2026-04-04T13:55:37.581957+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('50cf8e50-541a-4adb-8734-86f8b3cfc7f3', '77db7951-a82c-494b-a644-74d67f5119fa', 'Daniel Vilela assume governo de Goiás nesta terça-feira em solenidade na Alego', 'Daniel Vilela assume o governo de Goiás nesta terça-feira em uma solenidade na Assembleia Legislativa de Goiás (Alego). A cerimônia marca a entrega formal da carta de renúncia de Ronaldo Caiado e a posse do vice no cargo de governador. A notícia detalha os procedimentos da transição de poder no estado.', 'https://globoplay.globo.com/v/14479906/', 'globoplay.globo.com', 'movimentacao', 'positivo', ARRAY['Daniel Vilela','Ronaldo Caiado'], NULL, '2026-04-04T13:55:39.264596+00:00', '2026-04-04T13:55:39.264596+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('363e00b3-db4e-455c-ab54-3520ac2657f0', '251e4910-5f4e-4ea4-a820-776f9f0bfcae', 'Nova etapa do programa Profissionaliza Goiás deve beneficiar 4,9 mil jovens das escolas estaduais em 2026', 'A notícia aborda a nova etapa do programa Profissionaliza Goiás, que visa beneficiar 4,9 mil jovens de escolas estaduais em 2026. O programa busca oferecer qualificação profissional aos estudantes, preparando-os para o mercado de trabalho. A iniciativa é do governo de Goiás e demonstra um investimento na educação e futuro dos jovens do estado.', 'https://goias.gov.br/educacao/nova-etapa-do-programa-profissionaliza-goias-deve-beneficiar-49-mil-jovens-das-escolas-estaduais-em-2026/', 'goias.gov.br', 'outro', 'positivo', ARRAY[]::text[], NULL, '2026-04-04T13:55:56.135+00:00', '2026-04-04T13:55:56.135+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('82f2afd4-fdc2-4f91-8a82-ba063e4e66dd', '251e4910-5f4e-4ea4-a820-776f9f0bfcae', 'Quadra poliesportiva é inaugurada em Itarumã e reforça investimentos da Seduc/GO na Educação goiana', 'Uma nova quadra poliesportiva foi inaugurada em Itarumã, marcando um reforço nos investimentos da Secretaria de Estado da Educação de Goiás (Seduc/GO) na educação do estado. A iniciativa visa melhorar a infraestrutura escolar e oferecer mais oportunidades para os estudantes. A inauguração demonstra o compromisso do governo de Goiás com o desenvolvimento educacional.', 'https://goias.gov.br/educacao/quadra-poliesportiva-e-inaugurada-em-itaruma-e-reforca-investimentos-da-seduc-go-na-educacao-goiana/', 'goias.gov.br', 'outro', 'positivo', ARRAY[]::text[], NULL, '2026-04-04T13:55:58.127234+00:00', '2026-04-04T13:55:58.127234+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('5d6fc9c9-1476-4ca7-abf0-ead34d3c116d', '251e4910-5f4e-4ea4-a820-776f9f0bfcae', 'Nova etapa do programa Profissionaliza Goiás deve beneficiar 4,9 mil jovens das escolas estaduais em 2026', 'O programa Profissionaliza Goiás, uma iniciativa do governo estadual, está se preparando para uma nova fase que visa beneficiar 4,9 mil jovens de escolas estaduais em 2026. Este programa busca oferecer qualificação profissional para estudantes, preparando-os para o mercado de trabalho. A expansão do programa demonstra o compromisso do estado com a educação e o desenvolvimento profissional de seus jovens.', 'https://goias.gov.br/educacao/nova-etapa-do-programa-profissionaliza-goias-deve-beneficiar-49-mil-jovens-das-escolas-estaduais-em-2026/', 'goias.gov.br', 'outro', 'positivo', ARRAY[]::text[], NULL, '2026-04-04T13:55:58.870233+00:00', '2026-04-04T13:55:58.870233+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('b71ebc06-e7dc-4b3a-8266-b2db9a0439eb', '251e4910-5f4e-4ea4-a820-776f9f0bfcae', 'Governo de Goiás inicia distribuição gratuita de agendas escolares', 'A Secretaria de Educação de Goiás (Seduc/GO) iniciou a distribuição gratuita de 85 mil agendas escolares de 2026 para os Colégios Estaduais da Polícia Militar (CEPMGs), um investimento de R$ 1,5 milhão. Esta é a primeira vez que todos os estudantes dos CEPMGs recebem agendas gratuitamente, visando auxiliar na organização escolar e na comunicação entre escola e família. A ação foi destacada pela comandante de ensino dos CEPMGs, tenente-coronel Quéren Leles, e pela secretária da Educação, Fátima Gavioli.', 'https://www.portalcaldas.com.br/noticia/governo-de-goias-inicia-distribuicao-gratuita-de-agendas-escolares-de-2026-para-os-cepmgs', 'portalcaldas.com.br', 'outro', 'positivo', ARRAY['Quéren Leles','Fátima Gavioli'], NULL, '2026-04-04T13:56:00.141354+00:00', '2026-04-04T13:56:00.141354+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('c28bb0b7-3690-4d64-85ba-a68b2040e7b7', '251e4910-5f4e-4ea4-a820-776f9f0bfcae', 'Quadra poliesportiva é inaugurada em Itarumã e reforça investimentos da Seduc-GO na educação goiana', 'A Secretaria de Estado da Educação de Goiás (Seduc-GO) inaugurou uma quadra poliesportiva em Itarumã, reforçando seus investimentos na educação do estado. A nova infraestrutura visa proporcionar melhores condições para a prática de atividades físicas e esportivas aos estudantes. Este projeto faz parte de uma série de ações da Seduc-GO para aprimorar a infraestrutura educacional em Goiás.', 'https://goias.gov.br/educacao/quadra-poliesportiva-e-inaugurada-em-itaruma-e-reforca-investimentos-da-seduc-go-na-educacao-goiana/', 'goias.gov.br', 'outro', 'positivo', ARRAY[]::text[], NULL, '2026-04-04T13:56:01.010079+00:00', '2026-04-04T13:56:01.010079+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('3156b674-d1d8-4130-bfc5-aa30a447b60d', '251e4910-5f4e-4ea4-a820-776f9f0bfcae', 'Governo de Goiás inicia distribuição gratuita de agendas escolares', 'A Secretaria de Educação de Goiás (Seduc/GO) iniciou a distribuição gratuita de 85 mil agendas escolares de 2026 para os Colégios Estaduais da Polícia Militar (CEPMGs). A ação, que representa um investimento de R$ 1,5 milhão, visa fornecer um material essencial para a organização escolar dos estudantes, especialmente os mais vulneráveis. A comandante de ensino dos CEPMGs, tenente-coronel Quéren Leles, e a secretária da Educação, Fátima Gavioli, destacaram a importância das agendas como ferramenta de comunicação e gestão pedagógica.', 'https://www.portalcaldas.com.br/noticia/governo-de-goias-inicia-distribuicao-gratuita-de-agendas-escolares-de-2026-para-os-cepmgs', 'portalcaldas.com.br', 'outro', 'positivo', ARRAY['Quéren Leles','Fátima Gavioli'], NULL, '2026-04-04T13:56:02.648725+00:00', '2026-04-04T13:56:02.648725+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('be0e3817-f9fa-4364-803c-828bfa0204ee', 'c21eb35f-6dfa-4c1d-bfc1-fc3dbbc0b7a5', 'Convênio entre Estado de Goiás e Município de Hidrolândia para o 5º Festival do Cordeiro e 3ª Top Agro', 'O Estado de Goiás, por meio da Secretaria de Estado da Retomada, e o Município de Hidrolândia celebraram um convênio para viabilizar a realização do 5º Festival do Cordeiro e da 3ª Top Agro, que ocorrerão de 01 a 04 de abril de 2026. O evento visa promover lazer, cultura, integração social e fomentar a economia local, fortalecendo o comércio, o turismo e a cadeia produtiva de eventos na região.', 'https://goias.gov.br/retomada/wp-content/uploads/sites/22/2026/03/DOCUMENTOS-CONVENIO-19-HIDROLANDIA.pdf', 'goias.gov.br', 'outro', 'positivo', ARRAY['César Augusto de Sotkeviciene Moura','José Délio Alves Junior'], NULL, '2026-04-04T13:56:32.871652+00:00', '2026-04-04T13:56:32.871652+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('feab2bf7-ece1-4184-82ce-3d0dd07860ee', 'c21eb35f-6dfa-4c1d-bfc1-fc3dbbc0b7a5', 'Convênio entre o Estado de Goiás e o Município de Jaraguá para o Tour de Ciclismo', 'O Estado de Goiás, por meio da Secretaria de Estado da Retomada, e o Município de Jaraguá celebraram um convênio para apoiar a 6ª edição do Tour de Jaraguá de Ciclismo, que ocorrerá em março de 2026. O objetivo é incentivar o esporte, promover a integração social, fomentar o turismo e dinamizar a economia local, com a disponibilização de infraestrutura e suporte operacional para o evento.', 'https://goias.gov.br/retomada/wp-content/uploads/sites/22/2026/03/DOCUMENTOS-CONVENIO-20-JARAGUA.pdf', 'goias.gov.br', 'outro', 'positivo', ARRAY['César Augusto de Sotkeviciene Moura','Paulo Vitor Avelar'], NULL, '2026-04-04T13:56:34.622605+00:00', '2026-04-04T13:56:34.622605+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('cb22e9a8-7466-4512-bc13-314c607065fb', 'c21eb35f-6dfa-4c1d-bfc1-fc3dbbc0b7a5', 'Convênio entre Secretaria da Retomada e Município de Planaltina para Expo-Gospel e Aniversário da Cidade', 'A Secretaria de Estado da Retomada de Goiás e o Município de Planaltina celebraram um convênio para apoiar financeiramente a realização da Expo-Gospel e as comemorações do 135º Aniversário de Planaltina. O objetivo é promover eventos de interesse público e estimular a economia local através da geração de empregos e dinamização da renda. O convênio prevê o custeio de apresentações musicais de grande porte nos dias 28 e 29 de março de 2026.', 'https://goias.gov.br/retomada/wp-content/uploads/sites/22/2026/03/DOCUMENTOS-CONVENIO-17-PLANALTINA.pdf', 'goias.gov.br', 'outro', 'positivo', ARRAY['César Augusto de Sotkeviciene Moura','CRISTIOMARIO DE SOUSA MEDEIROS'], NULL, '2026-04-04T23:53:14.215789+00:00', '2026-04-04T23:53:14.215789+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('3d2a0edb-f5cb-4465-a027-0118c944eb3e', '251e4910-5f4e-4ea4-a820-776f9f0bfcae', 'Fátima Gavioli deixa Secretaria de Educação de Goiás após 7 anos', 'Fátima Gavioli se despede da Secretaria de Educação de Goiás após sete anos de atuação. Helena Bezerra assume o cargo, marcando uma mudança na liderança da pasta. A transição ocorre em um momento de continuidade para a educação do estado.', 'https://www.e1.app.br/noticia/22539/goias/fatima-gavioli-deixa-secretaria-de-educacao-de-goias-apos-7-anos-helena-bezerra-assume.html', 'e1.app.br', 'substituicao', 'neutro', ARRAY['Fátima Gavioli','Helena Bezerra'], NULL, '2026-04-04T23:53:22.677787+00:00', '2026-04-04T23:53:22.677787+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('e40a1611-d6b9-461e-95c1-c8a949f73bdf', '251e4910-5f4e-4ea4-a820-776f9f0bfcae', 'Com saída de Fátima Gavioli, Helena Bezerra deve ser a nova titular da Seduc', 'A notícia sugere que Helena Bezerra pode assumir a Secretaria de Educação de Goiás (Seduc-GO) após a saída de Fátima Gavioli. Embora o conteúdo da notícia não esteja disponível, o título indica uma possível mudança na liderança da Seduc-GO.', 'https://diretodoplenario.com.br/noticia/13365/com-saida-de-fatima-gavioli-helena-bezerra-deve-ser-a-nova-titular-da-seduc.html', 'diretodoplenario.com.br', 'substituicao', 'neutro', ARRAY['Fátima Gavioli','Helena Bezerra'], NULL, '2026-04-04T23:53:24.50247+00:00', '2026-04-04T23:53:24.50247+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('eb093805-0d8e-4016-9c96-2d2d640c8bb6', 'cd9aea18-6914-42ba-a445-493895143fb0', 'Secretaria de saúde afirma que atendimento no Célia Câmara volta à normalidade em 10 dias', 'A Secretaria de Saúde de Goiás (SES-GO) informou que o atendimento na maternidade Célia Câmara será normalizado em dez dias. A Organização Social (OS) responsável pela administração da unidade foi substituída devido a problemas graves, incluindo a falta de médicos.', 'https://g1.globo.com/go/goias/videos-bom-dia-go/video/secretaria-de-saude-afirma-que-atendimento-no-celia-camara-volta-a-normalidade-em-10-dias-14491497.ghtml', 'g1.globo.com', 'substituicao', 'positivo', ARRAY[]::text[], NULL, '2026-04-04T23:53:39.143899+00:00', '2026-04-04T23:53:39.143899+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('94258f54-4c39-4530-a8ce-b0ce6318792e', 'cd9aea18-6914-42ba-a445-493895143fb0', 'Entregues reforma, modernização e ampliação do Heana, em Anápolis', 'O governador Ronaldo Caiado entregou a reforma, modernização e ampliação do Hospital Estadual de Anápolis Dr. Henrique Santillo (Heana). Os investimentos, superiores a R$ 3,1 milhões, contemplaram a nova UTI adulta e a ampliação do Serviço de Diagnóstico por Imagem. O Heana é referência em média e alta complexidade para a região Centro-Norte goiana.', 'https://goias.gov.br/entregue-reforma-modernizacao-e-ampliacao-do-heana-em-anapolis/', 'goias.gov.br', 'outro', 'positivo', ARRAY['Ronaldo Caiado'], NULL, '2026-04-04T23:53:40.99083+00:00', '2026-04-04T23:53:40.99083+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('774936d8-b5de-43e6-bc9f-b136d2c2eac5', 'cd9aea18-6914-42ba-a445-493895143fb0', 'Prédio no Centro de Goiânia abrigará Secretaria de Saúde e outras pastas, anuncia Governo de Goiás', 'O Governo de Goiás anunciou que um edifício na Avenida Anhanguera, no Centro de Goiânia, será o novo Centro Administrativo, abrigando a Secretaria de Saúde (SES), Secretaria da Administração (Sead) e o Procon Goiás. A mudança, que começará em julho com o Procon e se estenderá aos outros órgãos após reforma em janeiro do próximo ano, visa economizar mais de R$ 21 milhões anuais em aluguéis e manutenções. O governador Ronaldo Caiado e o vice Daniel Vilela destacaram a modernização e eficiência da máquina pública com a nova sede.', 'https://opopular.com.br/cidades/predio-no-centro-de-goiania-abrigara-secretaria-de-saude-e-outras-pastas-anuncia-governo-de-goias-1.3392915', 'opopular.com.br', 'movimentacao', 'positivo', ARRAY['Ronaldo Caiado','Daniel Vilela'], NULL, '2026-04-04T23:53:43.133143+00:00', '2026-04-04T23:53:43.133143+00:00');

INSERT INTO public.news_items (id, entity_id, title, content, source_url, source_name, classification, sentiment, people_mentioned, published_at, collected_at, created_at) VALUES
  ('6ef74ccb-fe0b-4522-b805-21b2cd637b17', '31a40ccf-36cd-4e08-b4a6-2e3787cbb31f', 'Goiás: Daniel Vilela promove mudanças no secretariado e aposta em renovação da gestão', 'A notícia original não contém o conteúdo completo sobre as mudanças no secretariado de Daniel Vilela, apenas o título e links para outras notícias. Portanto, não é possível resumir as mudanças ou identificar as pessoas envolvidas.', 'https://sdnews.com.br/noticia/15538/goias-daniel-vilela-promove-mudancas-no-secretariado-e-aposta-em-renovacao-da-gestao.html', 'sdnews.com.br', 'outro', 'neutro', ARRAY[]::text[], NULL, '2026-04-05T00:00:06.374261+00:00', '2026-04-05T00:00:06.374261+00:00');


-- Fim do dump