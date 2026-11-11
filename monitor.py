import pandas as pd
import requests
import os
import io
import time

ESTADOS = ["PB", "SP"]
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip().replace("<", "").replace(">", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip().replace("<", "").replace(">", "")
SCRAPER_KEY = os.environ.get("SCRAPERAPI_KEY", "").strip()

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensagem,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, data=payload, timeout=15)
    except Exception as e:
        print(f"Erro Telegram: {e}")

def obter_valor_col(row, termos, padrao='N/D'):
    for col in row.index:
        c_low = str(col).lower()
        if any(t in c_low for t in termos):
            val = str(row[col]).strip()
            if val and val.lower() != 'nan':
                return val
    return padrao

def obter_link_imovel(row):
    # Verifica se a própria planilha já traz coluna com link direto
    link_csv = obter_valor_col(row, ['link'], padrao='')
    if link_csv and link_csv.lower().startswith('http'):
        return link_csv.replace('&', '&amp;')

    # Monta a URL direta oficial da Caixa pelo número de identificação do imóvel
    num = str(row.get('Número do imóvel', '')).strip()
    if num.endswith('.0'):
        num = num[:-2]

    if num and num != 'N/D' and num.lower() != 'nan':
        return f"https://venda-imoveis.caixa.gov.br/sistema/detalhe-imovel.asp?hdnimovel={num}"
    return None

def obter_csv_caixa(estado, max_tentativas=3):
    url_alvo = f"https://venda-imoveis.caixa.gov.br/listaweb/Lista_imoveis_{estado}.csv"
    params = {
        'api_key': SCRAPER_KEY,
        'url': url_alvo,
        'country_code': 'br'
    }

    for tentativa in range(1, max_tentativas + 1):
        print(f"[{estado}] Tentativa {tentativa} de {max_tentativas}...")
        try:
            resp = requests.get('https://api.scraperapi.com/', params=params, timeout=70)
            
            if resp.status_code == 200 and len(resp.content) >= 500:
                try:
                    conteudo = resp.content.decode('utf-8')
                except UnicodeDecodeError:
                    conteudo = resp.content.decode('latin1', errors='ignore')

                if not (conteudo.strip().startswith('<') or '<html' in conteudo.lower()[:300]):
                    linhas = conteudo.splitlines()
                    linha_inicio = 0
                    for i, l in enumerate(linhas[:15]):
                        l_lower = l.lower()
                        if any(termo in l_lower for termo in ['imovel', 'imóvel', 'cidade', 'bairro', 'preco', 'preço']):
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

                    if col_id:
                        df = df.rename(columns={col_id: 'Número do imóvel'})
                        print(f"[{estado}] Sucesso na tentativa {tentativa}! Total de linhas: {len(df)}")
                        return df
            else:
                print(f"[{estado}] Retorno inconsistente (Status: {resp.status_code}, Tamanho: {len(resp.content)} bytes)")

        except Exception as e:
            print(f"[{estado}] Erro na tentativa {tentativa}: {e}")

        if tentativa < max_tentativas:
            time.sleep(5)

    return None

def monitorar():
    relatorio_geral = []

    for estado in ESTADOS:
        print(f"A processar estado: {estado}...")
        df_hoje = obter_csv_caixa(estado)

        if df_hoje is None or df_hoje.empty:
            enviar_telegram(f"⚠️ <b>Aviso ({estado}):</b> Não foi possível descarregar os dados após 3 tentativas.")
            continue

        arquivo_base = f"base_imoveis_{estado}.csv"

        if not os.path.exists(arquivo_base):
            df_hoje.to_csv(arquivo_base, sep=';', encoding='utf-8', index=False)
            
            exemplo = df_hoje.iloc[0]
            cidade = obter_valor_col(exemplo, ['cidade'])
            bairro = obter_valor_col(exemplo, ['bairro'])
            preco = obter_valor_col(exemplo, ['preço', 'preco', 'preã§o', 'valor'])
            link_exemplo = obter_link_imovel(exemplo)

            msg = (
                f"🎉 <b>Base catalogada com sucesso para {estado}!</b>\n"
                f"Total de imóveis ativos: <b>{len(df_hoje)}</b>\n\n"
                f"<b>Exemplo de imóvel capturado:</b>\n"
                f"📍 {cidade} - {bairro}\n"
                f"💰 R$ {preco}\n"
            )
            if link_exemplo:
                msg += f"🔗 <a href='{link_exemplo}'>Ver imóvel na Caixa</a>\n"
            msg += "\n<i>O rastreador já está operacional na nuvem.</i>"

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
                link = obter_link_imovel(row)

                mensagem += f"📍 {cidade} - {bairro}\n💰 R$ {preco}\n"
                if link:
                    mensagem += f"🔗 <a href='{link}'>Ver imóvel no site da Caixa</a>\n"
                mensagem += "---\n"

            if len(novos) > 5:
                mensagem += f"<i>+ {len(novos) - 5} outros imóveis novos em {estado}.</i>"

            enviar_telegram(mensagem)
            relatorio_geral.append(f"{estado}: {len(novos)} novos detetados")
        else:
            relatorio_geral.append(f"{estado}: 0 novos (total {len(df_hoje)})")

    resumo = "\n".join(relatorio_geral)
    enviar_telegram(f"✅ <b>Relatório de Execução:</b>\n{resumo}")

if __name__ == "__main__":
    monitorar()
