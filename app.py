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

TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", None) if hasattr(st, "secrets") else None
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", None) if hasattr(st, "secrets") else None

def send_telegram_alert(message):
    """Envoie une notification Telegram si les identifiants sont configurés."""
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception:
            pass

def calculate_bourso_fees(amount):
    """
    Calcul exact des frais BoursoBank PEA - Tarif Découverte basés sur le MONTANT EN EUROS (€) :
    - Montant <= 398 € : 0,50% (plafond légal PEA)
    - 398 € < Montant <= 500 € : 1,99 € (forfait fixe Découverte)
    - Montant > 500 € : 0,50%
    """
    if amount <= 0:
        return 0.0
    if amount <= 398.0:
        return round(amount * 0.005, 2)
    elif amount <= 500.0:
        return 1.99
    else:
        return round(amount * 0.005, 2)

def load_portfolio():
    """Charge le portefeuille depuis le CSV ou crée une structure vide."""
    if os.path.exists(CSV_FILE):
        try:
            df = pd.read_csv(CSV_FILE)
            required_cols = ["Ticker", "Quantite", "PRU", "FraisAchat", "GainVise"]
            if all(col in df.columns for col in required_cols):
                return df
        except Exception:
            pass
    return pd.DataFrame(columns=["Ticker", "Quantite", "PRU", "FraisAchat", "GainVise"])

def save_portfolio(df):
    """Sauvegarde le portefeuille dans le CSV."""
    df.to_csv(CSV_FILE, index=False)

# Initialisation de la session
if "portfolio_df" not in st.session_state:
    st.session_state.portfolio_df = load_portfolio()

st.title("📈 Suivi & Alerting Portefeuille PEA BoursoBank")
st.markdown("*Tarif Découverte PEA avec calcul automatique des frais de vente selon le montant en €, modification des lignes et alerte de seuil.*")

# --- BARRE LATÉRALE : GESTION DES POSITIONS ---
with st.sidebar:
    st.header("⚙️ Gestion des Lignes")
    
    df_current = st.session_state.portfolio_df
    
    mode = "Ajouter"
    selected_ticker = None
    default_qty, default_pru, default_f_buy, default_gain = 10, 25.0, 1.99, 20.0
    
    if not df_current.empty:
        action_type = st.radio("Mode d'édition", ["Ajouter une nouvelle ligne", "Modifier une ligne existante"])
        if action_type == "Modifier une ligne existante":
            mode = "Modifier"
            selected_ticker = st.selectbox("Choisir l'action à modifier", options=df_current["Ticker"].tolist())
            row_data = df_current[df_current["Ticker"] == selected_ticker].iloc[0]
            default_qty = int(row_data["Quantite"])
            default_pru = float(row_data["PRU"])
            default_f_buy = float(row_data["FraisAchat"])
            default_gain = float(row_data["GainVise"])

    with st.form("position_form"):
        st.subheader(f"{mode} une position")
        
        if mode == "Modifier":
            ticker = st.text_input("Ticker Yahoo", value=selected_ticker, disabled=True)
        else:
            ticker = st.text_input("Ticker Yahoo (ex: GLE.PA, TTE.PA, CW8.PA)", value="GLE.PA").strip().upper()
            
        qty = st.number_input("Quantité d'actions", min_value=1, value=default_qty, step=1)
        pru = st.number_input("PRU / Prix d'achat unitaire (€)", min_value=0.01, value=default_pru, step=0.05, format="%.2f")
        
        # Calcul automatique suggéré pour les frais d'achat basés sur le montant investi en €
        estimated_buy_amount = qty * pru
        suggested_buy_fee = calculate_bourso_fees(estimated_buy_amount)
        
        fee_buy = st.number_input(
            f"Frais d'achat (€) [Calculé Bourso sur {estimated_buy_amount:.2f}€: {suggested_buy_fee}€]", 
            min_value=0.0, 
            value=suggested_buy_fee if mode == "Ajouter" else default_f_buy, 
            step=0.10, 
            format="%.2f"
        )
        
        target_gain = st.number_input("Gain net minimum visé (€)", min_value=1.0, value=default_gain, step=5.0, format="%.2f")
        
        submit_btn = st.form_submit_button("💾 Enregistrer la ligne")

    if submit_btn:
        df = st.session_state.portfolio_df.copy()
        
        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker, ["Quantite", "PRU", "FraisAchat", "GainVise"]] = [qty, pru, fee_buy, target_gain]
            st.success(f"Ligne **{ticker}** mise à jour avec succès !")
        else:
            new_row = pd.DataFrame([{"Ticker": ticker, "Quantite": qty, "PRU": pru, "FraisAchat": fee_buy, "GainVise": target_gain}])
            df = pd.concat([df, new_row], ignore_index=True)
            st.success(f"Ligne **{ticker}** ajoutée avec succès !")
            
        st.session_state.portfolio_df = df
        save_portfolio(df)
        st.rerun()

    st.divider()
    
    # Suppression d'une ligne
    if not st.session_state.portfolio_df.empty:
        st.subheader("🗑️ Supprimer une ligne")
        ticker_to_delete = st.selectbox("Action à supprimer", options=st.session_state.portfolio_df["Ticker"].tolist(), key="del_select")
        if st.button("Supprimer définitivement"):
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
    
    col_title, col_btn = st.columns([3, 1])
    with col_btn:
        if st.button("🔄 Rafraîchir les cours maintenant", use_container_width=True):
            st.rerun()

    # Récupération des cours Yahoo Finance
    with st.spinner("Téléchargement des cours Euronext en temps réel..."):
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
        except Exception:
            latest_prices = {t: None for t in tickers_list}

    results = []
    alert_triggered = False
    
    for idx, row in df_positions.iterrows():
        t = row["Ticker"]
        qty = row["Quantite"]
        pru = row["PRU"]
        f_buy = row["FraisAchat"]
        target = row["GainVise"]
        current = latest_prices.get(t, None)
        
        # Le calcul des frais se fait à 100% sur le MONTANT EN EUROS (€) de la transaction
        ref_price = current if current else pru
        est_sell_amount_eur = qty * ref_price
        
        # Calcul automatique selon le montant en €
        f_sell = calculate_bourso_fees(est_sell_amount_eur)
        
        # Cout total d'acquisition avec frais d'achat
        total_cost = (qty * pru) + f_buy
        
        # Prix de vente unitaire minimum pour atteindre le gain net voulu
        min_sell_price = round((total_cost + target + f_sell) / qty, 3)
        
        if current:
            current_total_val = qty * current
            net_pnl = round(current_total_val - (qty * pru) - f_buy - f_sell, 2)
            is_target_reached = current >= min_sell_price
        else:
            net_pnl = None
            is_target_reached = False

        if is_target_reached:
            alert_triggered = True

        results.append({
            "Ticker": t,
            "Qté": qty,
            "PRU (€)": f"{pru:.2f}",
            "Montant Inv. (€)": f"{(qty * pru):.2f}",
            "Frais Achat (€)": f"{f_buy:.2f}",
            "Frais Vente Est. (€)": f"{f_sell:.2f}",
            "Gain Visé (€)": f"{target:.2f}",
            "Cours Cible Min (€)": min_sell_price,
            "Cours Actuel (€)": current if current else "N/A",
            "Gain Net Actuel (€)": net_pnl if net_pnl is not None else "N/A",
            "Objectif Atteint": "✅ OUI (VENDRE)" if is_target_reached else "⏳ Non"
        })

    df_display = pd.DataFrame(results)

    # METRIQUES CLÉS
    col1, col2, col3 = st.columns(3)
    total_invested = sum([row["Quantite"] * row["PRU"] + row["FraisAchat"] for idx, row in df_positions.iterrows()])
    total_net_pnl = sum([r["Gain Net Actuel (€)"] for r in results if isinstance(r["Gain Net Actuel (€)"], (int, float))])
    
    col1.metric("Capital Investi Total", f"{total_invested:.2f} €")
    col2.metric("Plus-Value Nette Globale", f"{total_net_pnl:+.2f} €", delta_color="normal")
    col3.metric("Lignes en Objectif Vente", f"{sum(1 for r in results if '✅' in r['Objectif Atteint'])} / {len(results)}")

    st.divider()

    # TABLEAU RECAPITULATIF
    def highlight_alert(row):
        if "OUI" in str(row["Objectif Atteint"]):
            return ['background-color: #d4edda; color: #155724; font-weight: bold'] * len(row)
        return [''] * len(row)

    st.dataframe(df_display.style.apply(highlight_alert, axis=1), use_container_width=True)

    # ALERTE & NOTIFICATIONS
    if alert_triggered:
        st.balloons()
        st.success("🎉 **Objectif atteint sur au moins une position !**")
        for r in results:
            if "OUI" in r["Objectif Atteint"]:
                msg = f"🔔 **ALERTE PEA - {r['Ticker']}**\n- Cours actuel : **{r['Cours Actuel (€)']} €**\n- Cours cible min : **{r['Cours Cible Min (€)']} €**\n- Gain net potentiel : **+{r['Gain Net Actuel (€)']} €**"
                st.info(msg)
                if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
                    telegram_msg = f"🚀 *ALERTE VENTE PEA* : {r['Ticker']}\n\n• Cours Actuel : `{r['Cours Actuel (€)']} €`\n• Seuil Cible : `{r['Cours Cible Min (€)']} €`\n• Gain Net : `+{r['Gain Net Actuel (€)']} €`"
                    send_telegram_alert(telegram_msg)

    # AUTO REFRESH
    st.divider()
    col_ref, col_info = st.columns([1, 3])
    with col_ref:
        refresh_sec = st.selectbox("Rafraîchissement automatique", options=[900, 1800, 3600], format_func=lambda x: f"{x//60} minutes", index=1)
    with col_info:
        st.caption(f"Dernier rafraîchissement à {pd.Timestamp.now().strftime('%H:%M:%S')}. Auto-rafraîchissement toutes les {refresh_sec//60} min.")
        
    time.sleep(1)
else:
    st.info("👋 Votre portefeuille est vide. Ajoutez vos premières actions dans le panneau latéral de gauche.")
