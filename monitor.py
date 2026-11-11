import pandas as pd
import requests
import os

# Configurações: Lista de estados a serem monitorados
ESTADOS = ["PB", "SP"]
TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "HTML"})

def monitorar():
    # Disfarçando o robô para parecer um navegador de verdade (Chrome)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    }
    
    for estado in ESTADOS:
        print(f"Verificando estado: {estado}...")
        url_caixa = f"https://venda-imoveis.caixa.gov.br/listaweb/Lista_imoveis_{estado}.csv"
        arquivo_base = f"base_imoveis_{estado}.csv"
        arquivo_hoje = f"hoje_{estado}.csv"
        
        # 1. Baixa a lista de hoje da Caixa
        try:
            resposta = requests.get(url_caixa, headers=headers, timeout=15)
            with open(arquivo_hoje, "wb") as f:
                f.write(resposta.content)
                
            df_hoje = pd.read_csv(arquivo_hoje, sep=';', encoding='latin1', on_bad_lines='skip')
            
            # --- BLINDAGEM CONTRA O ERRO ---
            # Verifica se a coluna realmente existe. Se a Caixa bloqueou, ele avisa e pula.
            if 'Número do imóvel' not in df_hoje.columns:
                print(f"⚠️ Erro ao ler dados de {estado}. A Caixa bloqueou o download hoje.")
                continue 
                
        except Exception as e:
            print(f"Erro ao baixar/processar {estado}: {e}")
            continue
            
        # 2. Se não existir a base anterior, cria e avisa
        if not os.path.exists(arquivo_base):
            df_hoje.to_csv(arquivo_base, sep=';', encoding='latin1', index=False)
            enviar_telegram(f"🤖 Monitoramento ativado para {estado}! A partir da próxima verificação, você receberá os novos imóveis.")
            continue

        # Carrega a base antiga e blinda contra erros de leitura
        try:
            df_base = pd.read_csv(arquivo_base, sep=';', encoding='latin1', on_bad_lines='skip')
            if 'Número do imóvel' not in df_base.columns:
                df_hoje.to_csv(arquivo_base, sep=';', encoding='latin1', index=False)
                continue
        except Exception:
            df_hoje.to_csv(arquivo_base, sep=';', encoding='latin1', index=False)
            continue
        
        # 3. Compara os imóveis usando a coluna de ID
        novos = df_hoje[~df_hoje['Número do imóvel'].isin(df_base['Número do imóvel'])]
        
        # 4. Atualiza a base para o dia seguinte
        df_hoje.to_csv(arquivo_base, sep=';', encoding='latin1', index=False)
        
        # 5. Envia o alerta se houver imóveis novos
        if not novos.empty:
            mensagem = f"🚨 <b>{len(novos)} NOVOS IMÓVEIS NA CAIXA ({estado})</b>\n\n"
            for _, row in novos.head(10).iterrows():
                cidade = row.get('Cidade', 'N/A')
                bairro = row.get('Bairro', 'N/A')
                valor = row.get('Preço de venda', 'N/A')
                mensagem += f"📍 {cidade} - {bairro}\n💰 R$ {valor}\n---\n"
                
            if len(novos) > 10:
                mensagem += f"\n<i>+ {len(novos) - 10} outros imóveis em {estado}. Confira o site.</i>"
                
            enviar_telegram(mensagem)
        else:
            print(f"Nenhum imóvel novo em {estado} hoje.")

if __name__ == "__main__":
    monitorar()
