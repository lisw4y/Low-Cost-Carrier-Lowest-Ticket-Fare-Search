# Low-cost Carrier Lowest Ticket Fare Search

A service that helps users search the lowest ticket fares in the five low-cost airlines, Tigerair Taiwan, Vanilla Air, Scoot, Peach Aviation, and Jetstar with showing one-month fares for one search
> **Caution!** Searching for ticket fares of `Scoot` and `Peach Aviation` is not available now.

## Required Packages

> This project is programmed under `python 3.6.3`.

* requests 2.18.4
* pandas 0.22.0
* altair 1.2.1
* plotly 2.2.3
* selenium 3.8.0
* beautifulsoup4 4.6.0
* hanziconv 0.3.2
* Flask 0.12.2
> Selenium requires a driver to interact with the browser. `Chrome` is used by selenium in this project to fetch website data, so [downloading the Chrome driver](https://sites.google.com/a/chromium.org/chromedriver/downloads) to enable selenium to use Chrome.

## Guidelines

1. Install the required packages. The [requirements.txt](https://github.com/lisw4y/Low-Cost-Carrier-Lowest-Ticket-Fare-Search/blob/master/requirements.txt) includes all related packages. You can simply install all packages by using `pip` with the following command.
    ```bash
    pip install -r requirements.txt
    ```
1. Execute the [server.py](https://github.com/lisw4y/Low-Cost-Carrier-Lowest-Ticket-Fare-Search/blob/master/server.py) to get or update the information of countries, airports, and routes.
1. Use [DB browser for SQLite](http://sqlitebrowser.org/) to open the lcc.db file and update some incomplete parts of the data in the database that was fetched in the step 2 because the function in the server cannot fetch the information perfectly (But it already helps the user get about 90% of the data).
1. Execute the [service.py](https://github.com/lisw4y/Low-Cost-Carrier-Lowest-Ticket-Fare-Search/blob/master/service.py) to activate the local server.
1. Turn on the browser and direct to the url (`127.0.0.1:5000` as default), then enjoying the search function.

## Demo

![Demo](https://i.imgur.com/ZSaHrVN.png)