import pandas as pd
import QuantLib as ql

convention = ql.ModifiedFollowing
calendar = ql.TARGET()
base = ql.Actual360()

trade_date = ql.Date(18, 5, 2026)
ql.Settings.instance().evaluationDate = trade_date

settlement_days = 2
settlement_date = calendar.advance(trade_date, ql.Period(settlement_days, ql.Days), convention)


df = pd.read_csv('ois_rates.csv', index_col="Maturity")

helpers = []

for maturity, row in df.iterrows():
    rate_quote = ql.SimpleQuote(row['OIS_Rates'] / 100.0)
    quote_handle = ql.QuoteHandle(rate_quote)
    period = ql.Period(maturity)
    

    if period <= ql.Period("1Y"):
        helper = ql.DepositRateHelper(quote_handle, period, settlement_days, 
                                      calendar, convention, False, base)
    else:
        index = ql.OvernightIndex("OIS_Index", settlement_days, ql.EURCurrency(), calendar, base)
        helper = ql.OISRateHelper(settlement_days, period, quote_handle, index)
        
    helpers.append(helper)

yield_curve = ql.PiecewiseLinearZero(settlement_days, calendar, helpers, base)
yield_curve.enableExtrapolation() 

ZC_complet = {}
for maturity in df.index:
    end_date = calendar.advance(settlement_date, ql.Period(maturity), convention)
    ZC_complet[maturity] = yield_curve.discount(end_date)

df_res = pd.DataFrame.from_dict(ZC_complet, orient='index', columns=['ZC_Bootstrapped'])
print(df_res)