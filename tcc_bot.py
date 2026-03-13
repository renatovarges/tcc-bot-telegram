#!/usr/bin/env python3
"""
Bot Telegram - Transcrição e Legendagem de Áudios
Railway/Render compatible (HTTP health check included)
HTML parse_mode for Telegram formatting
"""

import os
import logging
import io
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ALLOWED_USER_ID = int(os.getenv('ALLOWED_USER_ID', '0'))
PORT = int(os.getenv('PORT', '10000'))

JOGADORES_LIST = "Abel Ferreira, Acevedo, Ademir, Adonis Frías, Adson, Aguirre, Alan Franco, Alan Patrick, Alan Rodríguez, Alerrandro, Alef Manga, Alisson, Alex Sandro, Alex Telles, Alexander Barboza, Alexsander, Alix Vinicius, Allan, André, André Luis, André Ramalho, Andreas Pereira, Andrew, Andrey Fernandes, Angileri, Anthoni, Ararat, Arboleda, Arias, Arthur, Arthur Cabral, Arthur Dias, Arthur Izaque, Arthur Melo, Arthur Novaes, Artur, Arrascaeta, Ayrton Lucas, Bastos, Batata, Belé, Benassi, Benavídez, Benedetti, Bernal, Bernabei, Bernard, Bobadilla, Bolasie, Borré, Braithwaite, Brayan, Breno Bidon, Breno Lopes, Bruno Alves, Bruno Fuchs, Bruno Gomes, Bruno Henrique, Bruno Leonardo, Bruno Melo, Bruno Pacheco, Bruno Rodrigues, Bruno Tabata, Bruninho, Cacá, Caio Alexandre, Caio Paulista, Caíque, Calleri, Camilo, Camutanga, Canobbio, Cantalapiedra, Cantillo, Carlos Cuesta, Carlos Eduardo, Carlos Miguel, Carlos Vinícius, Carlinhos, Carrascal, Carrillo, Cássio, Cassierra, Cauan Baptistella, Cauê, Cauly, Cédric Soares, Charles, Chico da Costa, Chico Kim, Chris Ramos, Christian, Claudinho, Clayton Sampaio, Cleiton, Coronel, Cristhian Loor, Cristian Olivera, Cuello, Cuiabano, Cufré, Da Mata, Danilo, Daniel Borges, Daniel Fuzato, Daniel Silva, Danielzinho, David, David Duarte, David Ricardo, Davi Gomes, De la Cruz, Dell, Denilson, Diego, Diego Hernández, Dieguinho, Diógenes, Djhordney, Dodi, Dória, Dorival Júnior, Douglas Telles, Dudu, Dyogo Alves, Edenílson, Edson Carioca, Edu, Eduardo, Eduardo Domínguez, Eduardo Doma, Eduardo Sasha, Eduardo Santos, Emerson Royal, Emiliano Martínez, Emmanuel Martínez, Enamorado, Ênio, Enzo Díaz, Enzo Vagner, Erick, Erick Pulga, Eric Ramires, Escobar, Esquivel, Everaldo, Everson, Everton, Everton Galdino, Everton Ribeiro, Evertton Araújo, Fabinho, Fábio, Fabri, Fabrício, Fabrício Bruno, Fagner, Felipe Anderson, Felipe Chiqueti, Felipe Guimarães, Felipe Jonatan, Felipe Longo, Felipe Negrucci, Felipinho, Félix Torres, Fernando, Fernando Pradella, Fernando Seabra, Fernando Sobral, Ferraresi, Ferreira, Fintelman, Flaco López, Fredi Lippert, Freitas, Freytes, Gabriel, Gabriel Abdias, Gabriel Bontempo, Gabriel Brazão, Gabriel Delfim, Gabriel Grando, Gabriel Leite, Gabriel Mec, Gabriel Menino, Gabriel Paulista, Gabriel Xavier, Galeano, Ganso, Garcez, Garro, Gerson, Giay, Gilberto, Gilmar Dal Pozzo, Giovanni Augusto, Giovanni Pavani, Guga, Gui Negão, Guilherme Arana, Guilherme Gomes, Gustavinho, Gustavo, Gustavo Henrique, Gustavo Martins, Gustavo Prado, Gustavo Scarpa, Gustavo Talles, Guzmán Rodríguez, Habraão, Hércules, Herrera, Higor Meritão, Hulk, Hugo, Hugo Moura, Hugo Souza, Iago, Igor Cariús, Igor Formiga, Igor Gomes, Igor Rabello, Igor Vinícius, Ignácio, Ignacio Sosa, Índio, Isaac, Isidro Pitta, Ítalo, Ivan, Iván Román, Jacy, Jáderson, Jair, Jair Ventura, Jajá, Jamerson, Janderson, Japa, Jean Carlos, Jean Gabriel, Jean Lucas, Jefté, Jefinho, Jeferson, Jeffinho, Jemmes, Jhoan Hernández, João Ananias, João Basso, João Bezerra, João Bom, João Cruz, João Lucas, João Marcelo, João Paulo, João Pedro, João Schmidt, João Victor, João Vitor, Joaquín Correa, Johan Rojas, John Kennedy, Jonathan Jesus, Jorginho, Josué, JP, JP Chermont, Juan Vojvoda, Julimar, Júnior Santos, Juninho, Juninho Capixaba, Junior Alonso, Justino, Kadir, Kaiki Bruno, Kainã, Kaio, Kaio César, Kaio Jorge, Kaique Kenji, Kaiquy Luiz, Kannemann, Kanu, Kauã Moraes, Kauã Pascini, Kauã Prates, Kauan, Kauan Toledo, Kauê Furquim, Kayke, Kayky, Kayky Almeida, Keno, Keven Samuel, Khellven, Kike Saverio, Klaus, Labyad, Larson, Lavega, Lawan, Léo, Léo Andrade, Léo Derik, Léo Jardim, Léo Linck, Léo Nannetti, Léo Ortiz, Léo Pereira, Léo Vieira, Leozinho, Leonel Pérez, Luan, Luan Cândido, Luan Freitas, Luan Peres, Lucas Arcanjo, Lucas Barbosa, Lucas Cunha, Lucas Evangelista, Lucas Freitas, Lucas Moura, Lucas Mugni, Lucas Oliveira, Lucas Paquetá, Lucas Piton, Lucas Romero, Lucas Ronier, Lucas Silva, Lucas Taverna, Lucca, Luciano, Luciano Juba, Lucão, Lucho Acosta, Luighi, Luis Miguel, Luis Zubeldía, Luiz Araújo, Luiz Felipe, Luiz Gustavo, Lyanco, Maicon, Maik, Mailson, Mancha, Marçal, Marcelinho, Marcelo Eráclito, Marcelo Lomba, Marcelo Pitaluga, Marcelo Rangel, Marcão, Marcinho, Marcos Alexandre, Marcos Antônio, Marcos Rocha, Marcos Vinícius, Marinho, Marino Hinestroza, Marlon, Marlon Freitas, Marllon, Marquinhos, Martín Anselmi, Martinelli, Mastriani, Mateus Carvalho, Mateus Dias, Mateus Iseppe, Mateus Silva, Mateus Xavier, Matheus Bahia, Matheus Bidu, Matheus Cunha, Matheus Donelli, Matheus Fernandes, Matheus França, Matheus Henrique, Matheus Martins, Matheus Pereira, Matheus Reis, Matheus Soares, Matheuzinho, Maurício, Maycon, Mayke, Medina, Memphis Depay, Mendoza, Mercado, Michel Araújo, Miguelito, Minda, Moisés, Monsalve, Montoro, Murilo, Murilo Rhikman, Mycael, Nadson, Nardoni, Natanael, Nathan, Nathan Fogaça, Nathan Mendes, Negueba, Neris, Neto, Neto Moura, Neto Pessoa, Newton, Neymar, Nicolas Pontes, Nicolás Ferreira, Nonato, Noriega, Nuno Moreira, Oliva, Osvaldo, Otávio, Pablo Baianinho, Pablo Lúcio, Pablo Maia, Palacios, Panagiotis, Patrick, Patrick de Paula, Paulinho, Paulo Henrique, Paulo Pezzolano, Pavón, Pedro, Pedro Cobra, Pedro Ferreira, Pedro Henrique, Pedro Kauã, Pedro Morisco, Pedro Raul, Pedro Rocha, Perotti, PH Gama, Phillipe Gabriel, Picco, Piquerez, Plata, Portilla, Praxedes, Preciado, Puma Rodríguez, Rafael, Rafael Carvalheira, Rafael Guanaes, Rafael Monti, Rafael Santos, Rafael Soares, Rafael Thyere, Rafael Tolói, Raniele, Raul, Rayan Lelis, Raykkonen, Reinaldo, Renan Lodi, Renan Peixoto, Renan Viana, Renato Kayzer, Renato Marques, Renê, Renzo López, Rhuan Gabriel, Riccieli, Richard, Riquelme, Riquelme Fillipi, Riquelme Felipe, Robert, Robert Renan, Robinho Jr., Rochet, Rodrigo Moledo, Rodrigo Nestor, Rodrigo Rodrigues, Rodrigues, Roger, Rogério Ceni, Rollheiser, Román Gómez, Ronald, Ronald Lopes, Ronaldo, Rony, Rossi, Ruan, Ruan Assis, Ruan Pablo, Rúben Ismael, Rubens, Ryan, Ryan Francisco, Sabino, Saldivia, Samuel Lino, Samuel Xavier, Sanabria, Santi Moreno, Santi Rodríguez, Santiago Mingo, Santos, Sant Anna, Saúl, Sávio, Savarino, Sebastián Gómez, Serna, Shaylon, Sinisterra, Soteldo, Souza, Spinelli, Tassano, Tchê Tchê, Terán, Tetê, Tevis, Thaciano, Thalisson Gabriel, Thiago Azaf, Thiago Beltrame, Thiago Couto, Thiago Maia, Thiago Mendes, Thiago Santos, Thomazella, Tiago Cóser, Tiago Volpi, Tiaguinho, Tico, Tiquinho Soares, Tite, Tomás Pérez, Tinga, Vanderlan, Varela, Vegetti, Viery, Villalba, Villasanti, Villagra, Villarreal, Vini Paulista, Vinicinho, Vinicius, Vinicius Lira, Vitão, Vitinho, Vitor Bueno, Vitor Eudes, Vitor Gabriel, Vitor Hugo, Vitor Roque, Viveros, Wagner Leonardo, Walace, Wallace Davi, Wallace Yan, Wallisson, Walter, Walter Clar, Wanderson, Weverton, Wendell, Wesley Natã, Willian, Willian Arão, Willian José, Willian Machado, Willian Oliveira, Yago Ferreira, Yago Pikachu, Ygor Vinhas, Ythallo, Yuri Alberto, Yuri Lara, Yuri Leles, Zé Breno, Zé Guilherme, Zé Ivaldo, Zé Marcos, Zé Ricardo, Zé Rafael, Zapelli"

SYSTEM_PROMPT = f"""Você converte transcrições de áudio em legendas para um grupo de Telegram de análise do Cartola FC.

## REGRAS DE OURO

1. **Fidelidade total**: escreva APENAS o que foi dito. Sem acréscimos, sem conclusões inventadas, sem frases motivacionais.
2. **Resumo inteligente**: remova repetições, vícios de linguagem, pausas e redundâncias, mas sem mutilar ideias importantes.
3. **Parágrafos curtos**: prefira blocos curtos, fáceis de ler no Telegram.
4. **Sem linguagem artificial**: evite frases como "Em resumo", "Portanto", "Vale ressaltar", "Essa análise mostra", "Boa sorte", "Fique atento" e semelhantes, a menos que isso tenha sido dito no áudio.
5. **A legenda termina quando o conteúdo do áudio termina.** Sem frase de encerramento automática.
6. **Nomes de jogadores**: se o nome estiver claramente identificável na transcrição, use a grafia correta da lista abaixo.
7. **Nunca troque um jogador por outro por suposição.** Se houver dúvida real, preserve o nome como veio na transcrição, sem inventar correção.

## LISTA DE JOGADORES (grafia oficial):
{JOGADORES_LIST}

## FORMATAÇÃO HTML (Telegram)
- Pode usar emojis de forma útil e natural.
- Pode usar destaques com CAIXA ALTA.
- Pode usar <b>negrito</b> para nomes, times, conceitos e pontos fortes.
- Pode usar <i>itálico</i> para ressalvas, nuances e observações.
- Pode usar <b><i>negrito itálico</i></b> quando houver um destaque central realmente importante.
- NÃO use Markdown com asteriscos ou underscores. Use apenas HTML.
- NÃO exagere na quantidade de destaques.

## ESTILO ESPERADO
- Linguagem natural, clara, fluida e agradável.
- Texto organizado e enxuto.
- Se o áudio for curto, a legenda pode ser curta.
- Se o áudio for mais longo e tiver conteúdo relevante, a legenda pode ser mais desenvolvida.
- O tamanho da legenda deve acompanhar a densidade do conteúdo, e não apenas a duração do áudio.
- A legenda deve parecer feita por alguém que ouviu com atenção, entendeu bem e organizou o conteúdo com fidelidade.

## EXEMPLOS REAIS (aprenda o estilo com estes dois casos)

### EXEMPLO 1

**TRANSCRIÇÃO:**
Bom pessoal, vamos lá então começar a fazer a nossa análise dos confrontos aqui, ainda que um pouco tardiamente, pelos imprevistos aqui que eu tive, mas vamos em frente. Seguinte, por que eu considero o Fluminense aqui favorito, jogo de faixinha verde, entre aspas, na minha análise do semáforo? E talvez não um outro time mais favorito na rodada, apesar de que eles existem. O Fluminense hoje, para mim, é um dos times mais organizados do Campeonato Brasileiro. O time que tem uma organização tanto defensiva quanto de transição ofensiva muito bem padronizada, um time que não se expõe muito. O time do Fluminense, você percebe que quando o time do Fluminense está jogando, ele toma todo o cuidado do mundo para só sair para o ataque se ele estiver totalmente organizado na defesa. E uma vez que o Fluminense perde a bola, ele faz um perde e pressiona muito rápido, justamente para evitar que a sua linha defensiva fique mais exposta lá atrás. Então ele tenta recuperar a bola na zona de menor perigo possível. Ainda assim, quando o Fluminense é atacado no seu último terço de campo, porque eles gostam de usar essa linguagem tática, quase sempre o Fluminense está muito bem protegido. O Zubel Dias já cuidou de fazer o ajuste defensivo do Fluminense depois da saída do Thiago Silva, que foi uma coisa que a gente detectou, que o Fluminense sentiu um pouco a saída dele. E hoje o Fluminense é um time bem organizado defensivamente. O Fluminense saiu para jogar contra o Remo, não poupou o time de maneira muito contundente. Teve ali praticamente seu time principal jogando contra o Remo lá no Pará, depois de uma final contra o Flamengo, que foi bastante cansativa, mas o Fluminense havia poupado o time contra o Palmeiras, então a gente não tem um Fluminense assim tão cansado. Além disso, o Fluminense joga no Maracanã, então não é momento do Fluminense poupar energia. Esses jogos são os jogos que o Fluminense tem que ganhar se ele quiser disputar a Libertadores, disputar a título, entendeu? Então a gente precisa ter esse nível de confiança no Fluminense justamente nesses jogos em que ele tem necessidade de vencer, tá bom? O time do Atlético Paranaense não é um time que tem demonstrado tanta fragilidade assim. Saiu para enfrentar o Red Bull Bragantino e teve em alguns momentos, não sei se vocês lembram, mas o jogo estava com muita chuva, não sei se vocês recordam disso, mas o time do Atlético Paraná esteve em alguns momentos até o domínio do jogo sobre o time do Red Bull Bragantino, mas não conseguiu vencer, apenas empatou, o que está longe de ser um resultado ruim. Ruim mesmo foi ter perdido em casa para o Corinthians, aquela derrota para o Corinthians em casa realmente foi bastante inesperada e o time fez um bom jogo naquela ocasião, mas perdeu um caminhão de gols, teve ali um xg muito alto, eu lembro que foi um amasso do time do Atlético Paranaense no Corinthians, mas o time não conseguiu marcar gols. Como o Fluminense é um time organizado e o Atlético Paranaense tem essa característica, É um jogo que eu acho que passa para a gente uma certa segurança em relação até a linha defensiva do Fluminense. Claro, é garantido que o Fluminense vai ficar sem sofrer gol. Não, garantido não tem nada no Campeonato Brasileiro. Mas a gente tem que analisar, tem que encontrar padrões, comparar com outros jogos e tomar decisões. Então, para mim, aqui, Fluminense é favorito e eu acho importante a gente olhar, sim, para a linha defensiva do Fluminense.

**LEGENDA CORRETA:**
🎙 <b>PRÉ-ANÁLISE FLUMINENSE x ATHLETICO-PR</b>

🟢 <b><i>FLUMINENSE FAVORITO — O JOGO DE FAIXINHA VERDE DA RODADA</i></b>

O <b>Fluminense</b> é <i>um dos times mais organizados do campeonato</i>. Defensivamente e em transição ofensiva, tudo muito bem padronizado.

Só sai pro ataque quando está totalmente organizado na defesa. Perdeu a bola? Perde e pressiona rápido, recupera na zona de menor perigo. Quando é atacado no último terço, <i>quase sempre está bem protegido</i>.

<b>Zubeldia</b> já fez o ajuste defensivo pós-saída do <b>Thiago Silva</b>. Time sentiu no começo, mas hoje está encaixado.

⚽ <b>DESGASTE FÍSICO?</b>

Fluminense não poupou contra o <b>Remo</b> (no Pará), mas <i>havia poupado contra o Palmeiras</i>. Não está tão cansado. Joga no Maracanã. Precisa vencer se quiser disputar Libertadores e títulos. <i>Não é hora de poupar.</i>

⚽ <b>ATHLETICO-PR</b>

Não é time frágil. Empatou com o <b>Bragantino</b> (sob chuva forte, chegou a dominar o jogo). A derrota em casa pro <b>Corinthians</b> foi inesperada: <i>amassou o Corinthians, xG altíssimo, mas não fez gol.</i>

Essa é a característica do <b>Athletico-PR</b>: produz, mas peca na finalização.

📌 <i>Fluminense organizado vs Athletico-PR que não converte. Cenário favorável pra olhar a <b>LINHA DEFENSIVA</b> do Fluminense com confiança.</i>

Garantido? Nada é no Brasileirão. Mas padrões e comparações apontam pro <b>Flu</b>.

---

### EXEMPLO 2

**TRANSCRIÇÃO:**
Bom pessoal, estou colocando para vocês aí a nossa análise do semáforo, aí sim eu tenho a minha opinião, eu espero que isso fique claro para vocês, que quando eu coloco as probabilidades da rodada, aquilo ali não é a minha opinião, aquilo ali são as bolsas esportivas, é a opinião deles, beleza? Eu sempre tenho muito receio das pessoas que não ouvem os meus áudios, não acompanham o meu raciocínio, porque vocês podem criar um certo tipo de confusão a respeito do que eu estou colocando, tá bom? Mas, enfim, estou fazendo o meu papel aqui. Na análise do semáforo, eu tenho um recorte aqui de pelo menos 5 times que eu considero favoritos na rodada, cada um com seu grau de favoritismo. Para mim, o maior favorito da rodada é o Fluminense, pelo que o time vem jogando, pelas atuações defensivas do time do Fluminense, pelo peso do Maracanã e etc. Com isso, eu não estou, entre aspas, desdenhando do Atlético Paranaense, tá? O Atlético Paranaense não é um time horroroso, não é um time fraco, não é um time ruim defensivamente, não. Mas o Fluminense já deu mostras que é um time que, em casa, precisa ser olhado com bastante carinho, tá bom? Palmeiras contra o Mirasol, para mim, também é um grande favorito da rodada, o segundo maior favorito da rodada. Só não vou colocar ali o Palmeiras como o maior favorito da rodada, porque a Chapecoense é um time enjoado de ser enfrentado. É um time chatinho, o Guanais é muito estratégico nas suas montagens de time e eles estão acostumados a se enfrentar. Isso também tem um peso, na medida que os técnicos vão se enfrentando cada vez mais, eles vão aprendendo a se anular nas suas características positivas, explorar as negativas, por isso que eu acho que o Palmeiras leva vantagem. O Palmeiras tem mais qualidade do que o time do Mirassol. O time do Mirassol vem falhando muito defensivamente em alguns momentos. Gosto do time do Coxa. Não acho que, por exemplo, o Cruzeiro é mais favorito do que o Coxa. Vendo o time do Remo jogar, o time do Coxa vem embalado por uma boa vitória contra o time do Corinthians. contra o Remo é um time que a gente tem que explorar. Pelo que eu tenho visto da Chapecoense, o Grêmio para mim é favorito, Chapecoense muito, muito limitada defensivamente, vem tomando caminhões de gol dentro de casa e o Grêmio ofensivamente tem sido um time muito produtivo, então para mim o Grêmio é favorito contra a Chape. E aí o quinto time ali que eu coloco como dentro de um hall de favoritos na rodada é o Cruzeiro contra o Vasco, mas aqui guardadas as devidas proporções de favoritismo, não acho que o Cruzeiro é tão favorito, por exemplo, quanto eu considero o Palmeiras, o próprio Fluminense, porque o Vasco, com a chegada do Renato Gaúcho, tende a ser um time que se protege um pouco melhor, um pouco mais estratégico também, em termos de planejamento tático para os jogos. Então isso gera um certo desconforto ali para a gente olhar para o Cruzeiro Ele cravar um favoritismo gigantesco. Até porque o time do Cruzeiro nas mãos do Tite ainda está em fase de construção. É lanterna do campeonato. Então a gente tem que ter um pouco de cuidado para não escalar o Cruzeiro do nosso imaginário. A gente tem que escalar o Cruzeiro real contra o Vasco real. O Cruzeiro hoje tem condição plena de vencer o Vasco, principalmente jogando no Mineirão. Mas não dá para a gente achar que esse Cruzeiro é o Cruzeiro do Leonardo Jardim, cara. Não é, é o Cruzeiro do Tite. Então a gente tem que tomar um certo cuidado com isso. Os jogos ali, do Internacional para cima, tem os seus favoritismos. Eu acho até que, por exemplo, São Paulo é favorito contra o Bragantino, mas uma coisa bem leve. Flamengo contra o Botafogo, mas uma coisa bem leve. Santos e Corinthians eu já acho mais parelho. Internacional e Bahia também. Beleza?

**LEGENDA CORRETA:**
🎙 <b>SEMÁFORO DA RODADA — OPINIÃO PESSOAL</b>

📌 <i>Diferente das probabilidades (mercado), aqui é a minha leitura.</i>

🟢 <b>TOP 5 FAVORITOS DA RODADA</b>

1️⃣ <b>Fluminense</b> — <i>maior favorito da rodada</i>
Atuações defensivas consistentes, peso do Maracanã. O Athletico-PR não é time fraco, mas o Fluminense em casa precisa ser olhado com carinho.

2️⃣ <b>Palmeiras</b> (vs Mirassol)
Qualidade superior. Mirassol vem falhando defensivamente. Só não é o 1° porque a Chapecoense é time enjoado e o Guanais é estratégico nas montagens. Técnicos que se enfrentam muito vão aprendendo a se anular.

3️⃣ <b>Coritiba</b> (vs Remo, no Couto Pereira)
Vem embalado pela vitória contra o Corinthians. Vai ter que ser protagonista e isso nem sempre é fácil pro Coxa. Mas contra o Remo em casa é jogo pra explorar.

4️⃣ <b>Grêmio</b> (vs Chapecoense)
Chape <i>muito limitada defensivamente</i>, tomando caminhões de gol. Grêmio ofensivamente produtivo. Favoritismo claro.

5️⃣ <b>Cruzeiro</b> (vs Vasco) — <i>com ressalvas</i>
Cruzeiro é lanterna, ainda em fase de construção nas palavras do Tite. Vasco com Renato Gaúcho tende a se proteger melhor e ser mais estratégico. <i>Não dá pra escalar o Cruzeiro do imaginário. É o Cruzeiro do Tite, não o do Leonardo Jardim.</i>

🟡 <b>DEMAIS JOGOS</b>

São Paulo favorito contra o Bragantino, mas <i>leve</i>
Flamengo favorito contra o Botafogo, mas <i>leve</i>
Santos x Corinthians — <i>parelho</i>
Internacional x Bahia — <i>parelho</i>

---

## AGORA É SUA VEZ

A transcrição do usuário vem a seguir. Siga o estilo dos exemplos acima, mas adapte o tamanho da legenda ao volume e à densidade do conteúdo. Se o áudio for mais longo e trouxer ideias relevantes, preserve essas ideias de forma organizada e fiel, sem resumir demais.

## PADRÃO DE SAÍDA DESEJADO
- Sempre que possível, comece com um título curto.
- Sempre que fizer sentido, use 2 a 4 seções com subtítulos.
- Evite legenda excessivamente seca ou puramente técnica.
- Evite também legenda floreada ou enfeitada demais.
- O tom deve ficar entre o sóbrio e o comunicativo.
- Use emojis quando ajudarem a organização visual, mas sem obrigação.
- A legenda deve soar como um resumo bem organizado do áudio, e não como uma lista fria de anotações.

"""

# ── Servidor HTTP para health check ──────────────────────────────────────────

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot TCC Legendas rodando!")

    def log_message(self, format, *args):
        pass


def start_health_server():
    server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
    logger.info(f"Servidor HTTP rodando na porta {PORT}")
    server.serve_forever()


# ── Funções de transcrição e legendagem ──────────────────────────────────────

def transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    audio_io = io.BytesIO(audio_bytes)
    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files={"file": (filename, audio_io, "audio/ogg")},
            data={"model": "whisper-1", "language": "pt"}
        )
        response.raise_for_status()
        return response.json()["text"]


def generate_legend(transcript: str) -> str:
    with httpx.Client(timeout=180.0) as client:
        response = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Transcrição do áudio:\n\n{transcript}"}
                ],
                "temperature": 0.2,
                "max_tokens": 1200
            }
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


# ── Handlers do Telegram ──────────────────────────────────────────────────────

async def process_audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    logger.info(f"Mensagem recebida de user_id={user_id}")
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Sem permissão.")
        return

    try:
        processing_msg = await update.message.reply_text("⏳ Processando áudio...")

        if update.message.voice:
            tg_file = await update.message.voice.get_file()
            filename = "voice.ogg"
        elif update.message.audio:
            tg_file = await update.message.audio.get_file()
            filename = update.message.audio.file_name or "audio.ogg"
        else:
            return

        audio_bytes = await tg_file.download_as_bytearray()
        logger.info(f"Áudio recebido: {len(audio_bytes)} bytes")

        await processing_msg.edit_text("🎙️ Transcrevendo com Whisper...")
        transcript = transcribe_audio(bytes(audio_bytes), filename)
        logger.info(f"Transcrição ({len(transcript)} chars)")

        await processing_msg.edit_text("✍️ Gerando legenda...")
        legend = generate_legend(transcript)
        logger.info(f"Legenda gerada ({len(legend)} chars)")

        await processing_msg.edit_text(legend, parse_mode='HTML')
        logger.info("✅ Legenda enviada com sucesso.")

    except httpx.HTTPStatusError as e:
        logger.error(f"Erro OpenAI: {e.response.status_code} - {e.response.text}")
        await update.message.reply_text(
            f"❌ Erro na API OpenAI (código {e.response.status_code})."
        )
    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Erro: {str(e)}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Sem permissão.")
        return
    await update.message.reply_text(
        "🎙️ Bot de Legendagem TCC ativo!\n\nEnvie um áudio e aguarde a legenda."
    )


# ── Inicialização ─────────────────────────────────────────────────────────────

async def run_bot():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN não configurado")
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY não configurado")
    if ALLOWED_USER_ID == 0:
        raise ValueError("ALLOWED_USER_ID não configurado")

    logger.info(f"Iniciando bot | ALLOWED_USER_ID={ALLOWED_USER_ID}")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, process_audio_message))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot rodando... aguardando mensagens.")
    await asyncio.Event().wait()


if __name__ == '__main__':
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    asyncio.run(run_bot())
