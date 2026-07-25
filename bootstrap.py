"""
================================================================================
BOOTSTRAP DE LA COURBE OIS €STR  -  Discount factors P(0,T)
================================================================================
Objectif : construire la courbe de discount factors P(0,T) qui reprice
exactement les taux de swaps OIS €STR observés sur le marché (18 mai 2026).

Cadre single-curve : €STR étant le taux risk-free de référence, la même courbe
sert au discounting et au forecasting (pas de double-curve EURIBOR/EONIA).

RAPPEL DES ÉQUATIONS (notation du mémoire) :
  - Taux de swap forward (Brigo & Mercurio) :
        S_{a,b}(t) = [P(t,T_a) - P(t,T_b)] / Level_{a,b}(t)          (3.3)
        Level_{a,b}(t) = sum_i tau_i * P(t,T_i)
  - Cas spot-starting (bootstrap, t=0, T_a=0 => P(0,0)=1) :
        S_n = [1 - P(0,T_n)] / Level_{0,n}(0)                        (3.4)
  - Bootstrap séquentiel, isolation de P(0,T_n) :
        P(0,T_n) = [1 - S_n * sum_{i=1}^{n-1} tau_i P(0,T_i)]
                   / [1 + S_n * tau_n]                               (3.5)

Le lien avec Hagan & West intervient APRÈS ce bootstrap : les P(0,T_i) obtenus
ici aux noeuds servent d'input à l'interpolation monotone convex (calcul des
forwards discrets f^d_i, éq. 5 et 11 de leur papier).
================================================================================
"""

import pandas as pd
import QuantLib as ql

# -----------------------------------------------------------------------------
# 1. CONVENTIONS DE MARCHÉ €STR
# -----------------------------------------------------------------------------
# €STR : Act/360, calendrier TARGET, fixing lag T+0, settlement des swaps T+2.
# Modified Following pour le roll des dates tombant un jour non ouvré.
calendar    = ql.TARGET()
day_count   = ql.Actual360()
convention  = ql.ModifiedFollowing
settle_days = 2                       # J+2 pour le règlement des swaps OIS EUR

# Date de trade = date d'observation du marché
trade_date = ql.Date(18, 5, 2026)
ql.Settings.instance().evaluationDate = trade_date

# Date de règlement (spot) = trade + 2 jours ouvrés
settlement_date = calendar.advance(trade_date, ql.Period(settle_days, ql.Days), convention)

# -----------------------------------------------------------------------------
# 2. LECTURE DES DONNÉES
# -----------------------------------------------------------------------------
df = pd.read_csv("ois_rates.csv", index_col="Maturity")

# Index €STR natif de QuantLib : bonnes conventions (Act/360, TARGET, lag 0).
# On le relie plus bas à la courbe en cours de construction.
estr = ql.Estr()

# -----------------------------------------------------------------------------
# 3. CONSTRUCTION DES HELPERS DE BOOTSTRAP
# -----------------------------------------------------------------------------
# Chaque helper encode une équation de repricing (3.4) pour une maturité donnée.
# QuantLib résout ensuite le système séquentiel (3.5) en interne.
#
# CHOIX MÉTHODOLOGIQUE IMPORTANT :
# Sur €STR, TOUS les points cotés (y compris courts : 1W, 1M, ...) sont des
# SWAPS OIS (fixe vs €STR composé), PAS des dépôts. On utilise donc
# OISRateHelper pour toutes les maturités -> cohérence de la convention de
# capitalisation (composition overnight), contrairement à DepositRateHelper
# qui suppose un taux linéaire simple.
helpers = []
for maturity, row in df.iterrows():
    rate   = row["OIS_Rates"] / 100.0          # les taux du CSV sont en %
    quote  = ql.QuoteHandle(ql.SimpleQuote(rate))
    tenor  = ql.Period(maturity)               # '1W', '3M', '2Y', ... parsés directement

    helper = ql.OISRateHelper(
        settle_days,        # settlement lag (T+2)
        tenor,              # maturité du swap
        quote,              # taux fixe coté S_n
        estr                # index overnight €STR
    )
    helpers.append(helper)

# -----------------------------------------------------------------------------
# 4. BOOTSTRAP DE LA COURBE
# -----------------------------------------------------------------------------
# PiecewiseLogLinearDiscount = interpolation log-linéaire sur les discount
# factors <=> forwards constants par morceaux ("raw"/"linear on log of discount"
# chez Hagan & West §4.4). C'est le choix le plus stable et le point de départ
# recommandé : il garantit des forwards positifs, et servira de base de contrôle
# avant d'appliquer le vrai monotone convex à la main.
#
# NB : ici on bootstrappe AUX NOEUDS. L'interpolation monotone convex (Hagan &
# West) remplacera ce log-linéaire à l'étape suivante, pour lisser les forwards
# entre noeuds et stabiliser theta(t).
curve = ql.PiecewiseLogLinearDiscount(settlement_date, helpers, day_count)
curve.enableExtrapolation()

# -----------------------------------------------------------------------------
# 5. EXTRACTION DES DISCOUNT FACTORS P(0,T)
# -----------------------------------------------------------------------------
# Pour chaque maturité cotée, on lit P(0,T) = curve.discount(date).
# Ce sont les valeurs qui repricent exactement les swaps d'input (3.4).
results = []
for maturity, row in df.iterrows():
    end_date = calendar.advance(settlement_date, ql.Period(maturity), convention)
    t   = day_count.yearFraction(settlement_date, end_date)   # T en années (Act/360)
    dfr = curve.discount(end_date)                            # P(0,T)
    zero = curve.zeroRate(end_date, day_count, ql.Continuous).rate()  # r(T) continu
    results.append((maturity, t, row["OIS_Rates"], dfr, zero * 100))

res = pd.DataFrame(results, columns=["Maturity", "T (yrs)", "OIS_Rate(%)",
                                     "P(0,T)", "ZeroRate(%)"])

pd.set_option("display.float_format", lambda v: f"{v:.6f}")
print(res.to_string(index=False))

# -----------------------------------------------------------------------------
# 6. CONTRÔLE DE REPRICING
# -----------------------------------------------------------------------------
# On revalorise chaque swap OIS avec la courbe construite : le taux fixe
# "fair" (par swap) doit retomber sur le taux d'input à ~1e-8 près, preuve
# que le bootstrap reprice exactement les instruments (critère (1) de Hagan
# & West : "all input instruments are exactly reproduced").
print("\n--- Contrôle repricing (fair rate vs input) ---")
curve_handle = ql.YieldTermStructureHandle(curve)
estr_linked  = ql.Estr(curve_handle)
max_err = 0.0
for maturity, row in df.iterrows():
    ois = ql.MakeOIS(ql.Period(maturity), estr_linked, 0.0)
    fair = ois.fairRate() * 100
    err  = abs(fair - row["OIS_Rates"])
    max_err = max(max_err, err)
print(f"Erreur maximale de repricing : {max_err:.2e} points de pourcentage")

# Sauvegarde des discount factors pour l'étape suivante (Hagan & West)
res.to_csv("bootstrapped_discount_factors.csv", index=False)
print("\nDiscount factors sauvegardés dans bootstrapped_discount_factors.csv")