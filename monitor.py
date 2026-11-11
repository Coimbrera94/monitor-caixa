import pandas as pd
import requests
import os

ESTADOS = ["PB", "SP"]
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip().replace("<", "").replace(">", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip().replace("<", "").replace(">", "")

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, data=payload, timeout=10)
        print(f"Envio Telegram: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Erro de conexão com Telegram: {e}")

def monitorar():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }
    
    total_novos_geral = 0

    for estado in ESTADOS:
        print(f"Verificando estado: {estado}...")
        url_caixa = f"https://venda-imoveis.caixa.gov.br/listaweb/Lista_imoveis_{estado}.csv"
        arquivo_base = f"base_imoveis_{estado}.csv"
        arquivo_hoje = f"hoje_{estado}.csv"
        
        try:
            resposta = requests.get(url_caixa, headers=headers, timeout=20)
            with open(arquivo_hoje, "wb") as f:
                f.write(resposta.content)
                
            df_hoje = pd.read_csv(arquivo_hoje, sep=';', encoding='latin1', on_bad_lines='skip')
            
            if 'Número do imóvel' not in df_hoje.columns:
                print(f"Aviso: Dados de {estado} não contêm a coluna esperada.")
                continue 
                
        except Exception as e:
            print(f"Falha ao obter lista de {estado}: {e}")
            continue
            
        if not os.path.exists(arquivo_base):
            df_hoje.to_csv(arquivo_base, sep=';', encoding='latin1', index=False)
            enviar_telegram(f"🤖 <b>Monitoramento ativado para {estado}!</b>\nBase inicial registrada.")
            continue

        try:
            df_base = pd.read_csv(arquivo_base, sep=';', encoding='latin1', on_bad_lines='skip')
            if 'Número do imóvel' not in df_base.columns:
                df_hoje.to_csv(arquivo_base, sep=';', encoding='latin1', index=False)
                continue
        except Exception:
            df_hoje.to_csv(arquivo_base, sep=';', encoding='latin1', index=False)
            continue
        
        novos = df_hoje[~df_hoje['Número do imóvel'].isin(df_base['Número do imóvel'])]
        df_hoje.to_csv(arquivo_base, sep=';', encoding='latin1', index=False)
        
        if not novos.empty:
            total_novos_geral += len(novos)
            mensagem = f"🚨 <b>{len(novos)} NOVOS IMÓVEIS NA CAIXA ({estado})</b>\n\n"
            for _, row in novos.head(10).iterrows():
                cidade = row.get('Cidade', 'N/A')
                bairro = row.get('Bairro', 'N/A')
                valor = row.get('Preço de venda', 'N/A')
                mensagem += f"📍 {cidade} - {bairro}\n💰 R$ {valor}\n---\n"
                
            if len(novos) > 10:
                mensagem += f"\n<i>+ {len(novos) - 10} outros imóveis em {estado}.</i>"
                
            enviar_telegram(mensagem)
        else:
            print(f"Nenhum novo imóvel em {estado}.")

    enviar_telegram(f"✅ <b>Varredura diária concluída!</b>\nTotal de novos imóveis detectados: {total_novos_geral}")

if __name__ == "__main__":
    monitorar()
