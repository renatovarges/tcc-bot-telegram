# Bot Telegram - Transcrição e Legendagem de Áudios

Bot inteligente que transcreve áudios com Whisper e gera legendas automáticas com GPT-4 mini, perfeito para acessibilidade em grupos de análise.

## 🎯 Funcionalidades

- ✅ Transcrição automática de áudios com Whisper
- ✅ Geração de legendas inteligentes com emojis contextualizados
- ✅ Respeita o prompt de legendagem customizado
- ✅ Segurança: apenas usuário autorizado pode usar
- ✅ Custo ultra-baixo (~$3-5/mês)

## 📋 Pré-requisitos

- Bot Telegram criado (via @BotFather)
- Chave OpenAI com créditos disponíveis
- Conta Render (gratuita)

## 🚀 Deploy no Render

### Passo 1: Preparar o repositório GitHub

1. Crie um repositório **privado** no GitHub
2. Clone este projeto para seu computador
3. Faça push dos arquivos para o repositório

### Passo 2: Conectar ao Render

1. Acesse https://render.com
2. Clique em "New +" → "Web Service"
3. Selecione "Deploy an existing Git repository"
4. Conecte sua conta GitHub
5. Selecione o repositório que você criou

### Passo 3: Configurar o Render

**Build Command:**
```
pip install -r requirements.txt
```

**Start Command:**
```
python tcc_bot.py
```

### Passo 4: Adicionar variáveis de ambiente

No Render, vá para **Environment** e adicione:

| Chave | Valor |
|-------|-------|
| `TELEGRAM_BOT_TOKEN` | Seu token do bot (começa com números) |
| `OPENAI_API_KEY` | Sua chave OpenAI (começa com `sk-proj-`) |
| `ALLOWED_USER_ID` | Seu ID de usuário do Telegram |

### Passo 5: Deploy

Clique em "Create Web Service" e pronto! O bot vai estar rodando em segundos.

## 🧪 Teste Local (Opcional)

```bash
# Instalar dependências
pip install -r requirements.txt

# Criar arquivo .env
cp .env.example .env

# Editar .env com suas credenciais
nano .env

# Rodar o bot
python tcc_bot.py
```

## 💰 Custos

| Serviço | Custo Mensal |
|---------|------------|
| Render (hosting) | Gratuito |
| Whisper (transcrição) | ~$0,02/min |
| GPT-4 mini (legendagem) | ~$0,00015/token |
| **Total (25 áudios/semana, 7.5min)** | **~$3-5/mês** |

## 🔒 Segurança

- ✅ Variáveis sensíveis protegidas no Render
- ✅ Apenas usuário autorizado pode usar o bot
- ✅ Repositório privado no GitHub
- ✅ `.env` nunca é commitado (protegido por `.gitignore`)

## 📝 Customização

Para alterar o prompt de legendagem, edite o `SYSTEM_PROMPT` no arquivo `tcc_bot.py`.

## 🆘 Troubleshooting

**Bot não responde:**
- Verifique se o token está correto no Render
- Verifique se o `ALLOWED_USER_ID` é o seu ID

**Erro de autenticação OpenAI:**
- Verifique se a chave está correta
- Verifique se você tem créditos disponíveis

**Transcrição lenta:**
- Normal para áudios longos (5-10 min)
- Whisper processa em tempo real

## 📞 Suporte

Se tiver problemas, verifique:
1. Logs no Render (aba "Logs")
2. Credenciais no Render (aba "Environment")
3. Token do bot no @BotFather

---

**Criado para acessibilidade e inclusão** 🎙️
