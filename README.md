
---------- Quick presentation of the code ----------

The code is used to build a yield curve (Discounting Curve) using Overnight Index Swaps (OIS) with LSEG/ICAP Data on OIS from the 18th May 2026 available in 'ois_rates.csv'.

The code is fully reproducible on your device using the environment specified in 'uv.lock'. It has been built for futher use in pricing interest rate products such as swaptions, caps, floors, etc.

---------- Yield Curve Toolkit ----------

In the multicurve world after the 2008 financial crisis, two types of curves are now
used to price interest rates products:

1. Discounting Curve: This curve is used to discount future cash flows. It is usually
built from Overnight Index Swaps (OIS).
2. Forecasting Curve: This curve is used to forecast future cash flows. It is usually based on the floating rates of the contract (IBOR rates such as EURIBOR).

---------- Useful Reminders ----------

Basis A/360: Means Actual/360

Modified Following: If the payment date is not a business day, we move to the next date, as long as this date is in the same calendar month. Otherwise, we move to the previous business day. (cf. ISDA Definition 2021)

Target: Official Calendar of TARGET (Trans-European Automated Real-time Gross settlement Express Transfer System) from the ECB

Spot: T + 2 business days

Overnight Index Swaps (OIS): Interest Rate Swaps where the floating leg is benchmarked against an overnight index (usually €STR for the Eurozone).
Market practice on OIS: Effective Date Spot (T+2), payment frequency 1 Year, Modified Following and Target Calendar, Basis A/360.

