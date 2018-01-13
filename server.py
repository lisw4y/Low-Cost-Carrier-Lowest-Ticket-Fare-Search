import logging
from logging.handlers import RotatingFileHandler
import requests
import json
import datetime as dt
import re
import sqlite3
from enum import Enum, unique
from time import time
from calendar import monthrange

import pandas as pd
import altair as alt
import plotly.offline as offline
import plotly.graph_objs as go
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from hanziconv import HanziConv

# Set the logger
logger = logging.getLogger('server')
logger.setLevel(logging.INFO)
rfh = RotatingFileHandler('service.log', maxBytes=10240)
rfh.setLevel(logging.INFO)
rfh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s in %(filename)s - %(funcName)s: %(message)s'))
logger.addHandler(rfh)

DB_LCC_PATH = 'lcc.db'

@unique
class Airline(Enum):
    TIGERAIR_TAIWAN = 1
    VANILLA_AIR = 2
    SCOOT = 3
    PEACH_AVIATION = 4
    JETSTAR = 5

def init_prices(month, num_of_days, airline):
    data = []
    for i in range(num_of_days):
        data.append({
            'Airline': airline,
            'Date': month + '-{0:02}'.format(i + 1),
            'Price': 0
        })
    return data

def reset_prices(data, num_of_days):
    for i in range(num_of_days):
        data[i]['Price'] = 0
    return data
    
def get_fares(month, origin, destination, airlines, currency):
    result = []
    today = dt.date.today()
    num_of_days = monthrange(int(month[:4]), int(month[5:]))[1]
    success_stat = 'Succeed on getting fares of the airline with ID {0}'
    failure_stat = 'Fail on getting fares of the airline with ID {0} - {1}'
    # Use the API to fetch the JSON data directly
    if Airline.TIGERAIR_TAIWAN.value in airlines:
        data = init_prices(month, num_of_days, 'Tigerair Taiwan')
        payload = {
            'adults': '1',
            'children': '0',
            'infants': '0',
            'originStation': origin,
            'destinationStation': destination,
            'departureDate': month + '-16',
            'includeoverbooking': 'false',
            'daysBeforeAndAfter': '15',
            'locale': 'zh-TW'
        }
        try:
            response = requests.get('https://tiger-wkgk.matchbyte.net/wkapi/v1.0/flightsearch', params=payload)
            js = json.loads(response.text)
            fares = js['journeyDateMarkets'][0]['lowFares']['lowestFares']
            for i in range(num_of_days):
                if data[i]['Date'] == fares[i]['date'][:10]:
                    data[i]['Price'] = int(fares[i]['price']) if fares[i]['price'] > 0 else 0
        except Exception as e:
            reset_prices(data, num_of_days)
            logger.error(failure_stat.format(Airline.TIGERAIR_TAIWAN.value, repr(e)))
        else:
            logger.info(success_stat.format(Airline.TIGERAIR_TAIWAN.value))

        result.extend(data)
    # Use the API to fetch the JSON data directly
    if Airline.VANILLA_AIR.value in airlines:
        data = init_prices(month, num_of_days, 'Vanilla Air')
        try:
            # In Vanilla's system, additional search for transit is needed
            payload = {
                '__ts': int(time() * 1000),
                'version': '1.1'
            }
            response = requests.get('https://www.vanilla-air.com/api/booking/segment/route.json', params=payload)
            js = json.loads(response.text)
            for route in js['Result']:
                if route['BoardPoint'] == origin and route['OffPoint'] == destination:
                    transit = route['TransitPoint']
                    break
            else:
                transit = None

            payload = {
                '__ts': int(time() * 1000),
                'adultCount': '1',
                'childCount': '0',
                'couponCode': '',
                'currency': currency,
                'destination': destination,
                'infantCount': '0',
                'isMultiFlight': 'true',
                'origin': origin,
                'searchCurrency': currency,
                'targetMonth': month.replace('-', ''),
                'version': '1.0',
                'channel': 'pc'
            }
            if transit is not None:
                payload['transitPoint'] = transit
            response = requests.get('https://www.vanilla-air.com/api/booking/flight-fare/list.json', params=payload)
            js = json.loads(response.text)
            fares = js['Result'][0]['FareListOfDay']
            for i in range(num_of_days):
                data[i]['Price'] = fares[month + '-{0:02}'.format(i + 1)]['LowestFare']
        except Exception as e:
            reset_prices(data, num_of_days)
            logger.error(failure_stat.format(Airline.VANILLA_AIR.value, repr(e)))
        else:
            logger.info(success_stat.format(Airline.VANILLA_AIR.value))

        result.extend(data)

    if Airline.SCOOT.value in airlines:
        data = init_prices(month, num_of_days, 'Scoot')

        # To be constructed... fetch Scoot fares

        result.extend(data)

    if Airline.PEACH_AVIATION.value in airlines:
        data = init_prices(month, num_of_days, 'Peach Aviation')

        # To be constructed... fetch Peach Aviation fares

        result.extend(data)
    # Use requests and fake the browser to send GET requests as to fetch the data
    if Airline.JETSTAR.value in airlines:
        data = init_prices(month, num_of_days, 'Jetstar')
        payload = {
            'origin1': origin,
            'destination1': destination,
            'departuredate1': '',
            'adults': '1',
            'children': '0',
            'infants': '0',
            'currency': currency
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.84 Safari/537.36'
        }
        # Jetstar system shows data of a week for one search, so 5 times search is needed to cover the whole month
        try:
            for i in range(5):
                payload['departuredate1'] = month + '-{0:02}'.format(i * 7 + 4 if i < 4 else 28)
                response = requests.get('https://booking.jetstar.com/tw/zh/booking/search-flights', headers=headers, params=payload)
                soup = BeautifulSoup(response.text, 'html.parser')
                for li in soup.find_all('li', class_='date-selector__option'):
                    date = re.search(r'departuredate1=(\d{4}-\d{2}-\d{2})', li.attrs['data-lowfare'])
                    price = li.find('span', attrs={'data-amount': True})
                    if data[int(date[1][-2:]) - 1]['Date'] == date[1] and price is not None and re.search(r'\d', price.text):
                        data[int(date[1][-2:]) - 1]['Price'] = int(round(float(price.text.replace(',', ''))))
        except Exception as e:
            reset_prices(data, num_of_days)
            logger.error(failure_stat.format(Airline.JETSTAR.value, repr(e)))
        else:
            logger.info(success_stat.format(Airline.JETSTAR.value))

        result.extend(data)

    return result

def get_routes():
    success_stat = 'Succeed on fetching route data of the airline with ID {0}'
    failure_stat = 'Fail on fetching route data of the airline with ID {0} - {1}'
    conn = sqlite3.connect(DB_LCC_PATH)
    c = conn.cursor()
    # Tigerair Taiwan
    try:
        response = requests.get('http://www.tigerairtw.com/en/')
        data = json.loads(re.search(r'var StationList = (.+?);', response.text)[1])
        c.execute('UPDATE Route SET IsActive = 0 WHERE AirlineId = ?',
                  (Airline.TIGERAIR_TAIWAN.value, ))
        for station in data['stations']:
            if not station['airportCode'].startswith('X'):
                c.execute('SELECT Id FROM Airport WHERE Code = ?',
                          (station['airportCode'], ))
                if c.fetchone() is None:
                    c.execute('INSERT INTO Airport (Code) VALUES (?)',
                              (station['airportCode'], ))

                for market in station['markets']:
                    if not market.startswith('X'):
                        c.execute('SELECT Id FROM Airport WHERE Code = ?',
                                  (market, ))
                        if c.fetchone() is None:
                            c.execute('INSERT INTO Airport (Code) VALUES (?)',
                                      (market, ))

                        c.execute('''SELECT r.Id FROM Route r
                                     JOIN Airport fap ON r.FromAirportId = fap.Id
                                     JOIN Airport tap ON r.ToAirportId = tap.Id
                                     WHERE r.AirlineId = ? and fap.Code = ? and tap.Code = ?''',
                                  (Airline.TIGERAIR_TAIWAN.value, station['airportCode'], market))
                        if c.fetchone() is None:
                            c.execute('''INSERT INTO Route (AirlineId, FromAirportId, ToAirportId, IsActive)
                                         SELECT ?, fap.Id, tap.Id, 1 FROM Airport fap, Airport tap
                                         WHERE fap.Code = ? and tap.Code = ?''',
                                      (Airline.TIGERAIR_TAIWAN.value, station['airportCode'], market))
                        else:
                            c.execute('''UPDATE Route SET IsActive = 1
                                         WHERE AirlineId = ?
                                         AND FromAirportId = (SELECT Id FROM Airport WHERE Code = ?)
                                         AND ToAirportId = (SELECT Id FROM Airport WHERE Code = ?)''',
                                      (Airline.TIGERAIR_TAIWAN.value, station['airportCode'], market))
    except Exception as e:
        conn.rollback()
        logger.error(failure_stat.format(Airline.TIGERAIR_TAIWAN.value, repr(e)))
    else:
        conn.commit()
        logger.info(success_stat.format(Airline.TIGERAIR_TAIWAN.value))

    # Vanilla Air
    try:
        response = requests.get('https://www.vanilla-air.com/common/js/vnl.js')
        text = response.text
        for remove_line in set(re.findall(r'.*//.*', text)):
            text = text.replace(remove_line, '')
        data = json.loads(re.search(r'"oandd":({.+?})', re.sub(r'[\r\n\t ]', '', text))[1])
        c.execute('UPDATE Route SET IsActive = 0 WHERE AirlineId = ?',
                  (Airline.VANILLA_AIR.value, ))
        for station in data:
            c.execute('SELECT Id FROM Airport WHERE Code = ?',
                      (station, ))
            if c.fetchone() is None:
                c.execute('INSERT INTO Airport (Code) VALUES (?)',
                          (station, ))

            for destination in data[station]:
                c.execute('SELECT Id FROM Airport WHERE Code = ?',
                          (destination, ))
                if c.fetchone() is None:
                    c.execute('INSERT INTO Airport (Code) VALUES (?)',
                              (destination, ))

                c.execute('''SELECT r.Id FROM Route r
                             JOIN Airport fap ON r.FromAirportId = fap.Id
                             JOIN Airport tap ON r.ToAirportId = tap.Id
                             WHERE r.AirlineId = ? and fap.Code = ? and tap.Code = ?''',
                          (Airline.VANILLA_AIR.value, station, destination))
                if c.fetchone() is None:
                    c.execute('''INSERT INTO Route (AirlineId, FromAirportId, ToAirportId, IsActive)
                                 SELECT ?, fap.Id, tap.Id, 1 FROM Airport fap, Airport tap
                                 WHERE fap.Code = ? and tap.Code = ?''',
                              (Airline.VANILLA_AIR.value, station, destination))
                else:
                    c.execute('''UPDATE Route SET IsActive = 1
                                 WHERE AirlineId = ?
                                 AND FromAirportId = (SELECT Id FROM Airport WHERE Code = ?)
                                 AND ToAirportId = (SELECT Id FROM Airport WHERE Code = ?)''',
                              (Airline.VANILLA_AIR.value, station, destination))
    except Exception as e:
        conn.rollback()
        logger.error(failure_stat.format(Airline.VANILLA_AIR.value, repr(e)))
    else:
        conn.commit()
        logger.info(success_stat.format(Airline.VANILLA_AIR.value))

    # Scoot
    try:
        response = requests.get('https://www.flyscoot.com/en/')
        data = json.loads(re.search(r'<script id="city_pairs_data">(.+?)</script>', response.text)[1])
        c.execute('UPDATE Route SET IsActive = 0 WHERE AirlineId = ?',
                  (Airline.SCOOT.value, ))
        for country in data[0]:
            for airport in country['markets']:
                c.execute('SELECT Id FROM Airport WHERE Code = ?',
                          (airport['origin']['station_code'], ))
                if c.fetchone() is None:
                    c.execute('INSERT INTO Airport (Code) VALUES (?)',
                              (airport['origin']['station_code'], ))

                for dest_country in airport['destinations']:
                    for destination in dest_country['destinations']:
                        c.execute('SELECT Id FROM Airport WHERE Code = ?',
                                  (destination['station_code'], ))
                        if c.fetchone() is None:
                            c.execute('INSERT INTO Airport (Code) VALUES (?)',
                                      (destination['station_code'], ))

                        c.execute('''SELECT r.Id FROM Route r
                                     JOIN Airport fap ON r.FromAirportId = fap.Id
                                     JOIN Airport tap ON r.ToAirportId = tap.Id
                                     WHERE r.AirlineId = ? and fap.Code = ? and tap.Code = ?''',
                                  (Airline.SCOOT.value, airport['origin']['station_code'], destination['station_code']))
                        if c.fetchone() is None:
                            c.execute('''INSERT INTO Route (AirlineId, FromAirportId, ToAirportId, IsActive)
                                         SELECT ?, fap.Id, tap.Id, 1 FROM Airport fap, Airport tap
                                         WHERE fap.Code = ? and tap.Code = ?''',
                                      (Airline.SCOOT.value, airport['origin']['station_code'], destination['station_code']))
                        else:
                            c.execute('''UPDATE Route SET IsActive = 1
                                         WHERE AirlineId = ?
                                         AND FromAirportId = (SELECT Id FROM Airport WHERE Code = ?)
                                         AND ToAirportId = (SELECT Id FROM Airport WHERE Code = ?)''',
                                      (Airline.SCOOT.value, airport['origin']['station_code'], destination['station_code']))
    except Exception as e:
        conn.rollback()
        logger.error(failure_stat.format(Airline.SCOOT.value, repr(e)))
    else:
        conn.commit()
        logger.info(success_stat.format(Airline.SCOOT.value))

    # Peach Aviation
    try:
        response = requests.get('http://www.flypeach.com/widget/widgetvars.js')
        response.encoding = 'UTF-8'
        data = json.loads(re.search(r'routes:(.+?),landingPages:', re.sub(r'[\r\n\t ]', '', response.text))[1].replace('ori', '"ori"').replace('dest', '"dest"'))
        c.execute('UPDATE Route SET IsActive = 0 WHERE AirlineId = ?',
                  (Airline.PEACH_AVIATION.value, ))
        for route in data:
            c.execute('SELECT Id FROM Airport WHERE Code = ?',
                      (route['ori'], ))
            if c.fetchone() is None:
                c.execute('INSERT INTO Airport (Code) VALUES (?)',
                          (route['ori'], ))
            c.execute('SELECT Id FROM Airport WHERE Code = ?',
                      (route['dest'], ))
            if c.fetchone() is None:
                c.execute('INSERT INTO Airport (Code) VALUES (?)',
                          (route['dest'], ))

            c.execute('''SELECT r.Id FROM Route r
                         JOIN Airport fap ON r.FromAirportId = fap.Id
                         JOIN Airport tap ON r.ToAirportId = tap.Id
                         WHERE r.AirlineId = ? and fap.Code = ? and tap.Code = ?''',
                      (Airline.PEACH_AVIATION.value, route['ori'], route['dest']))
            if c.fetchone() is None:
                c.execute('''INSERT INTO Route (AirlineId, FromAirportId, ToAirportId, IsActive)
                             SELECT ?, fap.Id, tap.Id, 1 FROM Airport fap, Airport tap
                             WHERE fap.Code = ? and tap.Code = ?''',
                          (Airline.PEACH_AVIATION.value, route['ori'], route['dest']))
            else:
                c.execute('''UPDATE Route SET IsActive = 1
                             WHERE AirlineId = ?
                             AND FromAirportId = (SELECT Id FROM Airport WHERE Code = ?)
                             AND ToAirportId = (SELECT Id FROM Airport WHERE Code = ?)''',
                          (Airline.PEACH_AVIATION.value, route['ori'], route['dest']))
    except Exception as e:
        conn.rollback()
        logger.error(failure_stat.format(Airline.PEACH_AVIATION.value, repr(e)))
    else:
        conn.commit()
        logger.info(success_stat.format(Airline.PEACH_AVIATION.value))

    # Jetstar
    driver = webdriver.Chrome()
    wait = WebDriverWait(driver, 10)
    try:
        c.execute('UPDATE Route SET IsActive = 0 WHERE AirlineId = ?',
                  (Airline.JETSTAR.value, ))
        driver.get('http://www.jetstar.com/tw/zh/home')
        driver.execute_script('document.querySelector("button[data-direction-id = origin]").click();')
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        panel_from = soup.find('div', id='origin-panel01')
        for idx, airport_from in enumerate(panel_from.find_all('button', attrs={'data-value': True})):
            driver.execute_script('document.querySelector("#origin-panel01 button[data-value = \'{0}\']").click();'.format(airport_from.attrs['data-value']))
            if idx != 0:
                wait.until(EC.url_changes(driver.current_url))
            driver.execute_script('document.querySelector("button[data-direction-id = destination]").click();')
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'button[data-direction-id = destination][aria-expanded = true]')))
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            panel_to = soup.find('div', id='destination-panel01')
            for airport_to in panel_to.find_all('button', attrs={'data-value': True}):
                driver.execute_script('document.querySelector("#destination-panel01 button[data-value = \'{0}\']").click();'.format(airport_to.attrs['data-value']))
                wait.until(EC.url_changes(driver.current_url))
                codes = re.search(r'origin=([A-Z]{3})&destination=([A-Z]{3})', driver.current_url)
                c.execute('SELECT Id FROM Airport WHERE Code = ?',
                          (codes[1], ))
                if c.fetchone() is None:
                    c.execute('INSERT INTO Airport (Code) VALUES (?)',
                              (codes[1], ))
                c.execute('SELECT Id FROM Airport WHERE Code = ?',
                          (codes[2], ))
                if c.fetchone() is None:
                    c.execute('INSERT INTO Airport (Code) VALUES (?)',
                              (codes[2], ))

                c.execute('''SELECT r.Id FROM Route r
                             JOIN Airport fap ON r.FromAirportId = fap.Id
                             JOIN Airport tap ON r.ToAirportId = tap.Id
                             WHERE r.AirlineId = ? and fap.Code = ? and tap.Code = ?''',
                          (Airline.JETSTAR.value, codes[1], codes[2]))
                if c.fetchone() is None:
                    c.execute('''INSERT INTO Route (AirlineId, FromAirportId, ToAirportId, IsActive)
                                 SELECT ?, fap.Id, tap.Id, 1 FROM Airport fap, Airport tap
                                 WHERE fap.Code = ? and tap.Code = ?''',
                              (Airline.JETSTAR.value, codes[1], codes[2]))
                else:
                    c.execute('''UPDATE Route SET IsActive = 1
                                 WHERE AirlineId = ?
                                 AND FromAirportId = (SELECT Id FROM Airport WHERE Code = ?)
                                 AND ToAirportId = (SELECT Id FROM Airport WHERE Code = ?)''',
                              (Airline.JETSTAR.value, codes[1], codes[2]))
    except Exception as e:
        conn.rollback()
        logger.error(failure_stat.format(Airline.JETSTAR.value, repr(e)))
    else:
        conn.commit()
        logger.info(success_stat.format(Airline.JETSTAR.value))

    driver.quit()

    # Update English information of airports
    capital = None
    c.execute('SELECT Code FROM Airport ORDER BY Code')
    for row in c.fetchall():
        try:
            if row[0][0] != capital:
                capital = row[0][0]
                response = requests.get('https://en.wikipedia.org/wiki/List_of_airports_by_IATA_code:_' + capital)
                soup = BeautifulSoup(response.text, 'html.parser')
                table = soup.find('table', class_='wikitable sortable')
            tds = table.find(string=row[0]).find_parent('tr').find_all('td')
            airport_name = re.split(r'[\[\(\d]', tds[2].text)[0].strip()
            country_name = re.sub(r'\d', '', tds[3].text.split(',')[-1]).strip()
            c.execute('SELECT Id FROM Country WHERE Name = ?',
                      (country_name, ))
            if c.fetchone() is None:
                c.execute('INSERT INTO Country (Name) VALUES (?)',
                          (country_name, ))
            c.execute('UPDATE Airport SET Name = ?, CountryId = (SELECT Id FROM Country WHERE Name = ?) WHERE Code = ?',
                      (airport_name, country_name, row[0]))
        except Exception as e:
            logger.error('Fail on updating English info of the airport with code {0} - {1}'.format(row[0], repr(e)))

    # Update Chinese information of airports
    capital = None
    c.execute('SELECT Code FROM Airport ORDER BY Code')
    for row in c.fetchall():
        try:
            if row[0][0] != capital:
                capital = row[0][0]
                response = requests.get('https://zh.wikipedia.org/wiki/%E5%9B%BD%E9%99%85%E8%88%AA%E7%A9%BA%E8%BF%90%E8%BE%93%E5%8D%8F%E4%BC%9A%E6%9C%BA%E5%9C%BA%E4%BB%A3%E7%A0%81_(' + capital + ')')
                soup = BeautifulSoup(response.text, 'html.parser')
                table = soup.select('table.wikitable.sortable')[0]
            tds = table.find(string=row[0]).find_parent('tr').find_all('td')
            # Pages of these capitals have a different webpage structure
            start_idx = 1 if capital in ['H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'R', 'S', 'T', 'U'] else 2
            airport_name = tds[start_idx].text.split('（')[0].strip()
            country_name = tds[start_idx + 2].text.strip()
            c.execute('UPDATE Country SET NameZhTW = ? WHERE Id = (SELECT CountryId FROM Airport WHERE Code = ?)',
                      (HanziConv.toTraditional(country_name), row[0]))
            if re.search(r'[A-Za-z]', airport_name) is None:
                c.execute('UPDATE Airport SET NameZhTW = ? WHERE Code = ?',
                          (HanziConv.toTraditional(airport_name), row[0]))
        except Exception as e:
            logger.error('Fail on updating Chinese info of the airport with code {0} - {1}'.format(row[0], repr(e)))

    # Update currency codes of countries
    c.execute('SELECT Name FROM Country')
    for row in c.fetchall():
        try:
            response = requests.get('https://en.wikipedia.org/wiki/List_of_circulating_currencies')
            soup = BeautifulSoup(response.text, 'html.parser')
            tds = soup.find('table', class_='wikitable sortable').find(string=row[0]).find_parent('tr').find_all('td')
            currency_code = tds[3].text.strip()
            c.execute('UPDATE Country SET Currency = ? WHERE Name = ?',
                      (currency_code, row[0]))
        except Exception as e:
            logger.error('Fail on updating the currency of the country {0} - {1}'.format(row[0], repr(e)))

    conn.commit()
    conn.close()

def get_visualized_data(fares):
    data = pd.DataFrame(fares)

    # altair line chart
    chart = alt.Chart(data).mark_line().encode(
        color='Airline:N',
        x='Date:O',
        y='Price:Q'
    )

    # plotly table
    trace = go.Table(
        header={
            'values': data.columns,
            'fill': {
                'color': '#a1c3d1'
            },
            'align': ['center']
        },
        cells={
            'values': [data.Airline, data.Date, data.Price],
            'fill': {
                'color': '#EDFAFF'
            },
            'align': ['center']
        })
    fig = {
        'data': [trace]
    }

    return {
        'line': chart.to_json(),
        'table': offline.plot(fig, include_plotlyjs = False, output_type = 'div').replace('"', '\'')
    }

if __name__ == '__main__':
    get_routes()
