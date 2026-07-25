"""
================================================================================
INTERPOLATION MONOTONE CONVEX  -  Hagan & West (2006, 2007)
================================================================================
Traduction DIRECTE du pseudo-code VBA de Hagan & West (2007, Appendix),
appliquée aux forwards discrets déduits du bootstrap OIS €STR.

Chaîne complète :
   bootstrap_ois.py  ->  P(0,T_i) aux noeuds  ->  f^d_i  ->  monotone convex
                                                              ->  f(t), r(t), P(0,t) continus

CORRESPONDANCE ÉQUATIONS (papier 2007) :
   f^d_i            : forward discret de l'intervalle              (éq. 5, 11)
   f_i (nodal)      : valeur du forward instantané au noeud        (éq. 22-24)
   collar positivité: bornage des f_i                              (Step 3 pseudo-code)
   g(x)             : forme quadratique normalisée sur [0,1]       (éq. 25, 27)
   4 zones (i)-(iv) : corrections de monotonicité                  (éq. 28-34)
   r(t) via integ.  : récupération du taux zéro                    (éq. 12)

Les conditions de zone et les formules ci-dessous sont copiées EXACTEMENT du
pseudo-code VBA (fonctions Forward et Interpolant), y compris les primitives
fermées de l'intégrale de g (aucune intégration numérique).
================================================================================
"""

import numpy as np
import pandas as pd


def collar(a, b, c):
    """collar(a,b,c) = max(a, min(b,c))  -- utilitaire du pseudo-code."""
    return max(a, min(b, c))


class MonotoneConvex:
    """
    Interpolateur monotone convex de Hagan & West.

    Entrées :
        terms  : maturités T_1..T_n (années), croissantes. T_0=0 ajouté en interne.
        values : soit les taux zéro r_i (rate_input=True),
                 soit directement les forwards discrets f^d_i (rate_input=False).
        negative_forwards_allowed : si False, applique le collar de positivité.

    Le pseudo-code VBA indexe f^d sur 1..n et f (nodal) sur 0..n.
    On reproduit fidèlement cette indexation via des listes 0-basées où
    fdiscrete[i] correspond à f^d_i (fdiscrete[0] inutilisé).
    """

    def __init__(self, terms, values, rate_input=True,
                 negative_forwards_allowed=False):
        # --- extension de la courbe à t=0 (Terms(0)=0, Values(0)=Values(1)) ---
        self.terms = np.concatenate([[0.0], np.asarray(terms, float)])
        vals       = np.concatenate([[values[0]], np.asarray(values, float)])
        self.n     = len(self.terms) - 1
        self.neg_allowed = negative_forwards_allowed

        # =====================================================================
        # STEP 1  -  forwards discrets f^d_i           (éq. 5 / 11 ; VBA step 1)
        # =====================================================================
        # Si l'input est un taux zéro r_i : f^d_i = (r_i T_i - r_{i-1} T_{i-1})/(T_i - T_{i-1})
        # Si l'input est déjà un forward discret : on le prend tel quel.
        self.fdiscrete = np.zeros(self.n + 1)   # index 1..n utile
        if rate_input:
            for j in range(1, self.n + 1):
                self.fdiscrete[j] = (
                    self.terms[j] * vals[j] - self.terms[j-1] * vals[j-1]
                ) / (self.terms[j] - self.terms[j-1])
        else:
            for j in range(1, self.n + 1):
                self.fdiscrete[j] = vals[j]

        # on garde les r_i T_i pour la reconstruction de r(t) (éq. 12)
        self.rt = self.terms * vals   # rt[i] = r_i * T_i  (= -ln P(0,T_i))

        # =====================================================================
        # STEP 2  -  forwards nodaux f_i               (éq. 22-24 ; VBA step 2)
        # =====================================================================
        self.f = np.zeros(self.n + 1)   # f_0 .. f_n
        for j in range(1, self.n):
            self.f[j] = (
                (self.terms[j] - self.terms[j-1]) / (self.terms[j+1] - self.terms[j-1])
                * self.fdiscrete[j+1]
                + (self.terms[j+1] - self.terms[j]) / (self.terms[j+1] - self.terms[j-1])
                * self.fdiscrete[j]
            )

        # =====================================================================
        # STEP 3  -  bornes de positivité (collar)     (éq. 60-62 ; VBA step 3)
        # =====================================================================
        # f_0 et f_n calculés puis collarés ; f_i (1..n-1) collarés aussi.
        if not negative_forwards_allowed:
            self.f[0] = collar(0.0,
                               self.fdiscrete[1] - 0.5 * (self.f[1] - self.fdiscrete[1]),
                               2 * self.fdiscrete[1])
            self.f[self.n] = collar(0.0,
                               self.fdiscrete[self.n] - 0.5 * (self.f[self.n-1] - self.fdiscrete[self.n]),
                               2 * self.fdiscrete[self.n])
            for j in range(1, self.n):
                self.f[j] = collar(0.0, self.f[j],
                                   2 * min(self.fdiscrete[j], self.fdiscrete[j+1]))
        else:
            # sans contrainte de positivité : f_0, f_n via (23)-(24) sans collar
            self.f[0] = self.fdiscrete[1] - 0.5 * (self.f[1] - self.fdiscrete[1])
            self.f[self.n] = self.fdiscrete[self.n] - 0.5 * (self.f[self.n-1] - self.fdiscrete[self.n])

    # -------------------------------------------------------------------------
    def _last_index(self, t):
        """i unique tel que t in [T_i, T_{i+1})  (fonction LastIndex du VBA)."""
        # recherche le plus grand i avec terms[i] <= t
        i = np.searchsorted(self.terms, t, side='right') - 1
        return int(min(max(i, 0), self.n - 1))

    # -------------------------------------------------------------------------
    def forward(self, t):
        """
        Forward instantané f(t).  Traduction exacte de la fonction VBA 'Forward'.
        Extrapolation plate sur le forward hors [T_0, T_n] (cf. §6).
        """
        if t <= 0:
            return self.f[0]
        if t >= self.terms[self.n]:
            # extrapolation plate du forward = f_n
            return self.f[self.n]

        i = self._last_index(t)
        # x de l'éq. (25)
        x = (t - self.terms[i]) / (self.terms[i+1] - self.terms[i])
        g0 = self.f[i]   - self.fdiscrete[i+1]
        g1 = self.f[i+1] - self.fdiscrete[i+1]

        G = self._g_value(x, g0, g1)
        # éq. (26) : f(t) = g(x) + f^d_{i+1}
        return G + self.fdiscrete[i+1]

    # -------------------------------------------------------------------------
    @staticmethod
    def _g_value(x, g0, g1):
        """
        g(x) selon les 4 zones -- conditions EXACTES du pseudo-code VBA 'Forward'.
        Frontières définies par g1 = -2 g0 et g0 = -2 g1 (donc g1 = -0.5 g0).
        """
        if x == 0:
            return g0
        if x == 1:
            return g1

        # ----- zone (i) : déjà monotone, forme de base (éq. 27) -----
        if (g0 < 0 and -0.5 * g0 <= g1 <= -2 * g0) or \
           (g0 > 0 and -2 * g0 <= g1 <= -0.5 * g0):
            return g0 * (1 - 4*x + 3*x**2) + g1 * (-2*x + 3*x**2)

        # ----- zone (ii) : plateau plat au début, puis quadratique (éq. 28-29) -----
        elif (g0 < 0 and g1 > -2 * g0) or (g0 > 0 and g1 < -2 * g0):
            eta = (g1 + 2 * g0) / (g1 - g0)          # (29)
            if x <= eta:
                return g0
            else:
                return g0 + (g1 - g0) * ((x - eta) / (1 - eta))**2

        # ----- zone (iii) : quadratique puis plateau plat (éq. 30-31) -----
        elif (g0 > 0 and 0 > g1 > -0.5 * g0) or (g0 < 0 and 0 < g1 < -0.5 * g0):
            eta = 3 * g1 / (g1 - g0)                 # (31)
            if x < eta:
                return g1 + (g0 - g1) * ((eta - x) / eta)**2
            else:
                return g1

        # ----- cas trivial g0 = g1 = 0 -----
        elif g0 == 0 and g1 == 0:
            return 0.0

        # ----- zone (iv) : deux quadratiques raccordées en eta (éq. 32-34) -----
        else:
            eta = g1 / (g1 + g0)                     # (33)
            A = -g0 * g1 / (g0 + g1)                 # (34)
            if x <= eta:
                return A + (g0 - A) * ((eta - x) / eta)**2
            else:
                return A + (g1 - A) * ((x - eta) / (1 - eta))**2

    # -------------------------------------------------------------------------
    def zero_rate_times_t(self, t):
        """
        r(t) * t  via l'éq. (12) : primitive fermée de g par zone.
        Traduction exacte de la fonction VBA 'Interpolant' (renvoie r(t)*t via
        Terms(i)*Values(i) + f^d*(t-T_i) + G, puis on divise par t pour r(t)).
        Ici on renvoie directement r(t)*t = -ln P(0,t).
        """
        if t <= 0:
            return 0.0
        if t > self.terms[self.n]:
            # extrapolation : forward plat = f_n au-delà de T_n
            base = self.rt[self.n]
            return base + self.f[self.n] * (t - self.terms[self.n])

        i = self._last_index(t)
        L = self.terms[i+1] - self.terms[i]
        x = (t - self.terms[i]) / L
        g0 = self.f[i]   - self.fdiscrete[i+1]
        g1 = self.f[i+1] - self.fdiscrete[i+1]

        # G = integrale de g de 0 a x, multipliee par L (primitives closes du VBA)
        if x == 0 or x == 1:
            G = 0.0 if x == 0 else self._integral_full(g0, g1, L)
            if x == 0:
                G = 0.0
        # zone (i)
        if not (x == 0 or x == 1):
            if (g0 < 0 and -0.5 * g0 <= g1 <= -2 * g0) or \
               (g0 > 0 and -2 * g0 <= g1 <= -0.5 * g0):
                G = L * (g0 * (x - 2*x**2 + x**3) + g1 * (-x**2 + x**3))
            # zone (ii)
            elif (g0 < 0 and g1 > -2 * g0) or (g0 > 0 and g1 < -2 * g0):
                eta = (g1 + 2 * g0) / (g1 - g0)
                if x <= eta:
                    G = g0 * (t - self.terms[i])
                else:
                    G = g0 * (t - self.terms[i]) + (g1 - g0) * (x - eta)**3 / (1 - eta)**2 / 3 * L
            # zone (iii)
            elif (g0 > 0 and 0 > g1 > -0.5 * g0) or (g0 < 0 and 0 < g1 < -0.5 * g0):
                eta = 3 * g1 / (g1 - g0)
                if x < eta:
                    G = L * (g1 * x - 1/3 * (g0 - g1) * ((eta - x)**3 / eta**2 - eta))
                else:
                    G = L * (2/3 * g1 + 1/3 * g0) * eta + g1 * (x - eta) * L
            # trivial
            elif g0 == 0 and g1 == 0:
                G = 0.0
            # zone (iv)
            else:
                eta = g1 / (g1 + g0)
                A = -g0 * g1 / (g0 + g1)
                if x <= eta:
                    G = L * (A * x - 1/3 * (g0 - A) * ((eta - x)**3 / eta**2 - eta))
                else:
                    G = L * (2/3 * A + 1/3 * g0) * eta \
                        + L * (A * (x - eta) + (g1 - A) / 3 * (x - eta)**3 / (1 - eta)**2)

        # éq. (12) : r(t) t = r_i T_i + f^d_{i+1} (t - T_i) + G
        return self.rt[i] + self.fdiscrete[i+1] * (t - self.terms[i]) + G

    def _integral_full(self, g0, g1, L):
        # integrale de g sur tout l'intervalle = 0 par construction (éq. i)
        return 0.0

    def zero_rate(self, t):
        """r(t) continu."""
        if t <= 0:
            return self.f[0]
        return self.zero_rate_times_t(t) / t

    def discount(self, t):
        """P(0,t) = exp(-r(t) t)."""
        return np.exp(-self.zero_rate_times_t(t))


# =============================================================================
# APPLICATION AUX DONNÉES BOOTSTRAPPÉES
# =============================================================================
if __name__ == "__main__":
    # --- lecture des discount factors issus du bootstrap ---
    boot = pd.read_csv("bootstrapped_discount_factors.csv")
    T = boot["T (yrs)"].values
    P = boot["P(0,T)"].values
    r = boot["ZeroRate(%)"].values / 100.0   # taux zéro continus

    # --- construction de l'interpolateur sur les taux zéro ---
    mc = MonotoneConvex(T, r, rate_input=True, negative_forwards_allowed=False)

    # --- 1) contrôle de repricing exact aux noeuds (critère (1) Hagan-West) ---
    print("=== Repricing aux noeuds (P interpolé vs P bootstrappé) ===")
    max_err = 0.0
    for Ti, Pi in zip(T, P):
        P_interp = mc.discount(Ti)
        err = abs(P_interp - Pi)
        max_err = max(max_err, err)
    print(f"Erreur max sur P(0,T) aux noeuds : {max_err:.2e}")

    # --- 2) positivité et continuité du forward instantané ---
    print("\n=== Forward instantané f(t) sur une grille fine ===")
    ts = np.linspace(0.05, 60, 1200)
    fs = np.array([mc.forward(t) for t in ts])
    print(f"min f(t) = {fs.min()*100:.4f}%   max f(t) = {fs.max()*100:.4f}%")
    print(f"Tous positifs : {np.all(fs > 0)}")
    # continuité : pas de saut brutal entre points consécutifs
    jumps = np.abs(np.diff(fs))
    print(f"Saut max entre points adjacents (grille 1200 pts) : {jumps.max()*100:.4f}%")

    # --- 3) échantillon de la courbe forward ---
    print("\n=== Échantillon f(t) ===")
    for t in [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 25, 30, 40, 50]:
        print(f"  t={t:5.1f}  f(t)={mc.forward(t)*100:6.4f}%   "
              f"r(t)={mc.zero_rate(t)*100:6.4f}%   P(0,t)={mc.discount(t):.6f}")

    # --- sauvegarde d'une grille fine pour tracés / calcul de theta(t) ---
    grid = pd.DataFrame({
        "t": ts,
        "forward": fs,
        "zero_rate": [mc.zero_rate(t) for t in ts],
        "discount": [mc.discount(t) for t in ts],
    })
    grid.to_csv("monotone_convex_curve.csv", index=False)
    print("\nGrille fine sauvegardée dans monotone_convex_curve.csv")