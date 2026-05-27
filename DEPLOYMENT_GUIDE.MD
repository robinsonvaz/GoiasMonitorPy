# DEPLOYMENT GUIDE - GoiasMonitorPy (Windows Server + IIS)

Este documento descreve o processo completo para publicar o GoiasMonitorPy em servidor Windows usando IIS como reverse proxy para a aplicacao FastAPI, hospedada como subaplicacao do Default Web Site.

## 1. Visao geral da arquitetura

- IIS (Default Web Site) recebe HTTP/HTTPS (porta 80/443).
- IIS faz reverse proxy para Uvicorn local (porta 8000).
- GoiasMonitorPy roda como processo persistente (Windows Service via NSSM).
- Banco de dados MySQL roda localmente ou em servidor dedicado.
- Publicacao do app no caminho virtual `/goiasmonitor` (subaplicacao do site padrao).

Fluxo:

`Cliente -> IIS /goiasmonitor -> Uvicorn (127.0.0.1:8000) -> MySQL`

## 2. Pre-requisitos

- Windows Server 2019/2022 (recomendado).
- Permissao de administrador local no servidor.
- Dominio apontando para o servidor (se for usar HTTPS publico).
- Git instalado (opcional, mas recomendado para atualizacoes).
- MySQL 8.x (ou acesso a um MySQL remoto).

## 3. Estrutura de pastas recomendada

Use o caminho ja definido para este projeto:

- Codigo da aplicacao: `D:\Sistemas\GoiasMonitorPy`
- Logs da aplicacao: `D:\Sistemas\GoiasMonitorPy\logs`
- Ambiente virtual: `D:\Sistemas\GoiasMonitorPy\.venv`

## 4. Instalar componentes do IIS (features)

No Server Manager:

1. Add Roles and Features.
2. Selecione **Web Server (IIS)**.
3. Em **Role Services**, garanta pelo menos:
   - Common HTTP Features > Static Content
   - Common HTTP Features > Default Document
   - Security > Request Filtering
   - Performance > Static Content Compression
   - Health and Diagnostics > HTTP Logging
   - Management Tools > IIS Management Console

Opcional (somente se necessario para diagnostico):
- Tracing > Tracing

## 5. Instalar complementos/extensoes do IIS obrigatorios

Para reverse proxy funcionar corretamente no IIS, instale:

1. URL Rewrite Module 2.1
2. Application Request Routing (ARR) 3.0

Observacoes importantes:
- Instale primeiro o URL Rewrite e depois o ARR.
- Reinicie o IIS apos instalar (`iisreset`).

## 6. Runtime da aplicacao (Python ja instalado, sem PATH global)

O Python 3.11 ja esta instalado no servidor em `D:\Python\Python311`.

Diretriz deste ambiente:
- Nao adicionar Python no PATH global do Windows.
- Sempre usar o executavel absoluto para criar/operar o venv de cada aplicacao.

Validacao da instalacao:

```powershell
D:\Python\Python311\python.exe --version
```

## 7. Obter o codigo e criar ambiente virtual

```powershell
cd D:\Sistemas
git clone <URL_DO_REPOSITORIO> GoiasMonitorPy
cd D:\Sistemas\GoiasMonitorPy
D:\Python\Python311\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Se voce usa coleta com Playwright, instale o navegador:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

## 8. Configurar variaveis de ambiente (.env)

Crie o arquivo `.env` na raiz a partir do `.env.example`:

```powershell
Copy-Item .env.example .env
notepad .env
```

Configure no minimo:

- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`
- `LOCAL_ADMIN_EMAIL`
- `LOCAL_ADMIN_PASSWORD`
- `LOCAL_ADMIN_NAME`
- `APP_SECRET_KEY`
- `DEBUG=false`
- `APP_ROOT_PATH=/goiasmonitor` (obrigatorio quando publicado como subaplicacao)
- Chaves de IA que serao usadas (`LOVABLE_API_KEY`, etc.)

Gerar chave forte para `APP_SECRET_KEY`:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

## 9. Provisionar banco MySQL

### Opcao A: deixar a app criar estruturas automaticamente

A aplicacao executa `ensure_local_schema()` no startup e cria/atualiza estrutura basica.

### Opcao B: carga inicial via script SQL

Se preferir schema controlado, use os arquivos de `docs/`:

- `docs/schema_mysql.sql`

## 10. Teste local da aplicacao antes do IIS

```powershell
cd D:\Sistemas\GoiasMonitorPy
.\start-app.ps1 -NoReload -Port 8000
```

Opcional (comando direto do Uvicorn):

```powershell
cd D:\Sistemas\GoiasMonitorPy
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Valide no proprio servidor:
- http://127.0.0.1:8000

Se nao subir aqui, nao siga para o IIS antes de corrigir.

## 11. Criar servico Windows para Uvicorn (NSSM)

Para producao no Windows, nao rode em terminal aberto. Use servico Windows.

### 11.1 Instalar NSSM

Baixe e extraia o NSSM (Non-Sucking Service Manager) em pasta local, por exemplo:

- `C:\tools\nssm\win64\nssm.exe`

### 11.2 Registrar servico

Execute como administrador:

```powershell
C:\tools\nssm\win64\nssm.exe install GoiasMonitorPy
```

Na interface do NSSM, preencha:

- Application path:
  - `D:\Sistemas\GoiasMonitorPy\.venv\Scripts\python.exe`
- Startup directory:
  - `D:\Sistemas\GoiasMonitorPy`
- Arguments:
  - `-m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1`

Importante:
- Mantenha `--workers 1` para evitar execucao duplicada do scheduler APScheduler.

### 11.3 Configurar logs no NSSM (recomendado)

No NSSM, configure:
- stdout: `D:\Sistemas\GoiasMonitorPy\logs\stdout.log`
- stderr: `D:\Sistemas\GoiasMonitorPy\logs\stderr.log`

Crie a pasta antes:

```powershell
New-Item -ItemType Directory -Force -Path D:\Sistemas\GoiasMonitorPy\logs
```

### 11.4 Iniciar e validar servico

```powershell
sc.exe start GoiasMonitorPy
sc.exe query GoiasMonitorPy
```

Teste novamente:
- http://127.0.0.1:8000

## 12. Configurar IIS como reverse proxy (subaplicacao no Default Web Site)

### 12.1 Habilitar proxy no ARR

No IIS Manager (nivel servidor):

1. Clique em **Application Request Routing Cache**.
2. No painel da direita, abra **Server Proxy Settings**.
3. Marque **Enable proxy**.
4. Aplique.

### 12.2 Criar Application Pool dedicado (GoiasMonitorPool)

No IIS Manager (nivel servidor):

1. Abra **Application Pools**.
2. Clique em **Add Application Pool...**.
3. Configure:
  - Name: `GoiasMonitorPool`
  - .NET CLR version: **No Managed Code**
  - Managed pipeline mode: **Integrated**
  - Start application pool immediately: marcado
4. Clique em **OK**.

Recomendado apos criar:

1. Selecione o pool `GoiasMonitorPool` e clique em **Advanced Settings...**.
2. Ajuste:
  - **Start Mode**: `AlwaysRunning`
  - **Idle Time-out (minutes)**: `0` (evita descarte por inatividade)
  - **Load User Profile**: `True` (util quando bibliotecas exigem perfil)

### 12.3 Criar subaplicacao no Default Web Site

1. No IIS Manager, expanda **Sites > Default Web Site**.
2. Clique com o botao direito em **Default Web Site** > **Add Application...**.
3. Configure:
  - Alias: `goiasmonitor`
  - Physical path: `D:\Sistemas\GoiasMonitorPy`
  - Application Pool: `GoiasMonitorPool` (ou um pool dedicado)
4. A URL publica ficara no formato `https://seu-dominio/goiasmonitor`.

### 12.4 Criar regra de URL Rewrite

No nivel da aplicacao `goiasmonitor`, abra **URL Rewrite** e adicione regra **Blank rule**:

- Name: `ReverseProxyToUvicorn`
- Match URL:
  - Requested URL: `Matches the Pattern`
  - Using: `Regular Expressions`
  - Pattern: `(.*)`
- Conditions: nenhuma (ou adicione excecoes se quiser)
- Action:
  - Action type: `Rewrite`
  - Rewrite URL: `http://127.0.0.1:8000/{R:1}`
  - Append query string: marcado
  - Stop processing of subsequent rules: marcado

### 12.5 Preservar headers de proxy

Para FastAPI/Uvicorn interpretar corretamente IP de origem, esquema HTTPS e host, garanta o encaminhamento de:

- `X-Forwarded-For`
- `X-Forwarded-Proto`
- `X-Forwarded-Host` (opcional, recomendado)
- `Host`

Passo a passo recomendado:

1. No IIS Manager (nivel servidor), abra **Application Request Routing Cache** > **Server Proxy Settings**.
2. Marque **Enable proxy** (se ainda nao estiver ativo).
3. Marque **Preserve host header** para repassar o host original ao backend.
4. Aplique.

Liberar server variables no URL Rewrite (nivel servidor):

1. Abra **URL Rewrite** (no nivel servidor).
2. No painel da direita, clique em **View Server Variables**.
3. Adicione (Allow):
  - `HTTP_X_FORWARDED_FOR`
  - `HTTP_X_FORWARDED_PROTO`
  - `HTTP_X_FORWARDED_HOST`

Ajustar regra `ReverseProxyToUvicorn` (na aplicacao `goiasmonitor`):

1. Abra a regra no **URL Rewrite**.
2. Em **Server Variables**, adicione:
  - `HTTP_X_FORWARDED_FOR = {REMOTE_ADDR}`
  - `HTTP_X_FORWARDED_PROTO = https`
  - `HTTP_X_FORWARDED_HOST = {HTTP_HOST}`
3. Salve e aplique.

Observacao para Uvicorn/FastAPI:

- No servico NSSM, mantenha Uvicorn com suporte a proxy headers, por exemplo:
  - `-m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1`

Validacao rapida:

1. Acesse `https://seu-dominio/goiasmonitor`.
2. Verifique no backend se:
  - esquema da requisicao aparece como `https` (nao `http`);
  - host corresponde ao dominio publico;
  - IP do cliente nao aparece como `127.0.0.1` em logs de aplicacao.

Se os valores nao refletirem o acesso externo, revise ARR, `Preserve host header` e `serverVariables` da regra.

### 12.6 Observacao sobre caminho base (/goiasmonitor)

- Como a aplicacao sera publicada em subpasta, os acessos externos devem usar `/goiasmonitor`.
- Exemplo: `https://seu-dominio/goiasmonitor`.
- Se desejar publicar na raiz do dominio no futuro, mova a regra para o nivel do site e ajuste as rotas conforme a estrategia adotada.

## 13. HTTPS (SSL/TLS)

Opcoes comuns:

1. Certificado corporativo (PFX) importado no Windows Certificate Store.
2. Certificado publico com win-acme (Lets Encrypt) para dominio publico.

### 13.1 Associar certificado ao binding 443

No IIS Site Bindings:

- Type: `https`
- Port: `443`
- Host name: seu dominio
- SSL certificate: selecione o certificado

### 13.2 Redirecionar HTTP -> HTTPS

No site, adicione regra de redirect no URL Rewrite:

- Condicao: `{HTTPS}` igual `OFF`
- Acao: Redirect para `https://{HTTP_HOST}/{R:1}`
- Tipo: `Permanent (301)`

## 14. Firewall e rede

No servidor Windows, liberar:

- Entrada 80/TCP (HTTP)
- Entrada 443/TCP (HTTPS)

Porta 8000 deve ficar apenas local (`127.0.0.1`) e sem exposicao externa.

## 15. Conta de execucao e permissoes

Recomendado:

- Rodar o servico `GoiasMonitorPy` com conta de servico dedicada (nao LocalSystem), quando possivel.
- Dar permissao de leitura/escrita apenas nas pastas necessarias (`D:\Sistemas\GoiasMonitorPy`, `logs`).
- Proteger arquivo `.env` (ACL restrita para administradores e conta de servico).

### 15.1 Aplicar ACL do Application Pool com script (recomendado)

O repositorio possui o script `PoolGoiasMonitor.ps1`, que aplica:

- `RX` (leitura/execucao) para `IIS AppPool\GoiasMonitorPool` em `D:\Sistemas\GoiasMonitorPy`.
- `M` (modify) para a pasta de logs `D:\Sistemas\GoiasMonitorPy\logs`.

Execute em PowerShell elevado (Administrador):

```powershell
cd D:\Sistemas\GoiasMonitorPy
powershell -ExecutionPolicy Bypass -File .\PoolGoiasMonitor.ps1
```

Validacao opcional:

```powershell
icacls D:\Sistemas\GoiasMonitorPy | findstr /I "GoiasMonitorPool"
icacls D:\Sistemas\GoiasMonitorPy\logs | findstr /I "GoiasMonitorPool"
```

## 16. Rotina de deploy/atualizacao (runbook)

Sempre em janela de manutencao:

1. Parar servico:

```powershell
sc.exe stop GoiasMonitorPy
```

2. Atualizar codigo:

```powershell
cd D:\Sistemas\GoiasMonitorPy
git pull
```

3. Atualizar dependencias:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

4. (Se necessario) atualizar navegador Playwright:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

5. Subir servico:

```powershell
sc.exe start GoiasMonitorPy
```

6. Validar health funcional acessando pagina inicial e telas principais.

## 17. Monitoramento e logs

Pontos de observacao:

- Logs do servico (NSSM stdout/stderr)
- Event Viewer > Windows Logs > Application
- IIS Logs (`C:\inetpub\logs\LogFiles`)

Sinais de problema comuns:

- 502.3 no IIS: backend fora do ar ou timeout no proxy.
- 500 no backend: erro de dependencia, banco, ou variavel faltante no `.env`.
- Falhas em coleta: chaves de IA ou provedores de busca ausentes/invalidas.

## 18. Hardening recomendado

- `DEBUG=false` sempre em producao.
- Senhas fortes no MySQL e admin local.
- Rotacionar `APP_SECRET_KEY` apenas em janela planejada.
- Restringir acesso administrativo ao IIS e servidor.
- Habilitar backup de banco e do `.env` (cofre seguro).
- Definir politica de rotacao/retencao de logs.

## 19. Checklist final de go-live

- [ ] Python 3.11 instalado em `D:\Python\Python311` (fora do PATH global)
- [ ] Dependencias instaladas (`requirements.txt`)
- [ ] `.env` configurado com segredos reais
- [ ] MySQL acessivel e schema criado
- [ ] Servico `GoiasMonitorPy` iniciado automaticamente
- [ ] URL Rewrite + ARR instalados e proxy habilitado
- [ ] Application Pool `GoiasMonitorPool` criado e associado a aplicacao
- [ ] ACL do Pool aplicada (script `PoolGoiasMonitor.ps1` executado como administrador)
- [ ] Aplicacao IIS `Default Web Site/goiasmonitor` com regra de rewrite para `127.0.0.1:8000`
- [ ] HTTPS ativo com certificado valido
- [ ] Firewall liberando apenas 80/443 externamente
- [ ] Logs e monitoramento validados

## 20. Troubleshooting rapido

### Erro 502.3 no IIS

Verificar:

```powershell
sc.exe query GoiasMonitorPy
netstat -ano | findstr :8000
```

### Aplicacao sobe, mas login falha

- Confirmar conectividade MySQL e credenciais no `.env`.
- Confirmar se usuario admin foi criado na primeira inicializacao.

### Coleta de noticias sem resultados

- Validar chaves de IA e provedores no `.env`.
- Confirmar acesso de rede do servidor para APIs externas.
- Revisar logs em `logs\stderr.log`.

### Erro com Playwright

Reinstalar navegador:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

Se o servidor for restrito e sem necessidade de browser automation, configurar:

- `PLAYWRIGHT_ENABLED=false`

---

## Apendice A - Exemplo de web.config na subaplicacao goiasmonitor (opcional)

Se preferir manter configuracao versionada, voce pode usar `web.config` em `D:\Sistemas\GoiasMonitorPy` (path fisico da subaplicacao no IIS):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="HTTP to HTTPS" stopProcessing="true">
          <match url="(.*)" />
          <conditions>
            <add input="{HTTPS}" pattern="OFF" ignoreCase="true" />
          </conditions>
          <action type="Redirect" url="https://{HTTP_HOST}/{R:1}" redirectType="Permanent" />
        </rule>

        <rule name="ReverseProxyToUvicorn" stopProcessing="true">
          <match url="(.*)" />
          <action type="Rewrite" url="http://127.0.0.1:8000/{R:1}" appendQueryString="true" />
          <serverVariables>
            <set name="HTTP_X_FORWARDED_PROTO" value="https" />
            <set name="HTTP_X_FORWARDED_FOR" value="{REMOTE_ADDR}" />
          </serverVariables>
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
```

Nota: para usar `<serverVariables>` pode ser necessario liberar variaveis no Feature View de URL Rewrite (View Server Variables).
