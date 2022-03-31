import json
import time
import requests
import yaml
import os

from bs4 import BeautifulSoup
from jinja2 import Template

SETTINGS = yaml.safe_load(open('secrets.yml', 'r').read())
API_KEY = SETTINGS['geolocation_api_key']
JS_API_KEY = SETTINGS['geolocation_js_api_key']
GOOGLE_MAPS_URL = 'https://maps.googleapis.com/maps/api/geocode/json'
DEFAULT_PAGES = 10
URL = input('Please enter Kijiji URL: ')
PRICE = int(input('Please enter max price: '))
OUTPUT = input('Please enter output filename (default map.html): ') or 'map.html'
index = URL.rindex('/')
part1 = URL[:index + 1]
part2 = URL[index + 1:]
DEFAULT_URL_TEMPLATE = ('{part1}{page}{part2}')
DEFAULT_MAP_CENTER = [45.440294, -75.732922] #Ottawa
#DEFAULT_MAP_CENTER = [45.5071015, -73.5961619] #Montreal
TEMPLATE_NAME = 'template.jinja2'
FAKE_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like '
    'Gecko) Chrome/40.0.2214.85 Safari/537.36')

def geolocate(address):
    payload = {
        "address": address,
        "key": API_KEY,
    }

    result = requests.get(GOOGLE_MAPS_URL, params=payload)

    result_object = result.json()
    result_results = result_object["results"]
    if len(result_results) < 1:
        return None

    result_geometry = result_results[0]["geometry"]
    latlong = result_geometry["location"]

    return [latlong['lat'], latlong['lng']]

def urls(template, pages):
    yield template.format(part1=part1, page='', part2=part2)

    if pages == 1:
        return

    #adjust total # of pages
    url = template.format(part1=part1, page='/', part2=part2)
    response = requests.get(url, headers={'User-Agent': FAKE_USER_AGENT})
    content = response.content
    soup = BeautifulSoup(content, 'html.parser')
    all_pages = soup.select('div[class=pagination]')[0].find_all('a')
    if len(all_pages) > 1:
        last_page = all_pages[-3].text
    else:
        last_page = 1
    pages = int(last_page)

    for page in range(2, pages + 1):
        yield(template.format(part1=part1, page='page-{0}/'.format(page), part2=part2))

def get_details(url):
    # Sleep 3 seconds to not get throttled
    time.sleep(3)
    response = requests.get(url, headers={'User-Agent': FAKE_USER_AGENT})
    content = response.content
    soup = BeautifulSoup(content, 'html.parser')

    details = {
        'price': None,
        'address': None,
        'lat_long': None,
        'date': None,
    }

    price_el = soup.select('div[class=priceWrapper-1165431705]')
    if price_el:
        try:
            price_el = price_el[0].find('span').get('content')
            details['price'] = float(price_el.replace(',', ''))
        except ValueError:
            pass

    address_el = soup.select('span[class=address-3617944557]')
    if address_el:
        details['address'] = address_el[0].text.split("\n")[0]
        details['lat_long'] = geolocate(details['address'])

    date_el = soup.select('div[class=datePosted-383942873]')
    if date_el:
        details['date'] = date_el[0].text

    return details

def get_items(url):
    response = requests.get(url, headers={'User-Agent': FAKE_USER_AGENT})
    content = response.content
    soup = BeautifulSoup(content, 'html.parser')

    items = soup.find_all('div', attrs={'class': 'regular-ad'})
    return(items)

def get_posts(url):
    items = get_items(url)

    while len(items) == 0:
        print('Throttled by Kijiji, sleeping 120 sec. between pages')
        time.sleep(120)
        items = get_items(url)

    for item in items:
        title_el = item.find('a', attrs={'class': 'title'})
        title = title_el.text.strip()
        print(title)
        link = "https://www.kijiji.ca{path}".format(path=title_el.attrs['href'])
        print(link)
        description = item.find('div', attrs={'class': 'description'}).text.strip()

        details = get_details(link)

        yield({
            'title': title,
            'link': link,
            'description': description,
            'address': details['address'],
            'price': details['price'],
            'lat_long': details['lat_long'],
            'date': details['date'],
        })

def render_map(appartments):
    with open(TEMPLATE_NAME, 'r') as template_file:
        template = Template(template_file.read())
        return template.render(
            appartments=appartments,
            js_api_key=JS_API_KEY,
            map_center=DEFAULT_MAP_CENTER,
        )

def run():
    template = DEFAULT_URL_TEMPLATE

    appartments = []
    with open('exclusions.json') as f:
        exclusions = json.load(f)

    for url in urls(template, DEFAULT_PAGES):
        print("Processing {url}".format(url=url))
        for appartment in get_posts(url):
            if appartment['link'] not in exclusions:
                if appartment['price']:
                    if appartment['price'] <= PRICE:
                        appartments.append(appartment)
                    else:
                        print('Hit price out of range for some reason')

    the_map = open(OUTPUT, 'w')
    the_map.write(render_map(json.dumps(appartments)))
    the_map.close()
    os.system('mv {} /var/www/html/'.format(OUTPUT))

if __name__ == "__main__":
    run()
