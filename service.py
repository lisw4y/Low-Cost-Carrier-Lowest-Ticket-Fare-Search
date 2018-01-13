import logging
from logging.handlers import RotatingFileHandler
import sqlite3
import json
import functools

from flask import Flask, request, render_template, g, abort

from server import get_fares, get_visualized_data

# Set the logger
rfh = RotatingFileHandler('service.log', maxBytes=10240)
rfh.setLevel(logging.DEBUG)
rfh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s in %(filename)s - %(funcName)s: %(message)s'))
app = Flask(__name__)
app.logger.addHandler(rfh)

DB_LCC_PATH = 'lcc.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_LCC_PATH)
        db.execute("PRAGMA foreign_keys = ON")
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/')
def index():
    return render_template('index.html')

def compare(str_a, str_b):
    if str_a == 'Other' or str_a > str_b:
        return 1
    return -1

@app.route('/airport_codes', methods=['POST'])
def get_airport_codes():
    if 'id' not in request.form:
        app.logger.error('missing the parameter - id')
        abort(404)

    db = get_db()
    c = db.cursor()
    result = []
    # If id is 'ALL', showing all airports, otherwise showing the corresponding destination airports
    if request.form['id'] == 'ALL':
        c.execute('''SELECT a.Id, a.Code, a.Name, IFNULL(c.Name, "Other") CountryName FROM Airport a
                     LEFT JOIN Country c ON a.CountryId = c.Id''')
    else:
        c.execute('''SELECT DISTINCT a.Id, a.Code, a.Name, IFNULL(c.Name, "Other") CountryName FROM Route r
                     JOIN Airport a ON r.ToAirportId = a.Id
                     JOIN Country c ON a.CountryId = c.Id
                     WHERE r.FromAirportId = ? AND r.IsActive = 1''',
                  (request.form['id'], ))

    airport_list = c.fetchall()
    for country in sorted(set(d[3] for idx, d in enumerate(airport_list)), key=functools.cmp_to_key(compare)):
        result.append({
            'text': country,
            'children': [{
                'id': d[0],
                'text': d[2] + ' - ' + d[1] if d[2] is not None else d[1]
            } for idx, d in enumerate(airport_list) if d[3] == country]
        })

    return json.dumps(result)

@app.route('/airlines', methods=['POST'])
def get_airlines():
    if not all(param in list(request.form) for param in ['fromId', 'toId']):
        app.logger.error('missing one or more following parameters - fromId, toId')
        abort(404)

    db = get_db()
    c = db.cursor()
    c.execute('''SELECT a.Id, a.Name FROM Airline a
                 JOIN Route r ON a.Id = r.AirlineId
                 WHERE r.FromAirportId = ? AND r.ToAirportId = ? AND r.IsActive = 1''',
              (request.form['fromId'], request.form['toId']))
    return json.dumps([{
        'id': d[0],
        'name': d[1]
        } for idx, d in enumerate(c.fetchall())]
    )

@app.route('/data', methods=['POST'])
def get_data():
    if not all(param in list(request.form) for param in ['fromId', 'toId', 'month', 'airlines']):
        app.logger.error('missing one or more following parameters - fromId, toId, month, airlines')
        abort(404)

    db = get_db()
    c = db.cursor()
    c.execute('''SELECT fap.Code, tap.Code, c.Currency FROM Airport fap, Airport tap
                 JOIN Country c ON fap.CountryId = c.Id
                 WHERE fap.Id = ? AND tap.Id = ?''', (request.form['fromId'], request.form['toId']))
    codes = c.fetchone()
    currency = codes[2] if codes[2] is not None else 'TWD'
    data = get_visualized_data(
        get_fares(
            request.form['month'],
            codes[0],
            codes[1],
            [int(id_) for id_ in request.form['airlines'].split(',')],
            currency
    ))
    data['currency'] = currency
    return json.dumps(data)

if __name__ == '__main__':
    app.run()
