# Monitor Goiás — Guia de Utilização do Sistema

**Versão:** 1.1  
**Data:** 2026-04-05

---

## Sumário

1. [Visão Geral](#1-visão-geral)
2. [Acesso ao Sistema](#2-acesso-ao-sistema)
3. [Páginas do Sistema](#3-páginas-do-sistema)
   - 3.1 [Dashboard](#31-dashboard)
   - 3.2 [Entidades Monitoradas](#32-entidades-monitoradas)
   - 3.3 [Notícias](#33-notícias)
   - 3.4 [Alertas](#34-alertas)
   - 3.5 [Grafo de Relacionamentos](#35-grafo-de-relacionamentos)
   - 3.6 [Configurações](#36-configurações)
4. [Cadastro de Entidades](#4-cadastro-de-entidades)
   - 4.1 [Campos do Formulário](#41-campos-do-formulário)
   - 4.2 [Palavras-chave: Como Funcionam](#42-palavras-chave-como-funcionam)
   - 4.3 [Exemplos Práticos de Palavras-chave](#43-exemplos-práticos-de-palavras-chave)
   - 4.4 [Boas Práticas no Cadastro](#44-boas-práticas-no-cadastro)
5. [Fluxo de Coleta e Processamento de Notícias](#5-fluxo-de-coleta-e-processamento-de-notícias)
   - 5.1 [Etapa 1: Construção da Busca](#51-etapa-1-construção-da-busca)
   - 5.2 [Etapa 2: Busca na Web (Firecrawl)](#52-etapa-2-busca-na-web-firecrawl)
   - 5.3 [Etapa 3: Deduplicação](#53-etapa-3-deduplicação)
   - 5.4 [Etapa 4: Classificação por IA](#54-etapa-4-classificação-por-ia)
   - 5.5 [Etapa 5: Armazenamento e Alertas](#55-etapa-5-armazenamento-e-alertas)
6. [Classificações e Sentimentos](#6-classificações-e-sentimentos)
7. [Coleta Automática (Cron Job)](#7-coleta-automática-cron-job)
8. [Dicas para Máximo Aproveitamento](#8-dicas-para-máximo-aproveitamento)
9. [Perguntas Frequentes (FAQ)](#9-perguntas-frequentes-faq)

---

## 1. Visão Geral

O **Monitor Goiás** é um sistema de monitoramento automatizado de notícias sobre órgãos, autarquias, fundações e entidades públicas do estado de Goiás. Ele busca notícias na internet, classifica-as automaticamente por meio de inteligência artificial e gera alertas quando conteúdos relevantes são detectados — especialmente mídias negativas.

### Principais funcionalidades

- **Monitoramento contínuo** de entidades públicas na mídia e redes sociais (X, Instagram, Facebook)
- **Classificação automática** de notícias por tipo (nomeação, exoneração, mídia negativa, etc.)
- **Análise de sentimento** (positivo, negativo, neutro)
- **Identificação de pessoas** mencionadas nas notícias
- **Alertas automáticos** para notícias de mídia negativa
- **Coleta programada** a cada 6 horas, sem intervenção manual
- **Grafo de relacionamentos** para visualizar conexões entre entidades, notícias e pessoas

---

## 2. Acesso ao Sistema

1. Acesse a URL do sistema no navegador.
2. Na tela de autenticação, cadastre-se com e-mail e senha ou faça login com uma conta existente.
3. Após confirmar seu e-mail, você terá acesso completo ao sistema.

> **Importante:** É necessário confirmar o e-mail de cadastro antes do primeiro acesso.

---

## 3. Páginas do Sistema

### 3.1 Dashboard

A página inicial apresenta uma **visão geral** com:

- **Contadores resumidos:** total de notícias coletadas, entidades monitoradas, alertas pendentes e mídias negativas.
- **Distribuição por classificação:** quantas notícias de cada tipo foram coletadas.
- **Notícias recentes:** as 5 últimas notícias com título, entidade associada, sentimento e classificação.
- **Botão "Coletar Notícias":** dispara uma coleta manual imediata para todas as entidades ativas.

### 3.2 Entidades Monitoradas

Página para **gerenciar** os órgãos e entidades que o sistema monitora:

- **Criar** novas entidades com nome, tipo, descrição e palavras-chave.
- **Editar** entidades existentes.
- **Ativar/Desativar** o monitoramento de cada entidade (switch liga/desliga).
- **Excluir** entidades que não são mais necessárias.

> Apenas entidades **ativas** são incluídas nas coletas de notícias.

### 3.3 Notícias

Lista completa de todas as notícias coletadas, com:

- **Busca textual:** filtre por palavras no título ou conteúdo.
- **Filtro por entidade:** selecione uma entidade específica para ver apenas suas notícias.
- **Filtro por classificação:** selecione um tipo específico (ex: apenas "Nomeação").
- **Filtro por sentimento:** veja apenas notícias positivas, negativas ou neutras.
- **Link externo:** acesse a notícia original na fonte.
- **Pessoas mencionadas:** veja quem foi citado em cada notícia.
- **Botão "Coletar Notícias":** também disponível nesta página.

> **Dica:** Combine os filtros para análises mais específicas. Por exemplo, selecione uma entidade e filtre por "Mídia Negativa" para ver apenas as notícias negativas daquela entidade.

### 3.4 Alertas

Exibe notificações geradas automaticamente pelo sistema:

- Alertas são criados quando uma notícia de **sentimento negativo** ou **classificação "mídia negativa"** é coletada.
- Cada alerta pode ser marcado como **lido** individualmente ou em lote ("Marcar todos como lidos").
- Alertas lidos aparecem com opacidade reduzida.

> **Nota:** Alertas automáticos são gerados apenas em coletas manuais (quando há um usuário autenticado). Coletas via cron job não geram alertas porque não há contexto de usuário.

### 3.5 Grafo de Relacionamentos

Visualização interativa das conexões entre notícias, entidades e pessoas mencionadas, utilizando um grafo de forças (force-directed graph):

- **Nós de Notícia (círculos):** cada notícia é representada por um círculo colorido de acordo com sua classificação (ex: vermelho para mídia negativa, verde para nomeação).
- **Nós de Entidade (quadrados):** entidades monitoradas aparecem como quadrados azuis, conectados às notícias em que são mencionadas.
- **Nós de Pessoa (losangos):** pessoas mencionadas nas notícias aparecem como losangos roxos, com links para cada notícia que as cita.
- **Legenda:** painel superior mostra as cores e formas usadas para cada tipo de nó e classificação.
- **Estatísticas:** contadores de notícias, entidades, pessoas e conexões exibidos na parte inferior.
- **Interatividade:** arraste nós, amplie/reduza o zoom e passe o mouse para ver rótulos.

> **Uso:** O grafo permite identificar rapidamente padrões como pessoas que aparecem em múltiplas entidades, entidades com muitas notícias negativas, ou clusters de notícias relacionadas.

### 3.6 Configurações

Página de configurações gerais:

- **Perfil:** edite seu nome completo e visualize seu e-mail.
- **Coleta Automática:** informações sobre o status e frequência do cron job.
- **Visão Geral do Sistema:** estatísticas (total de entidades, notícias coletadas, entidades ativas).
- **Entidades Cadastradas:** lista resumida com status de cada entidade.

---

## 4. Cadastro de Entidades

### 4.1 Campos do Formulário

| Campo | Obrigatório | Descrição |
|-------|:-----------:|-----------|
| **Nome** | Sim | Nome oficial da entidade. Ex: "Secretaria de Saúde de Goiás" |
| **Tipo** | Sim | Classificação institucional: Órgão, Autarquia, Fundação, Empresa Pública, Soc. Economia Mista ou Outro |
| **Descrição** | Não | Texto livre para contextualização. Ex: "Responsável pela gestão da saúde pública estadual" |
| **Palavras-chave** | Não (recomendado) | Termos adicionais de busca, separados por vírgula |

### 4.2 Palavras-chave: Como Funcionam

As palavras-chave são um dos elementos mais importantes para a qualidade da coleta. Entender como elas funcionam é essencial:

#### Como a busca é construída

O sistema monta **4 consultas de busca** para cada entidade:

```
Busca web:       {Nome da Entidade} OR {Palavra-chave 1} OR {Palavra-chave 2} OR ... Goiás notícia
Busca X/Twitter: site:x.com {Nome da Entidade} OR {Palavra-chave 1} OR ... Goiás
Busca Instagram: site:instagram.com {Nome da Entidade} OR {Palavra-chave 1} OR ... Goiás
Busca Facebook:  site:facebook.com {Nome da Entidade} OR {Palavra-chave 1} OR ... Goiás
```

**Detalhes importantes:**

1. **O nome da entidade é SEMPRE incluído automaticamente.** Você **não precisa** repetir o nome da entidade nas palavras-chave — ele já faz parte da busca.

2. **As palavras-chave são combinadas com OR (OU).** Isso significa que cada palavra-chave é pesquisada **individualmente** como alternativa. Se você cadastrar "SES-GO, secretário da saúde", o sistema buscará notícias que mencionem o nome da entidade **OU** "SES-GO" **OU** "secretário da saúde".

3. **O termo "Goiás notícia" é adicionado automaticamente** na busca web. Nas redes sociais, apenas "Goiás" é adicionado.

4. **A busca é limitada à última semana** (parâmetro `tbs: qdr:w`), garantindo que apenas notícias recentes sejam coletadas.

5. **Cada entidade gera 4 buscas independentes** (web + 3 redes sociais). Os resultados são combinados e deduplicados por URL antes do processamento.

#### O que as palavras-chave devem conter

- **Siglas** do órgão (ex: SES-GO, SEDI, GOINFRA)
- **Nomes de dirigentes** importantes (ex: nome do secretário)
- **Variações do nome** que a mídia costuma usar (ex: "Secretaria da Saúde" vs "Sec. Saúde")
- **Termos específicos** que identifiquem a entidade (ex: "hospital estadual")

#### O que as palavras-chave NÃO devem conter

- **O nome completo da entidade** (já é incluído automaticamente)
- **Termos genéricos demais** (ex: "governo", "Goiás" — já fazem parte da busca)
- **Frases longas** — prefira termos curtos e objetivos

### 4.3 Exemplos Práticos de Palavras-chave

#### Exemplo 1: Secretaria de Saúde de Goiás

| Campo | Valor |
|-------|-------|
| Nome | Secretaria de Saúde de Goiás |
| Palavras-chave | `SES-GO, secretário da saúde, saúde pública estadual` |

**Busca gerada:**
```
Secretaria de Saúde de Goiás OR SES-GO OR secretário da saúde OR saúde pública estadual Goiás notícia
```

#### Exemplo 2: GOINFRA

| Campo | Valor |
|-------|-------|
| Nome | Agência Goiana de Infraestrutura e Transportes |
| Palavras-chave | `GOINFRA, rodovias Goiás, obras rodoviárias` |

**Busca gerada:**
```
Agência Goiana de Infraestrutura e Transportes OR GOINFRA OR rodovias Goiás OR obras rodoviárias Goiás notícia
```

#### Exemplo 3: Assembleia Legislativa

| Campo | Valor |
|-------|-------|
| Nome | Assembleia Legislativa do Estado de Goiás |
| Palavras-chave | `ALEGO, deputados estaduais Goiás` |

**Busca gerada:**
```
Assembleia Legislativa do Estado de Goiás OR ALEGO OR deputados estaduais Goiás Goiás notícia
```

### 4.4 Boas Práticas no Cadastro

1. **Comece com poucas palavras-chave** (2-4) e vá ajustando conforme a qualidade dos resultados.
2. **Use siglas conhecidas** — elas são eficazes para encontrar notícias.
3. **Evite palavras muito comuns** que geram ruído (ex: "estado", "público").
4. **Revise periodicamente** as palavras-chave com base nas notícias coletadas.
5. **Desative temporariamente** entidades que não precisam de monitoramento contínuo em vez de excluí-las.

---

## 5. Fluxo de Coleta e Processamento de Notícias

A coleta acontece em 5 etapas sequenciais para cada entidade ativa:

### 5.1 Etapa 1: Construção da Busca

O sistema lê todas as entidades ativas do banco de dados e, para cada uma, monta a query de busca conforme descrito na seção 4.2.

### 5.2 Etapa 2: Busca na Web e Redes Sociais (Firecrawl)

Para cada entidade, o sistema realiza **4 buscas paralelas**:

1. **Busca geral na web** — `{termos} Goiás notícia`
2. **Busca no X (Twitter)** — `site:x.com {termos} Goiás`
3. **Busca no Instagram** — `site:instagram.com {termos} Goiás`
4. **Busca no Facebook** — `site:facebook.com {termos} Goiás`

Cada busca possui as seguintes configurações:

- **Limite:** até 5 resultados por busca (total de até 20 resultados brutos por entidade)
- **Idioma:** Português (Brasil)
- **País:** Brasil
- **Período:** última semana
- **Formato:** markdown (conteúdo da página extraído)

> **Nota:** As buscas em redes sociais capturam apenas conteúdo **público**. Posts privados ou de contas fechadas não são acessíveis.

### 5.3 Etapa 3: Deduplicação

Antes de processar, o sistema verifica se a URL da notícia já existe no banco de dados. Notícias já coletadas anteriormente são descartadas, evitando duplicatas.

### 5.4 Etapa 4: Classificação por IA

Cada notícia nova é enviada para um modelo de inteligência artificial (Google Gemini 2.5 Flash), que analisa o conteúdo e retorna:

- **Título limpo** da notícia
- **Resumo** em 2-3 frases
- **Sentimento** (positivo, negativo ou neutro)
- **Classificação** por tipo (ver seção 6)
- **Pessoas mencionadas** na notícia
- **Relevância** — se a notícia realmente é sobre a entidade e sobre Goiás

> Notícias consideradas **não relevantes** pela IA são automaticamente descartadas.

### 5.5 Etapa 5: Armazenamento e Alertas

As notícias relevantes são salvas no banco de dados com todos os metadados. Se a notícia tiver sentimento negativo ou classificação de mídia negativa, um **alerta** é gerado automaticamente (apenas em coletas manuais).

---

## 6. Classificações e Sentimentos

### Classificações disponíveis

| Classificação | Descrição |
|---------------|-----------|
| **Mídia Negativa** | Escândalos, denúncias, corrupção, problemas institucionais |
| **Nomeação** | Alguém foi nomeado para um cargo |
| **Exoneração** | Alguém foi exonerado de um cargo |
| **Substituição** | Troca de pessoa em um cargo específico |
| **Troca** | Permuta ou mudança de posição |
| **Movimentação** | Transferências e mudanças administrativas |
| **Ação Judicial** | Processos, ações judiciais, decisões judiciais |
| **Outro** | Não se encaixa nas categorias acima |

### Sentimentos

| Sentimento | Descrição |
|------------|-----------|
| **Positivo** | Notícia com teor favorável à entidade |
| **Negativo** | Notícia com teor desfavorável, crítico ou problemático |
| **Neutro** | Notícia informativa sem carga valorativa |

---

## 7. Coleta Automática (Cron Job)

O sistema possui uma tarefa agendada que executa a coleta automaticamente:

- **Frequência:** a cada 6 horas
- **Horários (UTC):** 00:00, 06:00, 12:00 e 18:00
- **Funcionamento:** a tarefa faz uma requisição HTTP para a função de coleta, simulando o mesmo processo da coleta manual
- **Diferença da coleta manual:** a coleta automática **não gera alertas**, pois não há um usuário autenticado no contexto

### Verificando o status do cron

O status do cron job pode ser consultado na página de **Configurações** do sistema. A documentação técnica completa do agendamento está disponível em `docs/cron_setup.sql`.

---

## 8. Dicas para Máximo Aproveitamento

1. **Cadastre entidades estratégicas:** foque nos órgãos mais relevantes para seu trabalho antes de ampliar o escopo.

2. **Refine as palavras-chave:** após as primeiras coletas, verifique se as notícias são relevantes. Ajuste as palavras-chave para melhorar a precisão.

3. **Monitore os alertas regularmente:** a página de Alertas é o ponto central para identificar rapidamente notícias negativas.

4. **Use os filtros da página de Notícias:** combine filtros de entidade, classificação e sentimento para análises específicas (ex: ver todas as nomeações de uma entidade, ou todas as mídias negativas).

5. **Explore o Grafo de Relacionamentos:** use a página Grafo para descobrir padrões e conexões entre entidades e pessoas que não são óbvios na listagem de notícias.

6. **Acesse as fontes originais:** clique no ícone de link externo em cada notícia para ler a matéria completa na fonte.

7. **Mantenha entidades organizadas:** desative entidades temporariamente fora de escopo em vez de excluí-las — isso preserva o histórico de notícias associado.

8. **Coleta manual quando necessário:** use o botão "Coletar Notícias" no Dashboard ou na página de Notícias para uma coleta imediata, sem esperar o próximo ciclo automático.

---

## 9. Perguntas Frequentes (FAQ)

**P: Preciso incluir o nome da entidade nas palavras-chave?**  
R: Não. O nome da entidade é incluído automaticamente na busca. Nas palavras-chave, coloque apenas siglas, variações do nome e termos complementares.

**P: As palavras-chave são pesquisadas juntas como uma frase?**  
R: Não. Cada palavra-chave (separada por vírgula) é tratada como uma alternativa independente usando o operador OR. A busca retorna resultados que mencionem qualquer uma delas.

**P: Por que algumas notícias não aparecem após a coleta?**  
R: A IA analisa cada resultado e descarta aqueles que não são relevantes para a entidade ou para o estado de Goiás. Além disso, notícias já coletadas anteriormente são ignoradas para evitar duplicatas.

**P: Quantas notícias são coletadas por vez?**  
R: Até 5 resultados por entidade a cada coleta. Após deduplicação e filtragem de relevância pela IA, o número efetivo pode ser menor.

**P: A coleta automática gera alertas?**  
R: Não. Alertas são gerados apenas em coletas manuais, pois requerem um usuário autenticado para associar o alerta.

**P: Posso alterar a frequência da coleta automática?**  
R: A frequência é configurada a nível de banco de dados (cron job). Consulte o arquivo `docs/cron_setup.sql` para instruções de como alterar o intervalo.

**P: O que acontece se eu desativar uma entidade?**  
R: Ela deixa de ser incluída nas próximas coletas, mas todas as notícias já coletadas permanecem no banco de dados e continuam visíveis na página de Notícias.

**P: Posso coletar notícias de uma entidade específica?**  
R: A coleta manual pelo botão do sistema coleta para todas as entidades ativas simultaneamente. A coleta individual por entidade está disponível apenas via API.

---

*Documento atualizado em 05/04/2026 — Monitor Goiás v1.1*
