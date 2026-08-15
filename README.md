# SIS-UEMA Status

Monitor não-oficial de disponibilidade do [sis.sig.uema.br](https://sis.sig.uema.br/),
feito por/para estudantes. Roda 100% de graça em cima do GitHub (Actions + Pages),
sem precisar de servidor próprio.

**Como funciona:**
1. Um workflow do **GitHub Actions** roda a cada 5 minutos e verifica se o site responde.
2. O resultado é salvo em `docs/data/history.json`, dentro do próprio repositório.
3. O **GitHub Pages** publica a pasta `docs/` como um site estático — um painel em
   HTML/CSS/JS puro que lê esse JSON e mostra status atual, uptime e incidentes.

---

## Passo 1 — Criar o repositório no GitHub

1. Acesse [github.com/new](https://github.com/new).
2. Dê um nome, por exemplo `sis-uema-status`.
3. Deixe como **público** (necessário para usar o GitHub Pages gratuito em repositórios pessoais).
4. Não marque nenhuma opção de inicialização (README, .gitignore etc.) — vamos subir os arquivos prontos.
5. Clique em **Create repository**.

## Passo 2 — Subir os arquivos deste projeto

Baixe os arquivos que gerei (pasta `sis-uema-status/`) e suba pro repositório. Duas formas:

### Opção A — pelo site do GitHub (mais simples, sem terminal)
1. Na página do repositório recém-criado, clique em **"uploading an existing file"**.
2. Arraste **toda** a estrutura de pastas (`.github/`, `docs/`, `scripts/`, `requirements.txt`, `README.md`).
   > Importante: o GitHub aceita arrastar pastas inteiras pelo navegador (Chrome/Edge) — ele preserva a estrutura de subpastas.
3. Escreva uma mensagem de commit, ex: "setup inicial", e clique em **Commit changes**.

### Opção B — pelo terminal (git)
```bash
cd sis-uema-status
git init
git add .
git commit -m "setup inicial do monitor"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/sis-uema-status.git
git push -u origin main
```

## Passo 3 — Habilitar permissão de escrita para o Actions

O workflow precisa poder commitar o `history.json` atualizado de volta no repositório.

1. No repositório, vá em **Settings → Actions → General**.
2. Role até **"Workflow permissions"**.
3. Selecione **"Read and write permissions"**.
4. Clique em **Save**.

Sem isso, o passo `git push` do workflow vai falhar com erro de permissão.

## Passo 4 — Habilitar o GitHub Pages

1. Ainda em **Settings**, vá em **Pages** (menu lateral).
2. Em **"Build and deployment" → Source**, selecione **"Deploy from a branch"**.
3. Em **Branch**, escolha `main` e a pasta `/docs`.
4. Clique em **Save**.
5. Aguarde 1–2 minutos. O GitHub vai te dar uma URL do tipo:
   `https://SEU-USUARIO.github.io/sis-uema-status/`

Essa é a página que você vai compartilhar com os colegas.

## Passo 5 — Rodar o primeiro check manualmente

Não precisa esperar os 5 minutos do cron:

1. Vá na aba **Actions** do repositório.
2. Clique no workflow **"Verificar status do SIS-UEMA"** na lista à esquerda.
3. Clique em **"Run workflow"** → **Run workflow** (botão verde).
4. Aguarde terminar (ícone verde ✅). Isso já vai commitar o primeiro registro em `docs/data/history.json`.
5. Atualize a página do GitHub Pages — o status já deve aparecer.

## Passo 6 — Conferir que está tudo rodando sozinho

A partir daqui, o GitHub Actions roda automaticamente a cada 5 minutos (o cron `*/5 * * * *`
no arquivo `.github/workflows/check.yml`), sem você precisar fazer nada. Você pode
acompanhar os últimos runs na aba **Actions**.

> **Nota sobre o agendamento do GitHub Actions:** o GitHub não garante execução exatamente
> no minuto marcado — em horários de alta demanda pode atrasar alguns minutos. Isso é normal
> e não costuma ser um problema para esse tipo de monitoramento.

---

## Personalizações úteis

### Mudar a frequência de verificação
Edite `.github/workflows/check.yml`, linha do `cron`. Exemplos:
- A cada 10 min: `*/10 * * * *`
- A cada 1h: `0 * * * *`

(GitHub Actions não permite intervalos menores que 5 min em repositórios gratuitos.)

### Detectar "falso positivo" (site responde mas mostra erro/manutenção)
Em `scripts/check.py`, preencha a variável `EXPECTED_TEXT_SNIPPET` com um trecho de texto
que sempre aparece na tela de login normal do SIS, por exemplo:
```python
EXPECTED_TEXT_SNIPPET = "Sistema Integrado de Gestão"
```
Se esse texto não aparecer na resposta, o check marca como `down` mesmo com HTTP 200.

### Avisar no Telegram/Discord quando o status mudar
Dá pra adicionar um passo no workflow que dispara uma notificação comparando o último
status com o penúltimo. Se quiser, posso montar essa parte também — é só pedir.

### Quantos registros manter no histórico
Em `scripts/check.py`, a constante `MAX_HISTORY_ENTRIES` (padrão: 2016, equivalente a
7 dias com check a cada 5 min). Aumente se quiser reter mais histórico — o arquivo JSON
cresce, mas é leve (poucos KB até milhares de registros).

---

## Estrutura do projeto

```
sis-uema-status/
├── .github/
│   └── workflows/
│       └── check.yml       # roda o checker periodicamente no GitHub Actions
├── docs/                    # publicado pelo GitHub Pages
│   ├── index.html           # painel visual
│   ├── style.css
│   ├── app.js                # lê history.json e monta os gráficos
│   └── data/
│       └── history.json      # histórico de verificações (atualizado automaticamente)
├── scripts/
│   └── check.py              # faz a requisição HTTP e grava o resultado
├── requirements.txt
└── README.md
```

## Rodando localmente (opcional, pra testar antes de subir)

```bash
pip install -r requirements.txt
python scripts/check.py
```

Isso já atualiza `docs/data/history.json`. Para ver o painel localmente:

```bash
cd docs
python -m http.server 8000
```

E abra `http://localhost:8000` no navegador.

---

*Projeto independente, sem vínculo oficial com a UEMA.*
