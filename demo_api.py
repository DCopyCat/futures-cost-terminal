"""Synthetic data for UI smoke testing. NEVER treat as market quotes."""
class DemoAPI:
    symbols = {'SHFE':'rb2701','INE':'sc2701','CZCE':'SH701','DCE':'m2701','CFFEX':'IF2612','GFEX':'lc2701'}
    prices = {'SHFE':3040,'INE':690,'CZCE':1486,'DCE':3200,'CFFEX':4049,'GFEX':95280}
    def get_futures_daily(self, start_date, end_date, market):
        from datetime import date, timedelta
        day = date(int(end_date[:4]),int(end_date[4:6]),int(end_date[6:]))
        while day.weekday() >= 5: day-=timedelta(days=1)
        s=self.symbols[market]
        return [{'symbol':s,'date':day.strftime('%Y%m%d'),'variety':''.join(c for c in s if c.isalpha()),
                 'settle':self.prices[market], 'open_interest':56000,'volume':30000}]
    def futures_settle(self,date,market):
        return [{'symbol':self.symbols[market],'date':date,'spec_long_margin_ratio':.12,
                 'spec_short_margin_ratio':.12,'trade_fee_ratio':.0002,'close_today_fee_ratio':.0002}]
