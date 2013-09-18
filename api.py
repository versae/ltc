import os
from functools import wraps
from geopy.distance import distance

from pattern.web import DOM
from pattern.web import download
from pattern.web import HTTP404NotFound
from pattern.web import URL
from pattern.web import URLTimeout

from flask import Flask
from flask.ext import restful
from flask.ext.restful import reqparse

DEBUG = bool(os.environ.get("DEBUG", False))

app = Flask(__name__)
api = restful.Api(app)
parser = reqparse.RequestParser()
parser.add_argument('direction', type=str, required=False,
                    help='Direction of the route (north, east, south, west)')
parser.add_argument('stop', type=int, required=False,
                    help='Stop number')
parser.add_argument('latitude', type=float, required=False,
                    help='Latitude to sort results by')
parser.add_argument('longitude', type=float, required=False,
                    help='Longitude to sort results by')


def cors(func, allow_origin=None, allow_headers=None, max_age=None):
    if not allow_origin:
        allow_origin = "*"
    if not allow_headers:
        allow_headers = "content-type, accept"
    if not max_age:
        max_age = 60

    @wraps(func)
    def wrapper(*args, **kwargs):
        response = func(*args, **kwargs)
        cors_headers = {
            "Access-Control-Allow-Origin": allow_origin,
            "Access-Control-Allow-Methods": func.__name__.upper(),
            "Access-Control-Allow-Headers": allow_headers,
            "Access-Control-Max-Age": max_age,
        }
        if isinstance(response, tuple):
            if len(response) == 3:
                headers = response[-1]
            else:
                headers = {}
            headers.update(cors_headers)
            return (response[0], response[1], headers)
        else:
            return response, 200, cors_headers
    return wrapper


class Resource(restful.Resource):
    method_decorators = [cors]


class LondonTransitCommission(Resource):

    @classmethod
    def resource(cls):
        return cls, '/'

    def get(self):
        args_text = []
        for arg in parser.args:
            arg_text = {
                "name": arg.name,
                "type": arg.type.__name__,
                "help": arg.help,
                "required": arg.required,
            }
            args_text.append(arg_text)
        return {
            'message': 'Welcome to the London Transit Commission API',
            'source': 'https://github.com/versae/ltc',
            'status': 200,
            'resources': [{
                "resource": repr(LondonTransitCommission),
                "endpoints": LondonTransitCommission.resource()[1:],
            }, {
                "resource": repr(RoutesList),
                "endpoints": RoutesList.resource()[1:],
                "params": args_text,
            }, {
                "resource": repr(Routes),
                "endpoints": Routes.resource()[1:],
                "params": args_text,
            }],
        }, 200


class RoutesList(Resource):

    @classmethod
    def resource(cls):
        return cls, '/routes', '/routes/'

    def get(self):
        url = URL("http://www.ltconline.ca/WebWatch/ada.aspx")
        try:
            dom = DOM(url.download(cached=True))
        except (HTTP404NotFound, URLTimeout):
            return {
                "message": "LTC WebWatch service looks down",
                "status": 408,
            }, 408
        routes = {}
        for a in dom("a.ada"):
            a_split = a.content.split(",")
            routes.update({
                a_split[0].strip(): a.content.replace(", ", " - ").title(),
            })
        return routes


class Routes(Resource):

    @classmethod
    def resource(cls):
        return cls, '/routes/<string:route>', '/routes/<string:route>/'

    def get(self, route):
        parser = reqparse.RequestParser()
        parser.add_argument('direction', type=str, required=False,
                            help='Direction of the route')
        parser.add_argument('stop', type=int, required=False,
                            help='Stop number')
        parser.add_argument('latitude', type=float, required=False,
                            help='Latitude to sort results by')
        parser.add_argument('longitude', type=float, required=False,
                            help='Longitude to sort results by')
        args = parser.parse_args()
        url = "http://www.ltconline.ca/WebWatch/UpdateWebMap.aspx?u={}"
        try:
            html = download(url.format(route), timeout=60, cached=False)
        except (HTTP404NotFound, URLTimeout) as ex:
            msg = "LTC WebWatch service looks down ({})"
            return {
                "message": msg.format(repr(ex)),
                "status": 408,
            }, 408
        timestamp, main_stops, info_text, minor_stops = html.split("*")
        stops_lines = (main_stops + minor_stops).split(";")
        stops = []
        for stop_line in stops_lines:
            stop_line_split = stop_line.split("|")
            if len(stop_line_split) == 7:
                (latitude, longitude, name, direction,
                 stop_number, times_text) = stop_line_split[:6]
                stop_number = int(stop_number.replace("Stop Number ", ""))
                times = []
                for time_text in times_text.split("<br>"):
                    time_text_splits = time_text.split(" TO ")
                    if len(time_text_splits) == 2:
                        time, destination = time_text_splits
                        destination = destination.strip()
                        route_time = unicode(route)
                        if destination.startswith(route_time):
                            destination_split = destination.split(" ", 1)
                            route_time, destination = destination_split
                        times.append({
                            "time": time,
                            "destination": destination.title(),
                            "route": route_time,
                        })
                direction = direction.lower()
                if ((not args["stop"] or args["stop"] == stop_number) and
                    (not args["direction"]
                     or (direction.startswith(args["direction"].lower())
                         or args["direction"].lower() == direction))):
                    stop = {
                        "latitude": float(latitude),
                        "longitude": float(longitude),
                        "name": name.title(),
                        "direction": direction.title(),
                        "number": stop_number,
                        "times": times,
                        "route": route,
                    }
                    if args["latitude"] and args["longitude"]:
                        stop_location = stop["latitude"], stop["longitude"]
                        request_location = args["latitude"], args["longitude"]
                        distance_obj = distance(stop_location,
                                                request_location)
                        stop.update({
                            "distance": {
                                "meters": distance_obj.m,
                                "miles": distance_obj.miles,
                            }
                        })
                    stops.append(stop)
        if stops and args["latitude"] and args["longitude"]:
            stops.sort(key=lambda x: x["distance"]["meters"])
        return stops

api.add_resource(*LondonTransitCommission.resource())
api.add_resource(*RoutesList.resource())
api.add_resource(*Routes.resource())

if __name__ == '__main__':
    app.run(debug=DEBUG)
