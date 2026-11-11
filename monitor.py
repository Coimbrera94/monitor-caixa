import pandas as pd
import requests
import os
import io

ESTADOS = ["PB", "SP"]
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip().replace("<", "").replace(">", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip().replace("<", "").replace(">", "")
SCRAPER_KEY = os.environ.get("SCRAPERAPI_KEY", "").strip()

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, timeout=15)
    except Exception as e:
        print(f"Erro Telegram: {e}")

def obter_csv_caixa(estado):
    url_alvo = f"https://venda-imoveis.caixa.gov.br/listaweb/Lista_imoveis_{estado}.csv"
    
    params = {
        'api_key': SCRAPER_KEY,
        'url': url_alvo,
        'country_code': 'br'
    }
    
    try:
        resp = requests.get('https://api.scraperapi.com/', params=params, timeout=60)
    except Exception as e:
        print(f"Erro na conexão com ScraperAPI ({estado}): {e}")
        return None
        
    if resp.status_code != 200 or len(resp.content) < 1500:
        print(f"Retorno inválido ({estado}). Status: {resp.status_code}, Tamanho: {len(resp.content)} bytes")
        return None
        
    try:
        conteudo = resp.content.decode('latin1', errors='ignore')
        linhas = conteudo.splitlines()
        linha_inicio = 0
        for i, l in enumerate(linhas[:15]):
            if any(termo in l for termo in ['Número do imóvel', 'Numero do Imovel', 'Cidade', 'Preço de venda']):
                linha_inicio = i
                break
                
        df = pd.read_csv(io.StringIO(conteudo), sep=';', skiprows=linha_inicio, encoding='latin1', on_bad_lines='skip')
        df.columns = [str(col).strip() for col in df.columns]
        
        col_id = next((c for c in df.columns if 'Número do imóvel' in c or 'Numero' in c), None)
        if not col_id:
            print(f"Coluna identificadora ausente para {estado}.")
            return None
            
        df = df.rename(columns={col_id: 'Número do imóvel'})
        return df
    except Exception as e:
        print(f"Erro ao processar planilha de {estado}: {e}")
        return None

def monitorar():
    relatorio_geral = []

    for estado in ESTADOS:
        print(f"Buscando imóveis de {estado} via IP brasileiro...")
        df_hoje = obter_csv_caixa(estado)
        
        if df_hoje is None or df_hoje.empty:
            enviar_telegram(f"⚠️ <b>Aviso ({estado}):</b> Não foi possível baixar os dados hoje.")
            continue

        arquivo_base = f"base_imoveis_{estado}.csv"

        if not os.path.exists(arquivo_base):
            df_hoje.to_csv(arquivo_base, sep=';', encoding='latin1', index=False)
            
            exemplo = df_hoje.iloc[0]
            cidade = exemplo.get('Cidade', 'N/D')
            bairro = exemplo.get('Bairro', 'N/D')
            preco = exemplo.get('Preço de venda', exemplo.get('Valor de avaliação', 'N/D'))
            
            msg = (
                f"🎉 <b>Base catalogada com sucesso para {estado}!</b>\n"
                f"Total de imóveis ativos: <b>{len(df_hoje)}</b>\n\n"
                f"<b>Exemplo de imóvel real capturado:</b>\n"
                f"📍 {cidade} - {bairro}\n"
                f"💰 R$ {preco}\n\n"
                f"<i>O rastreador já está pronto na nuvem.</i>"
            )
            enviar_telegram(msg)
            relatorio_geral.append(f"{estado}: {len(df_hoje)} imóveis registrados")
            continue

        try:
            df_base = pd.read_csv(arquivo_base, sep=';', encoding='latin1', on_bad_lines='skip')
        except Exception:
            df_base = pd.DataFrame()

        if 'Número do imóvel' in df_base.columns:
            novos = df_hoje[~df_hoje['Número do imóvel'].isin(df_base['Número do imóvel'])]
        else:
            novos = pd.DataFrame()

        df_hoje.to_csv(arquivo_base, sep=';', encoding='latin1', index=False)

        if not novos.empty:
            mensagem = f"🚨 <b>{len(novos)} NOVOS IMÓVEIS ({estado})</b>\n\n"
            for _, row in novos.head(5).iterrows():
                cidade = row.get('Cidade', 'N/D')
                bairro = row.get('Bairro', 'N/D')
                preco = row.get('Preço de venda', 'N/D')
                mensagem += f"📍 {cidade} - {bairro}\n💰 R$ {preco}\n---\n"
            enviar_telegram(mensagem)
            relatorio_geral.append(f"{estado}: {len(novos)} novos detectados")
        else:
            relatorio_geral.append(f"{estado}: 0 novos (total {len(df_hoje)})")

    resumo = "\n".join(relatorio_geral)
    enviar_telegram(f"✅ <b>Relatório de Execução:</b>\n{resumo}")

if __name__ == "__main__":
    monitorar()
