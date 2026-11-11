import pandas as pd
import requests
import os
import io

ESTADOS = ["PB", "SP"]
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip().replace("<", "").replace(">", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip().replace("<", "").replace(">", "")

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, data=payload, timeout=15)
        print(f"Envio Telegram: {resp.status_code}")
    except Exception as e:
        print(f"Erro Telegram: {e}")

def obter_csv_caixa(estado, session):
    url = f"https://venda-imoveis.caixa.gov.br/listaweb/Lista_imoveis_{estado}.csv"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://venda-imoveis.caixa.gov.br/sistema/busca-imovel.asp',
        'Connection': 'keep-alive',
    }
    resp = session.get(url, headers=headers, timeout=30)
    
    # Valida se o retorno é um CSV real e não página de erro/bloqueio
    if resp.status_code != 200 or len(resp.content) < 1000:
        print(f"Falha ao baixar {estado}: retorno pequeno ou status {resp.status_code}")
        return None
        
    try:
        # A Caixa costuma ter linhas de cabeçalho descritivas antes dos dados; skiprows localiza o início
        conteudo = resp.content.decode('latin1', errors='ignore')
        linhas = conteudo.splitlines()
        linha_inicio = 0
        for i, l in enumerate(linhas[:10]):
            if 'Número do imóvel' in l or 'Numero do Imovel' in l or 'Cidade' in l:
                linha_inicio = i
                break
                
        df = pd.read_csv(io.StringIO(conteudo), sep=';', skiprows=linha_inicio, encoding='latin1', on_bad_lines='skip')
        df.columns = [col.strip() for col in df.columns]
        
        # Localiza coluna de identificador
        col_id = next((c for c in df.columns if 'Número do imóvel' in c or 'Numero' in c), None)
        if not col_id:
            print(f"Estrutura inesperada para {estado}. Colunas: {list(df.columns)}")
            return None
            
        df = df.rename(columns={col_id: 'Número do imóvel'})
        return df
    except Exception as e:
        print(f"Erro de processamento {estado}: {e}")
        return None

def monitorar():
    session = requests.Session()
    # Requisição inicial para obter cookies válidos do portal
    try:
        session.get("https://venda-imoveis.caixa.gov.br/sistema/busca-imovel.asp", timeout=15)
    except Exception:
        pass

    relatorio_geral = []

    for estado in ESTADOS:
        print(f"Buscando dados reais da Caixa para {estado}...")
        df_hoje = obter_csv_caixa(estado, session)
        
        if df_hoje is None or df_hoje.empty:
            enviar_telegram(f"⚠️ <b>Aviso ({estado}):</b> Caixa bloqueou o download ou não retornou dados.")
            continue

        arquivo_base = f"base_imoveis_{estado}.csv"

        # Primeira execução para este estado: salva e envia validação prática
        if not os.path.exists(arquivo_base):
            df_hoje.to_csv(arquivo_base, sep=';', encoding='latin1', index=False)
            
            exemplo = df_hoje.iloc[0]
            cidade = exemplo.get('Cidade', 'N/D')
            bairro = exemplo.get('Bairro', 'N/D')
            preco = exemplo.get('Preço de venda', exemplo.get('Valor de avaliação', 'N/D'))
            
            msg = (
                f"🎉 <b>Base de dados criada para {estado}!</b>\n"
                f"Total de imóveis catalogados: <b>{len(df_hoje)}</b>\n\n"
                f"<b>Exemplo de imóvel capturado:</b>\n"
                f"📍 {cidade} - {bairro}\n"
                f"💰 R$ {preco}\n\n"
                f"<i>O sistema já está apto a avisar sobre novas entradas.</i>"
            )
            enviar_telegram(msg)
            relatorio_geral.append(f"{estado}: {len(df_hoje)} imóveis salvos")
            continue

        # Comparação com base existente
        try:
            df_base = pd.read_csv(arquivo_base, sep=';', encoding='latin1', on_bad_lines='skip')
        except Exception:
            df_base = pd.DataFrame()

        if 'Número do imóvel' in df_base.columns:
            novos = df_hoje[~df_hoje['Número do imóvel'].isin(df_base['Número do imóvel'])]
        else:
            novos = pd.DataFrame()

        # Atualiza a base com o estado atual
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
