import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import os
import time

st.set_page_config(
    page_title="Alerting & Suivi PEA BoursoBank",
    page_icon="📈",
    layout="wide"
)

CSV_FILE = "portfolio.csv"

# --- TELEGRAM CONFIG (Optionnel - à configurer dans les Secrets Streamlit) ---
# Dans Streamlit Cloud : Settings > Secrets > ajouter :
# TELEGRAM_TOKEN = "votre_token_bot"
# TELEGRAM_CHAT_ID = "votre_chat_id"
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", None) if hasattr(st, "secrets") else None
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", None) if hasattr(st, "secrets") else None

def send_telegram_alert(message):
    """Envoie une notification Telegram si les identifiants sont configurés."""
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            st.error(f"Erreur d'envoi Telegram : {e}")

# --- GESTION DU FICHIER CSV DE SAUVEGARDE ---
def load_portfolio():
    """Charge le portefeuille depuis le CSV ou crée une structure vide."""
    if os.path.exists(CSV_FILE):
        try:
            df = pd.read_csv(CSV_FILE)
            required_cols = ["Ticker", "Quantite", "PRU", "FraisAchat", "FraisVente", "GainVise"]
            if all(col in df.columns for col in required_cols):
                return df
        except Exception:
            pass
    return pd.DataFrame(columns=["Ticker", "Quantite", "PRU", "FraisAchat", "FraisVente", "GainVise"])

def save_portfolio(df):
    """Sauvegarde le portefeuille dans le CSV."""
    df.to_csv(CSV_FILE, index=False)

# Initialisation des données dans la session
if "portfolio_df" not in st.session_state:
    st.session_state.portfolio_df = load_portfolio()

# --- EN-TÊTE DE L'APPLICATION ---
st.title("📈 Suivi & Alerting Portefeuille PEA BoursoBank")
st.markdown("""
*Application de suivi des petits gains sur compte PEA avec sauvegarde automatique en CSV et alertes de seuil.*
""")

# --- BARRE LATÉRALE : SAISIE / MODIFICATION DES POSITIONS ---
with st.sidebar:
    st.header("⚙️ Gestion des Lignes")
    
    with st.form("add_position_form", clear_on_submit=False):
        st.subheader("Ajouter ou Mettre à jour")
        ticker = st.text_input("Ticker Yahoo (ex: GLE.PA, TTE.PA, AIR.PA, CW8.PA)", value="GLE.PA").strip().upper()
        qty = st.number_input("Quantité d'actions", min_value=1, value=10, step=1)
        pru = st.number_input("PRU / Prix d'achat unitaire (€)", min_value=0.01, value=25.0, step=0.05, format="%.2f")
        fee_buy = st.number_input("Frais d'achat (€)", min_value=0.0, value=1.99, step=0.10, format="%.2f")
        fee_sell = st.number_input("Frais de vente estimés (€)", min_value=0.0, value=1.99, step=0.10, format="%.2f")
        target_gain = st.number_input("Gain net minimum visé (€)", min_value=1.0, value=20.0, step=5.0, format="%.2f")
        
        submit_btn = st.form_submit_button("💾 Enregistrer la ligne")
        
    if submit_btn:
        df = st.session_state.portfolio_df.copy()
        
        # Si le ticker existe déjà, on le met à jour, sinon on l'ajoute
        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker, ["Quantite", "PRU", "FraisAchat", "FraisVente", "GainVise"]] = [qty, pru, fee_buy, fee_sell, target_gain]
            st.success(f"Ligne **{ticker}** mise à jour avec succès !")
        else:
            new_row = pd.DataFrame([{
                "Ticker": ticker,
                "Quantite": qty,
                "PRU": pru,
                "FraisAchat": fee_buy,
                "FraisVente": fee_sell,
                "GainVise": target_gain
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            st.success(f"Ligne **{ticker}** ajoutée avec succès !")
            
        st.session_state.portfolio_df = df
        save_portfolio(df)
        st.rerun()

    st.divider()
    
    # Suppression d'une ligne
    if not st.session_state.portfolio_df.empty:
        st.subheader("🗑️ Supprimer une ligne")
        ticker_to_delete = st.selectbox("Choisir la ligne à supprimer", options=st.session_state.portfolio_df["Ticker"].tolist())
        if st.button("Supprimer du portefeuille"):
            df = st.session_state.portfolio_df
            df = df[df["Ticker"] != ticker_to_delete].reset_index(drop=True)
            st.session_state.portfolio_df = df
            save_portfolio(df)
            st.warning(f"Ligne **{ticker_to_delete}** supprimée !")
            st.rerun()

# --- TABLEAU DE BORD PRINCIPAL ---
df_positions = st.session_state.portfolio_df.copy()

if not df_positions.empty:
    tickers_list = df_positions["Ticker"].unique().tolist()
    
    # Récupération des cours du marché via yfinance
    with st.spinner("Récupération des cours en temps réel sur Euronext/Yahoo Finance..."):
        try:
            market_data = yf.download(tickers_list, period="1d", interval="1m", progress=False)
            latest_prices = {}
            for t in tickers_list:
                try:
                    if len(tickers_list) == 1:
                        val = market_data['Close'].iloc[-1]
                    else:
                        val = market_data['Close'][t].dropna().iloc[-1]
                    latest_prices[t] = round(float(val), 3)
                except Exception:
                    latest_prices[t] = None
        except Exception as e:
            st.error(f"Erreur de connexion Yahoo Finance : {e}")
            latest_prices = {t: None for t in tickers_list}

    # Calculs personnalisés pour chaque position
    results = []
    alert_triggered = False
    
    for idx, row in df_positions.iterrows():
        t = row["Ticker"]
        qty = row["Quantite"]
        pru = row["PRU"]
        f_buy = row["FraisAchat"]
        f_sell = row["FraisVente"]
        target = row["GainVise"]
        current = latest_prices.get(t, None)
        
        # Formule : Cout Total = (Qty * PRU) + Frais Achat
        total_cost = (qty * pru) + f_buy
        
        # Cours Cible Minimum = (Cout Total + Gain Visé + Frais Vente) / Qty
        min_sell_price = round((total_cost + target + f_sell) / qty, 3)
        
        if current:
            # Plus-value brute
            gross_pnl = (current - pru) * qty
            # Plus-value nette
            net_pnl = round(gross_pnl - f_buy - f_sell, 2)
            # Statut alerte
            is_target_reached = current >= min_sell_price
        else:
            gross_pnl = None
            net_pnl = None
            is_target_reached = False

        if is_target_reached:
            alert_triggered = True

        results.append({
            "Ticker": t,
            "Qté": qty,
            "PRU (€)": f"{pru:.2f}",
            "Cout Total (€)": f"{total_cost:.2f}",
            "Frais Total (€)": f"{f_buy + f_sell:.2f}",
            "Gain Visé (€)": f"{target:.2f}",
            "Cours Cible Min (€)": min_sell_price,
            "Cours Actuel (€)": current if current else "N/A",
            "Gain Net Actuel (€)": net_pnl if net_pnl is not None else "N/A",
            "Objectif Atteint": "✅ OUI (VENDRE)" if is_target_reached else "⏳ Non"
        })

    df_display = pd.DataFrame(results)

    # --- AFFICHAGE DES KPIS CLÉS ---
    col1, col2, col3 = st.columns(3)
    
    total_invested = sum([row["Quantite"] * row["PRU"] + row["FraisAchat"] for idx, row in df_positions.iterrows()])
    total_net_pnl = sum([r["Gain Net Actuel (€)"] for r in results if isinstance(r["Gain Net Actuel (€)"], (int, float))])
    
    col1.metric("Capital Investi Total", f"{total_invested:.2f} €")
    col2.metric("Plus-Value Nette Globale", f"{total_net_pnl:+.2f} €", delta_color="normal")
    col3.metric("Lignes en Objectif Vente", f"{sum(1 for r in results if '✅' in r['Objectif Atteint'])} / {len(results)}")

    st.divider()

    # --- TABLEAU RECAPITULATIF ---
    st.subheader("📋 État du Portefeuille & Cours Cibles")
    
    # Styliser la table : mise en évidence des lignes avec objectif atteint
    def highlight_alert(row):
        if "OUI" in str(row["Objectif Atteint"]):
            return ['background-color: #d4edda; color: #155724; font-weight: bold'] * len(row)
        return [''] * len(row)

    st.dataframe(
        df_display.style.apply(highlight_alert, axis=1),
        use_container_width=True
    )

    # --- GESTION DES ALERTES & NOTIFICATIONS ---
    if alert_triggered:
        st.balloons()
        st.success("🎉 **Objectif atteint sur au moins une position !**")
        
        for r in results:
            if "OUI" in r["Objectif Atteint"]:
                msg = f"🔔 **ALERTE PEA - {r['Ticker']}**\n" \
                      f"- Cours actuel : **{r['Cours Actuel (€)']} €**\n" \
                      f"- Cours cible min : **{r['Cours Cible Min (€)']} €**\n" \
                      f"- Gain net potentiel : **+{r['Gain Net Actuel (€)']} €**"
                
                st.info(msg)
                
                # Envoi notification Telegram
                if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
                    telegram_msg = f"🚀 *ALERTE VENTE PEA* : {r['Ticker']}\n\n" \
                                   f"• Cours Actuel : `{r['Cours Actuel (€)']} €`\n" \
                                   f"• Seuil Cible : `{r['Cours Cible Min (€)']} €`\n" \
                                   f"• Gain Net : `+{r['Gain Net Actuel (€)']} €`"
                    send_telegram_alert(telegram_msg)

    # --- RECHARGEMENT AUTOMATIQUE ---
    st.divider()
    col_ref, col_info = st.columns([1, 3])
    with col_ref:
        refresh_sec = st.selectbox("Rafraîchissement automatique", options=[900, 1800, 3600], format_func=lambda x: f"{x//60} minutes", index=1)
    with col_info:
        st.caption(f"Dernier rafraîchissement à {pd.Timestamp.now().strftime('%H:%M:%S')}. La page s'actualise automatiquement toutes les {refresh_sec//60} min.")
        
    time.sleep(1) # Pause technique
else:
    st.info("👋 Votre portefeuille est vide pour le moment. Utilisez la barre latérale à gauche pour ajouter vos premières actions.")
