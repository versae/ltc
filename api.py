import os
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


def response(data, status=200, headers=None):
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "content-type, accept",
        "Access-Control-Max-Age": 60,
    }
    if not headers:
        headers = {}
    headers.update(cors_headers)
    return data, status, headers


class LondonTransitComission(restful.Resource):

    @classmethod
    def resource(cls):
        return cls, '/'

    def get(self):
        return response({
            'message': 'Welcome to the London Transit Commission REST API',
            'status': 200,
            'resources': [
                unicode(LondonTransitComission.resource()),
                unicode(RoutesList.resource()),
                unicode(Routes.resource()),
            ],
        })


class RoutesList(restful.Resource):

    @classmethod
    def resource(cls):
        return cls, '/routes', '/routes/'

    def get(self):
        url = URL("http://www.ltconline.ca/WebWatch/ada.aspx")
        try:
            dom = DOM(url.download(cached=True))
        except (HTTP404NotFound, URLTimeout):
            return response({
                "message": "LTC WebWatch service looks down",
                "status": 408,
            }, 408)
        routes = {}
        for a in dom("a.ada"):
            a_split = a.content.split(",")
            routes.update({
                a_split[0].strip(): a.content.replace(", ", " - ").title(),
            })
        return response(routes)


class Routes(restful.Resource):

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
            html = download(url.format(route), timeout=10, cached=False)
        except (HTTP404NotFound, URLTimeout):
            return response({
                "message": "LTC WebWatch service looks down",
                "status": 408,
            }, 408)
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
                        times.append({
                            "time": time,
                            "destination": destination.title(),
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
                        "stop_number": stop_number,
                        "times": times,
                    }
                    if args["latitude"] and args["longitude"]:
                        stop_location = stop["latitude"], stop["longitude"]
                        request_location = args["latitude"], args["longitude"]
                        stop.update({
                            "distance": distance(stop_location,
                                                 request_location).m,
                        })
                    stops.append(stop)
        if stops and args["latitude"] and args["longitude"]:
            stops.sort(key=lambda x: x["distance"])
        return response(stops)

api.add_resource(*LondonTransitComission.resource())
api.add_resource(*RoutesList.resource())
api.add_resource(*Routes.resource())

if __name__ == '__main__':
    app.run(debug=DEBUG)
