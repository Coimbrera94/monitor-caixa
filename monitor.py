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

def obter_valor_col(row, termos, padrao='N/D'):
    for col in row.index:
        c_low = str(col).lower()
        if any(t in c_low for t in termos):
            return str(row[col])
    return padrao

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
        conteudo = resp.content.decode('utf-8', errors='ignore')
    except Exception:
        conteudo = resp.content.decode('latin1', errors='ignore')
        
    if conteudo.strip().startswith('<') or '<html' in conteudo.lower()[:300]:
        print(f"⚠️ Resposta em HTML recebida para {estado}:\n{conteudo[:300]}")
        return None
        
    try:
        linhas = conteudo.splitlines()
        linha_inicio = 0
        for i, l in enumerate(linhas[:15]):
            l_lower = l.lower()
            if any(termo in l_lower for termo in ['imovel', 'imóvel', 'imã³vel', 'cidade', 'bairro', 'preco', 'preço']):
                linha_inicio = i
                break
                
        df = pd.read_csv(io.StringIO(conteudo), sep=';', skiprows=linha_inicio, on_bad_lines='skip')
        df.columns = [str(col).strip() for col in df.columns]
        
        col_id = None
        for c in df.columns:
            c_low = c.lower()
            if ('im' in c_low and 'vel' in c_low) or 'num' in c_low or 'nãºm' in c_low:
                col_id = c
                break
                
        if not col_id and len(df.columns) > 0:
            col_id = df.columns[0]
            
        print(f"Identificador selecionado para {estado}: '{col_id}' (Total de colunas: {len(df.columns)})")
        df = df.rename(columns={col_id: 'Número do imóvel'})
        return df
    except Exception as e:
        print(f"Erro ao processar folha de cálculo de {estado}: {e}")
        return None

def monitorar():
    relatorio_geral = []

    for estado in ESTADOS:
        print(f"A obter imóveis de {estado}...")
        df_hoje = obter_csv_caixa(estado)
        
        if df_hoje is None or df_hoje.empty:
            enviar_telegram(f"⚠️ <b>Aviso ({estado}):</b> Não foi possível descarregar os dados.")
            continue

        arquivo_base = f"base_imoveis_{estado}.csv"

        if not os.path.exists(arquivo_base):
            df_hoje.to_csv(arquivo_base, sep=';', encoding='utf-8', index=False)
            
            exemplo = df_hoje.iloc[0]
            cidade = obter_valor_col(exemplo, ['cidade'])
            bairro = obter_valor_col(exemplo, ['bairro'])
            preco = obter_valor_col(exemplo, ['preço', 'preco', 'preã§o', 'valor'])
            
            msg = (
                f"🎉 <b>Base catalogada com sucesso para {estado}!</b>\n"
                f"Total de imóveis ativos: <b>{len(df_hoje)}</b>\n\n"
                f"<b>Exemplo de imóvel capturado:</b>\n"
                f"📍 {cidade} - {bairro}\n"
                f"💰 R$ {preco}\n\n"
                f"<i>O rastreador já está operacional na nuvem.</i>"
            )
            enviar_telegram(msg)
            relatorio_geral.append(f"{estado}: {len(df_hoje)} imóveis registados")
            continue

        try:
            df_base = pd.read_csv(arquivo_base, sep=';', encoding='utf-8', on_bad_lines='skip')
        except Exception:
            df_base = pd.DataFrame()

        if 'Número do imóvel' in df_base.columns:
            novos = df_hoje[~df_hoje['Número do imóvel'].isin(df_base['Número do imóvel'])]
        else:
            novos = pd.DataFrame()

        df_hoje.to_csv(arquivo_base, sep=';', encoding='utf-8', index=False)

        if not novos.empty:
            mensagem = f"🚨 <b>{len(novos)} NOVOS IMÓVEIS ({estado})</b>\n\n"
            for _, row in novos.head(5).iterrows():
                cidade = obter_valor_col(row, ['cidade'])
                bairro = obter_valor_col(row, ['bairro'])
                preco = obter_valor_col(row, ['preço', 'preco', 'preã§o', 'valor'])
                mensagem += f"📍 {cidade} - {bairro}\n💰 R$ {preco}\n---\n"
            enviar_telegram(mensagem)
            relatorio_geral.append(f"{estado}: {len(novos)} novos detetados")
        else:
            relatorio_geral.append(f"{estado}: 0 novos (total {len(df_hoje)})")

    resumo = "\n".join(relatorio_geral)
    enviar_telegram(f"✅ <b>Relatório de Execução:</b>\n{resumo}")

if __name__ == "__main__":
    monitorar()
