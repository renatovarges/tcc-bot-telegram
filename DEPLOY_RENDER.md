# 🚀 Guia Completo: Deploy do Bot no Render

Este é um guia **hiper-detalhado** para você fazer o deploy do bot no Render. Siga cada passo com atenção.

---

## PASSO 1: Criar repositório no GitHub

### 1.1 - Acesse GitHub

1. Vá para https://github.com
2. Faça login com sua conta (crie uma se não tiver)

### 1.2 - Criar novo repositório

1. Clique no ícone **+** (canto superior direito)
2. Clique em **"New repository"**

### 1.3 - Configurar o repositório

Preencha assim:

| Campo | Valor |
|-------|-------|
| Repository name | `tcc-bot-telegram` |
| Description | `Bot para transcrição e legendagem de áudios` |
| Visibility | **Private** (importante!) |
| Add a README file | Deixe desmarcado |
| Add .gitignore | Deixe desmarcado |

Clique em **"Create repository"**

---

## PASSO 2: Preparar os arquivos

### 2.1 - Baixar os arquivos do bot

Você vai receber estes arquivos:
- `tcc_bot.py` (código principal)
- `requirements.txt` (dependências)
- `Procfile` (configuração para Render)
- `runtime.txt` (versão Python)
- `.env.example` (exemplo de variáveis)
- `.gitignore` (proteção de arquivos sensíveis)
- `README.md` (documentação)

### 2.2 - Fazer upload para GitHub

1. No repositório que você criou, clique em **"Add file"** → **"Upload files"**
2. Arraste os 7 arquivos para a área de upload
3. Clique em **"Commit changes"**

---

## PASSO 3: Conectar Render ao GitHub

### 3.1 - Acessar Render

1. Vá para https://render.com
2. Clique em **"Sign up"** (ou faça login se já tiver conta)
3. Escolha **"Continue with GitHub"**
4. Autorize o Render a acessar sua conta GitHub

### 3.2 - Criar novo serviço

1. No dashboard do Render, clique em **"New +"** (canto superior direito)
2. Clique em **"Web Service"**

### 3.3 - Conectar repositório

1. Clique em **"Connect a repository"**
2. Procure por `tcc-bot-telegram` (o repositório que você criou)
3. Clique em **"Connect"**

---

## PASSO 4: Configurar o serviço no Render

### 4.1 - Nome e configurações básicas

Preencha assim:

| Campo | Valor |
|-------|-------|
| Name | `tcc-bot-telegram` |
| Environment | `Python 3` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python tcc_bot.py` |

### 4.2 - Plano (importante!)

Escolha o plano **"Free"** (é gratuito!)

---

## PASSO 5: Adicionar variáveis de ambiente

### 5.1 - Acessar variáveis de ambiente

1. Antes de clicar em "Create Web Service", procure pela seção **"Environment"**
2. Clique em **"Add Environment Variable"**

### 5.2 - Adicionar primeira variável: TELEGRAM_BOT_TOKEN

1. **Key:** `TELEGRAM_BOT_TOKEN`
2. **Value:** `8783235585:AAE4hpyW3QNK_X0aJ7Fy-uMw79j15bktEFA`
3. Clique em **"Add"**

### 5.3 - Adicionar segunda variável: OPENAI_API_KEY

1. Clique novamente em **"Add Environment Variable"**
2. **Key:** `OPENAI_API_KEY`
3. **Value:** `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`
4. Clique em **"Add"**

### 5.4 - Adicionar terceira variável: ALLOWED_USER_ID

1. Clique novamente em **"Add Environment Variable"**
2. **Key:** `ALLOWED_USER_ID`
3. **Value:** `5524998639678`
4. Clique em **"Add"**

---

## PASSO 6: Deploy

### 6.1 - Iniciar o deploy

1. Clique em **"Create Web Service"**
2. Render vai começar a fazer o deploy automaticamente
3. Você verá uma tela com logs em tempo real

### 6.2 - Esperar o deploy terminar

Você verá mensagens como:
```
Building...
Installing Python dependencies...
Starting service...
```

Quando aparecer:
```
✓ Service is live
```

**Parabéns! Seu bot está rodando! 🎉**

---

## PASSO 7: Testar o bot

### 7.1 - Abrir Telegram

1. Abra o Telegram
2. Procure pelo seu bot (TCC Legendas)
3. Clique em **"Iniciar"** ou envie `/start`

### 7.2 - Enviar um áudio

1. Envie um áudio para o bot
2. Aguarde a resposta (pode levar alguns segundos)
3. O bot vai responder com a legenda!

---

## ⚠️ Problemas comuns

### Bot não responde

**Solução:**
1. Vá para o Render (https://render.com)
2. Clique no seu serviço `tcc-bot-telegram`
3. Clique na aba **"Logs"**
4. Procure por mensagens de erro

Se ver erro de autenticação, verifique:
- Token do bot está correto?
- Chave OpenAI está correta?
- Você tem créditos na OpenAI?

### Erro "Service failed to start"

**Solução:**
1. Verifique se todas as 3 variáveis de ambiente foram adicionadas
2. Verifique se os nomes estão EXATAMENTE como mostrado acima
3. Clique em "Redeploy" para tentar novamente

### Bot para de responder depois de um tempo

**Solução:**
- Isso é normal no plano Free do Render (ele hiberna após inatividade)
- Quando você enviar um áudio, ele vai acordar e responder

---

## 🎯 Próximos passos

Seu bot está pronto! Agora você pode:

1. **Usar no seu grupo privado** com seus alunos
2. **Compartilhar com outros** (se quiser)
3. **Customizar o prompt** se necessário (me avise!)
4. **Monitorar custos** na OpenAI (deve ser bem baixo)

---

## 📞 Suporte

Se tiver dúvidas ou problemas:
1. Verifique os logs no Render
2. Verifique se as variáveis de ambiente estão corretas
3. Me contacte para ajudar

**Você consegue! 💪**
