#!/usr/bin/python3

import os
import time
import requests
import finnhub
from datetime import datetime
from plyer import notification
from currency_converter import CurrencyConverter

# Setup client
finnhub_client = finnhub.Client(api_key="btd5c0748v6t4umjee5g")

# Keep track of notifications already sent
notif_buffer = []

invest_val = []


def calculate_SMA(close_prices, time_period):
    """
    Daily SMA is calculated by adding the most recent closing prices and then dividing that number by the number
    of days.
    :param close_prices: all closing prices in stock historical data
    :param time_period: number of days / data points, e.g. 50,200
    :return: Simple Moving Average (SMA)
    """
    sma = close_prices.copy()
    for j in range(time_period - 1, len(close_prices)):
        total = 0
        for k in range(j - time_period + 1, j + 1):
            total += close_prices[k]
        sma[j - 1] = total / time_period

    return sma[len(sma) - 2]


def get_date_from_timestamp(timestamp):
    return datetime.strftime(datetime.fromtimestamp(timestamp), "%d/%m/%Y")


def send_notification(message, icon):
    if icon == 'g':
        icon_path = "icons/up.ico"
    elif icon == 'r':
        icon_path = "icons/down.ico"
    else:
        icon_path = "icons/v.ico"

    if message not in notif_buffer:
        notification.notify(title="Findicate", message=message, app_icon=icon_path, timeout=20)
        notif_buffer.append(message)


class Stock:
    def __init__(self, ticker, start_timestamp):
        """
        Finnhub supports resolutions of: '1', '5', '15', '30', '60', 'D', 'W', 'M',
        API call 'stock_candles' returns data of: close, high, low, open, response_status, timestamp, volume
        e.g. {'c': [0.0], 'h': [0.0], 'l': [0.0], 'o': [0.0], 's': 'ok', 't': [1603065600], 'v': [1547144]}
        @param ticker: Stock ticker symbol
        @param start_timestamp: Specify when this stock began trading
        """
        self.ticker, self.start_timestamp = ticker, int(start_timestamp)

        # Daily candles from IPO to present day
        now = int(datetime.now().timestamp())  # Current time
        resp = []

        try:
            resp = finnhub_client.stock_candles(self.ticker, '1', self.start_timestamp, now)
        except finnhub.exceptions.FinnhubAPIException as ex:
            print(ex)
            main()

        self.stock_data = {}
        if resp['s'] != 'ok':
            print("No response from Finnhub")
        else:
            # Set previous moving average values, up to previous trading day, to check against later
            self.lta, self.sta = calculate_SMA(resp['c'][:-1], 200), calculate_SMA(resp['c'][:-1], 50)

            # Set average daily volume
            total = 0
            for i in resp['v']:
                total += i
            self.avg_vol = total / len(resp['v'])

            for i in range(len(resp['c']) - 1):  # Get all data to previous market day
                # Convert timestamp to more readable date format
                day = get_date_from_timestamp(resp['t'][i])

                # Store data for this day
                self.stock_data.update({day: {'Close': resp['c'][i], 'High': resp['h'][i], 'Low': resp['l'][i],
                                              'Open': resp['o'][i], 'Vol': resp['v'][i]}})

            file_name = f"{ticker.upper()}.py"

            directory = os.path.realpath(__file__).replace("findicate.py", "")
            open(directory + "stocks/" + file_name, 'w').close()  # Make blank file
            with open(directory + "stocks/" + file_name, 'a') as the_file:
                the_file.write(f"{ticker} = {str(self.stock_data)}")

    def start(self, shares, once=False):
        flag_10, flag_15, flag_20, v_flag, ma_cross_flag = False, False, False, False, False
        start_time = time.time()
        # print("Starting...")
        while True:
            now = int(datetime.now().timestamp())
            today = get_date_from_timestamp(now)

            resp = finnhub_client.stock_candles(self.ticker, '1', now - 60 * 60 * 24, now)

            if resp['s'] == 'ok':
                # Update stock data with today's data
                close, high, low, open, vol = resp['c'][0], resp['h'][0], resp['l'][0], resp['o'][0], resp['v'][0]
                self.stock_data.update({today: {'Close': close, 'High': high, 'Low': low, 'Open': open, 'Vol': vol}})

                # Calculate current long and short term moving average values
                close_data = [self.stock_data[k]['Close'] for k in self.stock_data.keys()]
                _lta, _sta = calculate_SMA(close_data, 200), calculate_SMA(close_data, 50)

                # print(resp)
                diff = close - close_data[len(close_data) - 2]  # Difference from previous close

                perc_move = (diff / close) * 100  # Intraday percentage increase / decrease

                usd_val = shares * close
                c = CurrencyConverter()
                gbp = c.convert(usd_val, 'USD', 'GBP')
                invest_val.append(gbp)

                print(f"Price: ${round(close, 2)} | Change: {round(perc_move, 2)}% "
                      f"| Volume: {round(vol / 1000000, 3)}m | 200MA: {round(_lta, 3)} | 50MA: {round(_sta, 3)}")

                if once:
                    return gbp

                # Percentage difference from high / low of day
                range_itd_perc = (close - high) / high if close < high else (close - low) / low

                # Detect and notify large intraday moves
                if range_itd_perc < 0:
                    if range_itd_perc < -10 and not flag_10:
                        send_notification("-10% INTRADAY MOVE", 'r')
                        flag_10 = True
                    elif range_itd_perc < -15 and not flag_15:
                        send_notification("-15% INTRADAY MOVE", 'r')
                        flag_15 = True
                    elif range_itd_perc < -20 and not flag_20:
                        send_notification("-20% INTRADAY MOVE", 'r')
                        flag_20 = True
                else:
                    if range_itd_perc > 10 and not flag_10:
                        send_notification("+10% INTRADAY MOVE", 'g')
                        flag_10 = True
                    elif range_itd_perc > 15 and not flag_15:
                        send_notification("+15% INTRADAY MOVE", 'g')
                        flag_15 = True
                    elif range_itd_perc > 20 and not flag_20:
                        send_notification("+20% INTRADAY MOVE", 'g')
                        flag_20 = True

                # Detect abnormally high daily volume
                if not v_flag and vol > 15000000:
                    send_notification("HIGHER THAN AVERAGE DAILY VOLUME", 'v')
                    v_flag = True

                # Moving averages meet - signals death cross or golden cross
                if round(_sta, 2) == round(_lta, 2) and not ma_cross_flag:
                    ma_cross_flag = True
                    if self.lta < self.sta:
                        send_notification("ALERT: GOLDEN CROSS", 'g')
                    else:
                        send_notification("ALERT: DEATH CROSS", 'r')

            # Get data every 5 seconds
            time.sleep(5.0 - ((time.time() - start_time) % 5.0))
            return


def main():
    # Market close of IPO in UTC (4h ahead of eastern time) to timestamp
    ipo_date = time.mktime(datetime.strptime("28/10/2019 20:00:00", "%d/%m/%Y %H:%M:%S").timetuple())
    spce = Stock('SPCE', ipo_date)
    starttime = time.time()
    while True:
        try:
            print(spce.start(451))
        except requests.exceptions.ReadTimeout:
            print("Timeout")
            main()
        time.sleep(5.0 - ((time.time() - starttime) % 5.0))


if __name__ == "__main__":
    main()
